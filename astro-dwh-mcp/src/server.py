"""FastMCP server for data warehouse operations.

This server exposes tools for Python code execution, package installation,
kernel lifecycle management, and SQL database operations via the Model Context Protocol (MCP).

Usage:
    python -m src.server

Or via the installed script:
    astro-dwh-mcp
"""

import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .cache import (
    get_pattern_cache,
    get_schema_cache,
    get_template_cache,
)
from .config import get_session_data_dir
from .kernel import KernelManager
from .mocks import (
    get_mock_list_schemas,
    get_mock_list_tables,
    get_mock_response,
    get_mock_tables_info,
    is_dry_run,
)
from .scripts import (
    ValidationError,
    render_get_tables_info,
    render_list_schemas_configured,
    render_list_schemas_single_db,
    render_list_tables,
    render_run_sql,
)
from .warehouse import WarehouseConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Timeout constants (in seconds)
TIMEOUT_ENV_SETUP = 10.0
TIMEOUT_CODE_EXECUTION = 30.0
TIMEOUT_SCHEMA_QUERY = 60.0
TIMEOUT_SQL_EXECUTION = 120.0

# Global kernel manager instance
_kernel_manager: KernelManager | None = None

# Session state tracking
_warehouse_prelude_executed: dict[str, bool] = {}
_query_counters: dict[str, int] = {}

# Connection error patterns
CONNECTION_ERROR_PATTERNS = [
    "connection",
    "socket",
    "timeout",
    "expired",
    "authentication",
    "programmingerror",
    "databaseerror",
    "operationalerror",
]


def get_kernel_manager() -> KernelManager:
    """Get or create the global kernel manager instance."""
    global _kernel_manager
    if _kernel_manager is None:
        _kernel_manager = KernelManager()
    return _kernel_manager


def _is_connection_error(msg: str) -> bool:
    """Check if an error message indicates a connection issue."""
    msg_lower = msg.lower()
    return any(pattern in msg_lower for pattern in CONNECTION_ERROR_PATTERNS)


def _clear_warehouse_connection(session_id: str) -> None:
    """Clear the warehouse connection flag for a session."""
    _warehouse_prelude_executed.pop(session_id, None)


def _get_next_query_num(session_id: str) -> int:
    """Get the next query number for a session."""
    count = _query_counters.get(session_id, 0) + 1
    _query_counters[session_id] = count
    return count


def _handle_execution_error(
    error: str | None,
    output: str | None,
    session_id: str,
    operation: str,
) -> str:
    """Handle execution errors, clearing connection on connection errors.

    Args:
        error: Error message from execution
        output: Output from execution (may contain error info)
        session_id: Current session ID
        operation: Name of the operation for error message

    Returns:
        Formatted error message string
    """
    error_msg = error or "Unknown error"
    if _is_connection_error(error_msg) or (output and _is_connection_error(output)):
        _clear_warehouse_connection(session_id)
        logger.warning("Warehouse connection error detected, will reconnect on next query")

    if output:
        return f"Output:\n{output}\n\nError:\n{error_msg}"
    return f"Error: {operation} failed: {error_msg}"


async def _ensure_warehouse_connection(
    kernel_manager: KernelManager,
    session_id: str,
    warehouse_name: str | None = None,
) -> None:
    """Ensure the warehouse connection is established in the kernel.

    Args:
        kernel_manager: The kernel manager instance
        session_id: Current session ID
        warehouse_name: Optional specific warehouse name

    Raises:
        Exception: If connection cannot be established
    """
    # Check if prelude was already executed for this session
    if _warehouse_prelude_executed.get(session_id):
        return

    logger.info(f"Establishing warehouse connection for session {session_id}")

    # Load warehouse configuration
    config = WarehouseConfig.load()

    # Get the specified warehouse or default
    if warehouse_name:
        connector = config.get(warehouse_name)
    else:
        _, connector = config.get_default()

    # Install required packages
    packages = connector.required_packages()
    try:
        await kernel_manager.install_packages(packages)
    except Exception as e:
        logger.warning(f"Failed to install packages (may already be installed): {e}")

    # Inject environment variables into the kernel
    # (kernel runs in separate process without access to MCP server's env vars)
    env_vars = connector.get_env_vars_for_kernel()
    if env_vars:
        env_setup_code = "import os\n"
        for var_name, var_value in env_vars.items():
            # Use repr to safely escape the value
            env_setup_code += f"os.environ[{var_name!r}] = {var_value!r}\n"
        env_setup_code += "print('Environment variables injected')"

        env_result = await kernel_manager.execute(env_setup_code, timeout=TIMEOUT_ENV_SETUP)
        if not env_result.success:
            logger.warning(f"Failed to inject env vars: {env_result.error}")
        else:
            logger.debug(f"Injected {len(env_vars)} env vars into kernel")

    # Execute the prelude to establish connection
    prelude = connector.to_python_prelude()
    result = await kernel_manager.execute(prelude, timeout=TIMEOUT_SCHEMA_QUERY)

    if not result.success:
        error_msg = result.error or "Unknown error"
        raise Exception(f"Failed to establish warehouse connection: {error_msg}")

    logger.info(f"Warehouse connection established: {result.output}")
    _warehouse_prelude_executed[session_id] = True


def _write_sql_file(query: str, query_num: int, session_data_dir: Path) -> Path:
    """Write SQL query to a file and return the path.

    This approach avoids escaping issues by having Python read from the file.
    """
    session_data_dir.mkdir(parents=True, exist_ok=True)
    sql_file = session_data_dir / f"query_{query_num:03d}.sql"
    sql_file.write_text(query, encoding="utf-8")
    return sql_file


# Create the FastMCP server
mcp = FastMCP("astro-dwh-mcp")


@mcp.tool()
async def execute_python(
    code: str,
    timeout: float = 30.0,
    session_id: str | None = None,
) -> str:
    """Execute Python code in the Jupyter kernel.

    The kernel maintains state across executions - variables and imports persist.
    Use this for data analysis, visualization, and computation tasks.

    Pre-installed packages: polars, pandas, numpy, matplotlib, seaborn

    Args:
        code: Python code to execute. Keep code blocks small (10-15 lines)
              for better error handling and user experience.
        timeout: Optional execution timeout in seconds (default: 30, max: 300)
        session_id: Optional session identifier for state isolation

    Returns:
        Execution output or error message
    """
    kernel_manager = get_kernel_manager()

    # Set session if provided
    if session_id:
        await kernel_manager.set_session(session_id)

    # Clamp timeout
    timeout = max(1.0, min(300.0, timeout))

    result = await kernel_manager.execute(code, timeout=timeout)

    if result.success:
        return result.output if result.output else "(no output)"
    else:
        error_msg = result.error or "Execution failed"
        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error:\n{error_msg}"


@mcp.tool()
async def install_packages(packages: list[str]) -> str:
    """Install additional Python packages in the kernel environment.

    Supports version specs like 'plotly>=5.0' or 'numpy==1.24.0'.
    Packages are installed immediately and available for import in subsequent code.

    Args:
        packages: List of package names to install.
                  Can include version specs (e.g., ['plotly>=5.0', 'scipy==1.11.0'])

    Returns:
        Success message or error details
    """
    if not packages:
        return "Error: No packages specified"

    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.install_packages(packages)
        return f"Successfully installed: {', '.join(packages)}"
    except Exception as e:
        return f"Failed to install packages: {e}"


@mcp.tool()
async def start_kernel() -> str:
    """Start the Jupyter kernel.

    The kernel is started automatically on first execution, but this tool
    allows explicit control over kernel lifecycle.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.start()
        status = kernel_manager.get_status()
        return f"Kernel started successfully. Status: {status}"
    except Exception as e:
        return f"Failed to start kernel: {e}"


@mcp.tool()
async def stop_kernel() -> str:
    """Stop the Jupyter kernel.

    This clears all kernel state (variables, imports, etc.).
    A new kernel will be started on next execution.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.stop()
        return "Kernel stopped successfully"
    except Exception as e:
        return f"Failed to stop kernel: {e}"


@mcp.tool()
async def restart_kernel() -> str:
    """Restart the Jupyter kernel, clearing all state.

    This stops the current kernel and starts a fresh one.
    All variables and imports will be lost.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.restart()
        status = kernel_manager.get_status()
        return f"Kernel restarted successfully. Status: {status}"
    except Exception as e:
        return f"Failed to restart kernel: {e}"


@mcp.tool()
async def kernel_status() -> dict[str, Any]:
    """Get the current kernel status.

    Returns information about the kernel state including:
    - Whether the kernel is started
    - Whether it's currently alive
    - Current session ID and directory
    - Whether the session prelude has been executed

    Returns:
        Dictionary with kernel status information
    """
    kernel_manager = get_kernel_manager()
    return kernel_manager.get_status()


# =============================================================================
# SQL Tools
# =============================================================================


@mcp.tool(structured_output=False)
async def run_sql(
    query: str,
    limit: int = 100,
    save_result: bool = True,
    session_id: str | None = None,
) -> str:
    """Execute SQL query against the configured data warehouse.

    Returns results as a table and saves them as parquet files for later retrieval.
    Use this for querying data, exploring schemas, and running analytics queries.
    Always use fully qualified table names (DATABASE.SCHEMA.TABLE).

    Args:
        query: SQL query to execute. Always use fully qualified table names.
               Add LIMIT clause for exploratory queries.
        limit: Maximum number of rows to return (default: 100, use -1 for unlimited)
        save_result: Whether to save the query result as a parquet file (default: true)
        session_id: Optional session identifier for state isolation

    Returns:
        Query results as formatted table, or error message
    """
    # DRY_RUN mode: return mock response instead of executing real query
    if is_dry_run():
        return get_mock_response(query, "run_sql")

    kernel_manager = get_kernel_manager()

    if not query or not query.strip():
        return "Error: query parameter is required"

    # Clamp limit
    if limit < -1:
        limit = -1
    elif limit > 100000:
        limit = 100000

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Ensure warehouse connection
    try:
        await _ensure_warehouse_connection(kernel_manager, effective_session_id)
    except Exception as e:
        return f"Error: Failed to establish warehouse connection: {e}"

    # Get session data directory and query number
    session_data_dir = get_session_data_dir(effective_session_id)
    query_num = _get_next_query_num(effective_session_id) if save_result else 0

    # Write SQL to file to avoid escaping issues
    sql_file_path = _write_sql_file(query, query_num, session_data_dir)

    # Render and execute the script
    code = render_run_sql(
        sql_file_path=str(sql_file_path),
        limit=limit,
        save_parquet=save_result,
        query_num=query_num,
        session_data_dir=str(session_data_dir),
    )

    result = await kernel_manager.execute(code, timeout=TIMEOUT_SQL_EXECUTION)

    if not result.success:
        return _handle_execution_error(
            result.error, result.output, effective_session_id, "SQL execution"
        )

    return result.output if result.output else "(no output)"


@mcp.tool(structured_output=False)
async def list_schemas(
    database: str | None = None,
    session_id: str | None = None,
) -> str:
    """List all available schemas across configured databases.

    Returns schema names with table counts. ONLY use this tool once per session.

    Args:
        database: Optional: filter to a specific database. If not provided,
                  lists schemas from all configured databases in warehouse.yml.
        session_id: Optional session identifier for state isolation

    Returns:
        JSON with schema information, or error message
    """
    # DRY_RUN mode: return mock response
    if is_dry_run():
        return get_mock_list_schemas()

    kernel_manager = get_kernel_manager()

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Ensure warehouse connection
    try:
        await _ensure_warehouse_connection(kernel_manager, effective_session_id)
    except Exception as e:
        return f"Error: Failed to establish warehouse connection: {e}"

    # Build the script
    try:
        if database:
            code = render_list_schemas_single_db(database)
        else:
            # Get configured databases from warehouse config
            config = WarehouseConfig.load()
            _, connector = config.get_default()
            configured_databases = connector.databases
            if configured_databases:
                code = render_list_schemas_configured(configured_databases)
            else:
                return "Error: No databases configured in warehouse.yml"
    except ValidationError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: Failed to load warehouse config: {e}"

    result = await kernel_manager.execute(code, timeout=TIMEOUT_SCHEMA_QUERY)

    if not result.success:
        return _handle_execution_error(
            result.error, result.output, effective_session_id, "List schemas"
        )

    return result.output if result.output else "(no output)"


@mcp.tool(structured_output=False)
async def list_tables(
    database: str,
    schema: str,
    session_id: str | None = None,
) -> str:
    """List all tables in a specific schema.

    Returns table names, types, and row counts. Use this after list_schemas
    to discover available tables.

    Args:
        database: Name of the database containing the schema
        schema: Name of the schema to list tables from
        session_id: Optional session identifier for state isolation

    Returns:
        JSON with table information, or error message
    """
    # DRY_RUN mode: return mock response
    if is_dry_run():
        return get_mock_list_tables(database, schema)

    kernel_manager = get_kernel_manager()

    if not database:
        return "Error: database parameter is required"
    if not schema:
        return "Error: schema parameter is required"

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Ensure warehouse connection
    try:
        await _ensure_warehouse_connection(kernel_manager, effective_session_id)
    except Exception as e:
        return f"Error: Failed to establish warehouse connection: {e}"

    # Render the script
    try:
        code = render_list_tables(database, schema)
    except ValidationError as e:
        return f"Error: {e}"

    result = await kernel_manager.execute(code, timeout=TIMEOUT_SCHEMA_QUERY)

    if not result.success:
        return _handle_execution_error(
            result.error, result.output, effective_session_id, "List tables"
        )

    return result.output if result.output else "(no output)"


@mcp.tool(structured_output=False)
async def get_tables_info(
    database: str,
    schema: str,
    tables: list[str],
    session_id: str | None = None,
) -> str:
    """Get detailed information about multiple tables.

    Returns columns, data types, and descriptions for each table.
    Use this to understand table structures before writing queries.
    More efficient than calling get_table_info multiple times.

    Args:
        database: Name of the database containing the tables
        schema: Name of the schema containing the tables
        tables: List of table names to get information about (max 50)
        session_id: Optional session identifier for state isolation

    Returns:
        JSON with detailed table information, or error message
    """
    # DRY_RUN mode: return mock response
    if is_dry_run():
        return get_mock_tables_info(database, schema, tables)

    kernel_manager = get_kernel_manager()

    if not database:
        return "Error: database parameter is required"
    if not schema:
        return "Error: schema parameter is required"
    if not tables:
        return "Error: tables parameter is required (list of table names)"

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Ensure warehouse connection
    try:
        await _ensure_warehouse_connection(kernel_manager, effective_session_id)
    except Exception as e:
        return f"Error: Failed to establish warehouse connection: {e}"

    # Render the script
    try:
        code = render_get_tables_info(database, schema, tables)
    except ValidationError as e:
        return f"Error: {e}"

    result = await kernel_manager.execute(code, timeout=TIMEOUT_SCHEMA_QUERY)

    if not result.success:
        return _handle_execution_error(
            result.error, result.output, effective_session_id, "Get tables info"
        )

    return result.output if result.output else "(no output)"


# =============================================================================
# Cache Management Tools
# =============================================================================


@mcp.tool()
async def cache_status() -> dict[str, Any]:
    """Get schema cache statistics and health.

    Shows how many concepts, tables, and query templates are cached,
    plus counts of stale entries that may need refresh.

    Returns:
        Dictionary with cache statistics
    """
    schema_cache = get_schema_cache()
    template_cache = get_template_cache()

    return {
        "schema_cache": schema_cache.get_stats(),
        "template_cache": template_cache.get_stats(),
    }


@mcp.tool()
async def clear_cache(
    cache_type: str = "all",
    purge_stale_only: bool = False,
) -> str:
    """Clear the schema and query template cache.

    Use this when schema has changed or cache is causing issues.

    Args:
        cache_type: What to clear: "all", "schemas", "concepts", or "templates"
        purge_stale_only: If true, only remove entries older than TTL (7 days)

    Returns:
        Summary of what was cleared
    """
    schema_cache = get_schema_cache()
    template_cache = get_template_cache()
    results = []

    if purge_stale_only:
        if cache_type in ("all", "schemas", "concepts"):
            purged = schema_cache.purge_stale()
            results.append(
                f"Purged {purged['tables_purged']} stale tables, "
                f"{purged['concepts_purged']} stale concepts"
            )
        return "; ".join(results) if results else "No stale entries found"

    if cache_type == "all":
        schema_cache.clear_all()
        template_cache.clear_all()
        return "Cleared all caches (schemas, concepts, templates)"
    elif cache_type == "schemas":
        schema_cache._tables = {}
        schema_cache.save()
        return "Cleared table schema cache"
    elif cache_type == "concepts":
        schema_cache._concepts = {}
        schema_cache.save()
        return "Cleared concept cache"
    elif cache_type == "templates":
        template_cache.clear_all()
        return "Cleared query template cache"
    else:
        return f"Unknown cache_type: {cache_type}. Use: all, schemas, concepts, templates"


@mcp.tool()
async def lookup_concept(concept: str) -> dict[str, Any]:
    """Look up a business concept in the cache.

    Use this to quickly find which table contains data for a concept
    like "customers", "orders", "task_runs", etc.

    Args:
        concept: Business concept to look up (e.g., "customers", "deployments")

    Returns:
        Cached table mapping if found, or suggestions
    """
    schema_cache = get_schema_cache()
    result = schema_cache.get_concept(concept)

    if result:
        return {
            "found": True,
            "concept": concept,
            "table": result.get("table"),
            "key_column": result.get("key_column"),
            "date_column": result.get("date_column"),
            "learned_at": result.get("learned_at"),
        }

    # Suggest similar concepts
    all_concepts = list(schema_cache.concepts.keys())
    similar = [c for c in all_concepts if concept.lower() in c or c in concept.lower()]

    return {
        "found": False,
        "concept": concept,
        "similar_concepts": similar[:5],
        "hint": "Use learn_concept to teach this mapping after a successful query",
    }


@mcp.tool()
async def learn_concept(
    concept: str,
    table: str,
    key_column: str | None = None,
    date_column: str | None = None,
) -> str:
    """Teach the cache a new concept → table mapping.

    After successfully querying data, use this to remember which table
    contains data for a business concept. Future queries can skip discovery.

    Args:
        concept: Business concept name (e.g., "customers", "task_runs")
        table: Full table name (DATABASE.SCHEMA.TABLE)
        key_column: Primary key or main identifier column
        date_column: Main timestamp column for filtering

    Returns:
        Confirmation message
    """
    schema_cache = get_schema_cache()

    # Validate table name format
    parts = table.split(".")
    if len(parts) != 3:
        return f"Error: table must be fully qualified (DATABASE.SCHEMA.TABLE), got: {table}"

    schema_cache.set_concept(concept, table, key_column, date_column)

    return f"Learned: '{concept}' → {table}"


@mcp.tool()
async def get_cached_table(table: str) -> dict[str, Any]:
    """Get cached schema information for a table.

    Returns column names, types, and descriptions if the table
    has been queried before and cached.

    Args:
        table: Full table name (DATABASE.SCHEMA.TABLE)

    Returns:
        Cached table info or not-found message
    """
    schema_cache = get_schema_cache()
    cached = schema_cache.get_table(table)

    if cached:
        return {
            "found": True,
            "table": cached.full_name,
            "columns": cached.columns,
            "row_count": cached.row_count,
            "comment": cached.comment,
            "cached_at": cached.cached_at,
            "is_stale": cached.is_stale(),
        }

    return {
        "found": False,
        "table": table,
        "hint": "Use get_tables_info to fetch and cache this table's schema",
    }


@mcp.tool()
async def lookup_pattern(question: str) -> dict[str, Any]:
    """CALL THIS FIRST before any data query. Finds proven strategies for question types.

    Returns cached patterns with step-by-step strategies, tables to use, and gotchas
    to avoid. If a pattern matches, follow its strategy instead of running discovery.

    Example: "who uses HITLOperator" → returns operator_usage pattern with proven
    approach that avoids timeouts and finds all operator variants.

    Args:
        question: The user's question (e.g., "who uses S3Operator", "customer count")

    Returns:
        Matching patterns with strategies, or hint to proceed with normal discovery
    """
    pattern_cache = get_pattern_cache()
    matches = pattern_cache.lookup_by_question(question)

    if matches:
        return {
            "found": True,
            "question": question,
            "patterns": [
                {
                    "name": p.pattern_name,
                    "question_types": p.question_types,
                    "strategy": p.strategy,
                    "tables_used": p.tables_used,
                    "gotchas": p.gotchas,
                    "example_query": p.example_query,
                    "success_count": p.success_count,
                }
                for p in matches
            ],
        }

    return {
        "found": False,
        "question": question,
        "hint": "No matching patterns. Use learn_pattern after a successful query.",
    }


@mcp.tool()
async def learn_pattern(
    pattern_name: str,
    question_types: list[str],
    strategy: list[str],
    tables_used: list[str],
    gotchas: list[str],
    example_query: str | None = None,
    ttl_days: int = 90,
) -> str:
    """Save a query pattern for future use.

    After successfully answering a question, use this to remember the approach.
    Future similar questions can use this pattern to skip discovery.

    Args:
        pattern_name: Unique name (e.g., "operator_usage", "customer_metrics")
        question_types: Types of questions this pattern answers
                       (e.g., ["who uses X", "which customers use X"])
        strategy: Step-by-step approach that worked (list of steps)
        tables_used: Tables involved (e.g., ["HQ.MODEL_ASTRO.TASK_RUNS"])
        gotchas: What to avoid / what failed (e.g., ["GROUP BY times out"])
        example_query: Optional working SQL example
        ttl_days: Days before pattern expires (default 90)

    Returns:
        Confirmation message
    """
    pattern_cache = get_pattern_cache()

    # Check if pattern already exists
    existing = pattern_cache.get_pattern(pattern_name)
    if existing:
        # Update success count and overwrite
        success_count = existing.success_count + 1
        pattern_cache.delete_pattern(pattern_name)
    else:
        success_count = 1

    pattern = pattern_cache.store_pattern(
        pattern_name=pattern_name,
        question_types=question_types,
        strategy=strategy,
        tables_used=tables_used,
        gotchas=gotchas,
        example_query=example_query,
        ttl_days=ttl_days,
    )
    pattern.success_count = success_count
    pattern_cache.save()

    return f"Learned pattern: '{pattern_name}' for questions like {question_types}"


@mcp.tool()
async def record_pattern_outcome(pattern_name: str, success: bool) -> str:
    """Record whether a pattern helped or failed.

    Call this after using a pattern to track its effectiveness.
    Patterns with more failures than successes may be auto-purged.

    Args:
        pattern_name: Name of the pattern used
        success: True if pattern helped, False if it led to wrong approach

    Returns:
        Updated pattern stats
    """
    pattern_cache = get_pattern_cache()
    pattern = pattern_cache.get_pattern(pattern_name)

    if not pattern:
        return f"Pattern '{pattern_name}' not found"

    if success:
        pattern_cache.record_success(pattern_name)
        new_count = pattern.success_count + 1
        return f"Pattern '{pattern_name}': {new_count} successes, {pattern.failure_count} failures"
    else:
        pattern_cache.record_failure(pattern_name)
        new_count = pattern.failure_count + 1
        return f"Pattern '{pattern_name}': {pattern.success_count} successes, {new_count} failures"


@mcp.tool()
async def list_patterns() -> dict[str, Any]:
    """List all saved query patterns.

    Returns:
        All patterns with summary info
    """
    pattern_cache = get_pattern_cache()
    patterns = pattern_cache.list_patterns()

    return {
        "count": len(patterns),
        "patterns": patterns,
    }


@mcp.tool()
async def delete_pattern(pattern_name: str) -> str:
    """Delete a saved pattern.

    Use this when a pattern is outdated or no longer useful.

    Args:
        pattern_name: Name of the pattern to delete

    Returns:
        Confirmation or error message
    """
    pattern_cache = get_pattern_cache()

    if pattern_cache.delete_pattern(pattern_name):
        return f"Deleted pattern: '{pattern_name}'"
    else:
        return f"Pattern '{pattern_name}' not found"


def main() -> None:
    """Entry point for the data warehouse MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
