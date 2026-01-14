"""Script template rendering with parameter validation.

This module loads Python script templates from the scripts/ directory and renders
them with validated parameters. Mirrors functionality from ai-cli/agent/services/tools/scripts/.

Templates use Go template syntax ({{.Param}}) for compatibility with the ai-cli.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Directory containing the script templates
SCRIPTS_DIR = Path(__file__).parent / "scripts"

# SQL identifier validation regex - only allows alphanumeric and underscores
SQL_IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Maximum tables per request
MAX_TABLES_PER_REQUEST = 50


class ValidationError(Exception):
    """Raised when parameter validation fails."""

    pass


def validate_sql_identifier(name: str, identifier_type: str) -> None:
    """Validate that a string is a safe SQL identifier.

    Args:
        name: The identifier to validate
        identifier_type: Type of identifier (for error messages)

    Raises:
        ValidationError: If the identifier is invalid
    """
    if not name:
        raise ValidationError(f"{identifier_type} cannot be empty")
    if len(name) > 255:
        raise ValidationError(f"{identifier_type} too long (max 255 characters)")
    if not SQL_IDENTIFIER_REGEX.match(name):
        raise ValidationError(
            f"{identifier_type} '{name}' contains invalid characters "
            "(only alphanumeric and underscores allowed)"
        )


def _load_template(name: str) -> str:
    """Load a script template from the scripts directory.

    Args:
        name: Name of the script file (e.g., 'run_sql.py')

    Returns:
        Template content as string
    """
    script_path = SCRIPTS_DIR / name
    return script_path.read_text()


def _render_template(template: str, params: dict[str, str]) -> str:
    """Render a Go-style template with parameters.

    Args:
        template: Template string with {{.Param}} placeholders
        params: Dictionary of parameter values

    Returns:
        Rendered template string
    """
    result = template
    for key, value in params.items():
        result = result.replace(f"{{{{.{key}}}}}", str(value))
    return result


def render_run_sql(
    sql_file_path: str,
    limit: int,
    save_parquet: bool,
    query_num: int,
    session_data_dir: str,
) -> str:
    """Render the run_sql.py template.

    Args:
        sql_file_path: Path to the SQL file to read query from
        limit: Maximum rows to return
        save_parquet: Whether to save results as parquet
        query_num: Query number for file naming
        session_data_dir: Directory for session data

    Returns:
        Rendered Python code
    """
    # Escape backslashes for Python string literals
    escaped_sql_path = sql_file_path.replace("\\", "\\\\")
    escaped_session_dir = session_data_dir.replace("\\", "\\\\")

    template = _load_template("run_sql.py")
    return _render_template(
        template,
        {
            "SQLFilePath": escaped_sql_path,
            "Limit": str(limit),
            "SaveParquet": "True" if save_parquet else "False",
            "QueryNum": str(query_num),
            "SessionDataDir": escaped_session_dir,
        },
    )


def render_list_schemas_single_db(database: str) -> str:
    """Render the list_schemas_single_db.py template.

    Args:
        database: Database name to list schemas from

    Returns:
        Rendered Python code

    Raises:
        ValidationError: If database name is invalid
    """
    validate_sql_identifier(database, "database")

    template = _load_template("list_schemas_single_db.py")
    return _render_template(template, {"Database": database})


def render_list_schemas_configured(databases: list[str]) -> str:
    """Render the list_schemas_configured.py template.

    Args:
        databases: List of database names

    Returns:
        Rendered Python code

    Raises:
        ValidationError: If any database name is invalid
    """
    for db in databases:
        validate_sql_identifier(db, "database")

    # Build Python list literal
    db_list = "[" + ", ".join(f'"{db}"' for db in databases) + "]"

    template = _load_template("list_schemas_configured.py")
    return _render_template(template, {"DatabaseList": db_list})


def render_list_tables(database: str, schema: str) -> str:
    """Render the list_tables.py template.

    Args:
        database: Database name
        schema: Schema name

    Returns:
        Rendered Python code

    Raises:
        ValidationError: If identifiers are invalid
    """
    validate_sql_identifier(database, "database")
    validate_sql_identifier(schema, "schema")

    template = _load_template("list_tables.py")
    return _render_template(template, {"Database": database, "Schema": schema})


def render_get_tables_info(database: str, schema: str, tables: list[str]) -> str:
    """Render the get_tables_info.py template.

    Args:
        database: Database name
        schema: Schema name
        tables: List of table names

    Returns:
        Rendered Python code

    Raises:
        ValidationError: If identifiers are invalid or too many tables
    """
    validate_sql_identifier(database, "database")
    validate_sql_identifier(schema, "schema")

    if not tables:
        raise ValidationError("tables list cannot be empty")
    if len(tables) > MAX_TABLES_PER_REQUEST:
        raise ValidationError(
            f"too many tables requested ({len(tables)}), maximum is {MAX_TABLES_PER_REQUEST}"
        )

    for table in tables:
        validate_sql_identifier(table, "table")

    # Build Python list literal
    table_list = "[" + ", ".join(f'"{t}"' for t in tables) + "]"

    template = _load_template("get_tables_info.py")
    return _render_template(
        template,
        {
            "Database": database,
            "Schema": schema,
            "TableList": table_list,
        },
    )


def render_session_prelude(session_dir: str) -> str:
    """Render the session_prelude.py template.

    Args:
        session_dir: Path to the session directory

    Returns:
        Rendered Python code
    """
    # Escape backslashes for Python string literals
    escaped_dir = session_dir.replace("\\", "\\\\")

    template = _load_template("session_prelude.py")
    # session_prelude.py uses $session_dir (Python Template syntax)
    return template.replace("$session_dir", escaped_dir)
