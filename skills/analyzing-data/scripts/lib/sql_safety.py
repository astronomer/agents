"""SQL safety checker using proper SQL parsing.

Ported from kepler-cli to provide DDL/DML protection for the analyzing-data skill.
"""

import sqlglot
from sqlglot import exp


def check_sql_safety(query: str) -> tuple[bool, list[str]]:
    """Check if SQL query contains dangerous operations using proper SQL parsing.

    Args:
        query: SQL query string to check

    Returns:
        Tuple of (is_safe, detected_operations)
        - is_safe: True if query is safe to execute without confirmation
        - detected_operations: List of dangerous operation types found
    """
    # Map of SQLGlot expression types to operation names
    dangerous_types = {
        exp.Create: "CREATE",
        exp.Drop: "DROP",
        exp.Delete: "DELETE",
        exp.Update: "UPDATE",
        exp.Insert: "INSERT",
        exp.Alter: "ALTER",
        exp.TruncateTable: "TRUNCATE",
    }

    try:
        # Parse the SQL statement(s)
        parsed_statements = sqlglot.parse(query, dialect="snowflake")
        detected_operations = []

        for statement in parsed_statements:
            if statement is None:
                continue

            # Check if the main statement is dangerous
            for danger_class, operation_name in dangerous_types.items():
                if isinstance(statement, danger_class):
                    if operation_name not in detected_operations:
                        detected_operations.append(operation_name)

                # Also check for nested dangerous operations (e.g., in CTEs, subqueries)
                nested_operations = list(statement.find_all(danger_class))
                if nested_operations and operation_name not in detected_operations:
                    detected_operations.append(operation_name)

        is_safe = len(detected_operations) == 0
        return (is_safe, detected_operations)

    except Exception as e:
        # If parsing fails, be conservative and block the query
        return (False, [f"PARSE_ERROR: {str(e)}"])


def is_select_only(query: str) -> bool:
    """Check if query contains only SELECT statements (safe for auto-execution).

    Args:
        query: SQL query string to check

    Returns:
        True if query only contains SELECT statements
    """
    try:
        parsed_statements = sqlglot.parse(query, dialect="snowflake")

        for statement in parsed_statements:
            if statement is None:
                continue

            # Check if statement is SELECT or a CTE with only SELECTs
            if not isinstance(statement, exp.Select):
                # For CTEs, check if the main statement is SELECT
                if isinstance(statement, exp.With):
                    # The main query after WITH should be SELECT
                    main_query = statement.this
                    if not isinstance(main_query, exp.Select):
                        return False
                    # Check CTE expressions are also SELECT only
                    for cte in statement.expressions:
                        if hasattr(cte, "this") and not isinstance(cte.this, exp.Select):
                            return False
                else:
                    return False

        return True

    except Exception:
        # If parsing fails, assume not safe
        return False


def get_statement_type(query: str) -> str:
    """Get the primary statement type of a SQL query.

    Args:
        query: SQL query string

    Returns:
        String representing the statement type (SELECT, INSERT, etc.)
    """
    try:
        parsed_statements = sqlglot.parse(query, dialect="snowflake")

        if not parsed_statements or not parsed_statements[0]:
            return "UNKNOWN"

        statement = parsed_statements[0]

        if isinstance(statement, exp.Select):
            return "SELECT"
        elif isinstance(statement, exp.Insert):
            return "INSERT"
        elif isinstance(statement, exp.Update):
            return "UPDATE"
        elif isinstance(statement, exp.Delete):
            return "DELETE"
        elif isinstance(statement, exp.Create):
            return "CREATE"
        elif isinstance(statement, exp.Drop):
            return "DROP"
        elif isinstance(statement, exp.Alter):
            return "ALTER"
        elif isinstance(statement, exp.TruncateTable):
            return "TRUNCATE"
        elif isinstance(statement, exp.With):
            # For CTEs, check the main query type
            main_query = statement.this
            return get_statement_type(main_query.sql()) if main_query else "CTE"
        else:
            return type(statement).__name__.upper()

    except Exception:
        return "PARSE_ERROR"


def has_limit(query: str) -> bool:
    """Check if query already has a LIMIT clause.

    Args:
        query: SQL query string

    Returns:
        True if query has LIMIT clause
    """
    try:
        parsed_statements = sqlglot.parse(query, dialect="snowflake")

        for statement in parsed_statements:
            if statement is None:
                continue

            # Check for LIMIT in the statement
            if isinstance(statement, (exp.Select, exp.With)):
                # Find any Limit expression
                limit_expr = statement.find(exp.Limit)
                if limit_expr is not None:
                    return True

        return False

    except Exception:
        # Fallback to simple string check if parsing fails
        return "LIMIT" in query.upper()


def inject_limit(query: str, limit: int) -> str:
    """Inject LIMIT clause into a SELECT query if not already present.

    Args:
        query: SQL query string
        limit: Maximum rows to return

    Returns:
        Query with LIMIT clause added (or original if already has LIMIT)
    """
    if has_limit(query):
        return query

    # Only inject LIMIT for SELECT queries
    if not is_select_only(query):
        return query

    # Simple injection - add LIMIT at the end
    # Strip trailing semicolon if present
    query = query.rstrip().rstrip(";")
    return f"{query} LIMIT {limit}"
