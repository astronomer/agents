"""FastMCP server for Jupyter kernel code execution.

This server exposes tools for Python code execution, package installation,
kernel lifecycle management, and SQL database operations via the Model Context Protocol (MCP).

Usage:
    python -m data_jupyter.server

Or via the installed script:
    data-jupyter
"""

import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import get_session_data_dir
from .kernel import KernelManager
from .scripts import (
    ValidationError,
    render_get_tables_info,
    render_list_query_results,
    render_list_schemas_configured,
    render_list_schemas_single_db,
    render_list_tables,
    render_load_query_result,
    render_run_sql,
)
from .warehouse import WarehouseConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

        env_result = await kernel_manager.execute(env_setup_code, timeout=10.0)
        if not env_result.success:
            logger.warning(f"Failed to inject env vars: {env_result.error}")
        else:
            logger.debug(f"Injected {len(env_vars)} env vars into kernel")

    # Execute the prelude to establish connection
    prelude = connector.to_python_prelude()
    result = await kernel_manager.execute(prelude, timeout=60.0)

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
mcp = FastMCP("data-jupyter")


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


@mcp.tool()
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

    result = await kernel_manager.execute(code, timeout=120.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        # Check for connection errors and reset prelude flag
        if _is_connection_error(error_msg) or (
            result.output and _is_connection_error(result.output)
        ):
            _clear_warehouse_connection(effective_session_id)
            logger.warning("Warehouse connection error detected, will reconnect on next query")

        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: SQL execution failed: {error_msg}"

    return result.output if result.output else "(no output)"


@mcp.tool()
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

    result = await kernel_manager.execute(code, timeout=60.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        if _is_connection_error(error_msg) or (
            result.output and _is_connection_error(result.output)
        ):
            _clear_warehouse_connection(effective_session_id)

        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: Failed to list schemas: {error_msg}"

    return result.output if result.output else "(no output)"


@mcp.tool()
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

    result = await kernel_manager.execute(code, timeout=60.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        if _is_connection_error(error_msg) or (
            result.output and _is_connection_error(result.output)
        ):
            _clear_warehouse_connection(effective_session_id)

        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: Failed to list tables: {error_msg}"

    return result.output if result.output else "(no output)"


@mcp.tool()
async def get_tables_info(
    database: str,
    schema: str,
    tables: list[str],
    session_id: str | None = None,
) -> str:
    """Get detailed information about multiple tables including columns, data types, and descriptions.

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

    result = await kernel_manager.execute(code, timeout=60.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        if _is_connection_error(error_msg) or (
            result.output and _is_connection_error(result.output)
        ):
            _clear_warehouse_connection(effective_session_id)

        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: Failed to get tables info: {error_msg}"

    return result.output if result.output else "(no output)"


@mcp.tool()
async def list_query_results(
    session_id: str | None = None,
) -> str:
    """List all saved SQL query results from the current session.

    Shows query numbers, row counts, and query previews.
    Calling this tool repeatedly will return the same results.

    Args:
        session_id: Optional session identifier for state isolation

    Returns:
        List of saved query results, or message if none
    """
    kernel_manager = get_kernel_manager()

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Get session data directory
    session_data_dir = get_session_data_dir(effective_session_id)

    # Render and execute the script
    code = render_list_query_results(str(session_data_dir))

    result = await kernel_manager.execute(code, timeout=30.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: Failed to list query results: {error_msg}"

    return result.output if result.output else "No query results saved yet."


@mcp.tool()
async def get_query_result(
    query_num: int,
    session_id: str | None = None,
) -> str:
    """Load a previously saved SQL query result from a parquet file.

    Use list_query_results first to see available results.

    Args:
        query_num: The query number to load (e.g., 1 for query_001.parquet)
        session_id: Optional session identifier for state isolation

    Returns:
        Query result data, or error message
    """
    kernel_manager = get_kernel_manager()

    if query_num < 1:
        return "Error: query_num must be at least 1"

    # Set session
    effective_session_id = session_id or "default"
    await kernel_manager.set_session(effective_session_id)

    # Get session data directory
    session_data_dir = get_session_data_dir(effective_session_id)

    # Render and execute the script
    code = render_load_query_result(str(session_data_dir), query_num)

    result = await kernel_manager.execute(code, timeout=30.0)

    if not result.success:
        error_msg = result.error or "Unknown error"
        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error: Failed to load query result: {error_msg}"

    return result.output if result.output else "(no output)"


def main() -> None:
    """Entry point for the Jupyter kernel MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
