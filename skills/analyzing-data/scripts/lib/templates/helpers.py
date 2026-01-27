# ruff: noqa: F821
"""SQL helper functions for the Jupyter kernel.

This code is injected directly into the kernel after the connection is established.
The _conn, pl, pd, and sqlglot variables are defined in the kernel before this runs.
"""


# --- SQL Safety Functions (injected into kernel) ---

def _check_sql_safety(query: str) -> tuple[bool, list[str]]:
    """Check if SQL query contains dangerous operations."""
    from sqlglot import exp

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
        parsed_statements = sqlglot.parse(query, dialect="snowflake")
        detected_operations = []

        for statement in parsed_statements:
            if statement is None:
                continue

            for danger_class, operation_name in dangerous_types.items():
                if isinstance(statement, danger_class):
                    if operation_name not in detected_operations:
                        detected_operations.append(operation_name)
                nested_operations = list(statement.find_all(danger_class))
                if nested_operations and operation_name not in detected_operations:
                    detected_operations.append(operation_name)

        return (len(detected_operations) == 0, detected_operations)
    except Exception as e:
        return (False, [f"PARSE_ERROR: {str(e)}"])


def _is_select_only(query: str) -> bool:
    """Check if query contains only SELECT statements."""
    from sqlglot import exp

    try:
        parsed_statements = sqlglot.parse(query, dialect="snowflake")

        for statement in parsed_statements:
            if statement is None:
                continue

            if not isinstance(statement, exp.Select):
                if isinstance(statement, exp.With):
                    main_query = statement.this
                    if not isinstance(main_query, exp.Select):
                        return False
                    for cte in statement.expressions:
                        if hasattr(cte, "this") and not isinstance(cte.this, exp.Select):
                            return False
                else:
                    return False
        return True
    except Exception:
        return False


def _has_limit(query: str) -> bool:
    """Check if query already has a LIMIT clause."""
    from sqlglot import exp

    try:
        parsed_statements = sqlglot.parse(query, dialect="snowflake")
        for statement in parsed_statements:
            if statement is None:
                continue
            if isinstance(statement, (exp.Select, exp.With)):
                if statement.find(exp.Limit) is not None:
                    return True
        return False
    except Exception:
        return "LIMIT" in query.upper()


def _inject_limit(query: str, limit: int) -> str:
    """Inject LIMIT clause into SELECT query if not present."""
    if _has_limit(query):
        return query
    if not _is_select_only(query):
        return query
    query = query.rstrip().rstrip(";")
    return f"{query} LIMIT {limit}"


# --- Main SQL Execution Functions ---

def run_sql(query: str, limit: int = 100):
    """Execute SQL and return Polars DataFrame.

    Safety features:
    - Blocks dangerous DDL/DML operations (CREATE, DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE)
    - Automatically injects LIMIT clause for SELECT queries without one

    Use run_sql_unsafe() to bypass safety checks for intentional DDL/DML.
    """
    # Safety check
    is_safe, operations = _check_sql_safety(query)
    if not is_safe:
        raise ValueError(
            f"Blocked dangerous operation(s): {', '.join(operations)}. "
            f"Use run_sql_unsafe() if this is intentional."
        )

    # Inject LIMIT at SQL level for efficiency
    query = _inject_limit(query, limit)

    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        try:
            df = cursor.fetch_pandas_all()
            result = pl.from_pandas(df)
        except Exception:
            rows = cursor.fetchall()
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            result = pl.DataFrame(rows, schema=columns, orient="row")
        return result
    finally:
        cursor.close()


def run_sql_pandas(query: str, limit: int = 100):
    """Execute SQL and return Pandas DataFrame.

    Safety features:
    - Blocks dangerous DDL/DML operations (CREATE, DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE)
    - Automatically injects LIMIT clause for SELECT queries without one

    Use run_sql_pandas_unsafe() to bypass safety checks for intentional DDL/DML.
    """
    # Safety check
    is_safe, operations = _check_sql_safety(query)
    if not is_safe:
        raise ValueError(
            f"Blocked dangerous operation(s): {', '.join(operations)}. "
            f"Use run_sql_pandas_unsafe() if this is intentional."
        )

    # Inject LIMIT at SQL level for efficiency
    query = _inject_limit(query, limit)

    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        try:
            df = cursor.fetch_pandas_all()
        except Exception:
            rows = cursor.fetchall()
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            df = pd.DataFrame(rows, columns=columns)
        return df
    finally:
        cursor.close()


def run_sql_unsafe(query: str, limit: int = 0):
    """Execute SQL without safety checks. Use for intentional DDL/DML operations.

    WARNING: This bypasses all safety checks. Use with caution.

    Args:
        query: SQL query (including DDL/DML)
        limit: Max rows to return (0 = no limit, default for DDL/DML)
    """
    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        try:
            df = cursor.fetch_pandas_all()
            result = pl.from_pandas(df)
        except Exception:
            rows = cursor.fetchall()
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            if not columns:
                # DDL/DML returns no columns
                return pl.DataFrame({"status": ["Query executed successfully"]})
            result = pl.DataFrame(rows, schema=columns, orient="row")
        return result.head(limit) if limit > 0 and len(result) > limit else result
    finally:
        cursor.close()


def run_sql_pandas_unsafe(query: str, limit: int = 0):
    """Execute SQL without safety checks. Use for intentional DDL/DML operations.

    WARNING: This bypasses all safety checks. Use with caution.

    Args:
        query: SQL query (including DDL/DML)
        limit: Max rows to return (0 = no limit, default for DDL/DML)
    """
    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        try:
            df = cursor.fetch_pandas_all()
        except Exception:
            rows = cursor.fetchall()
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            if not columns:
                # DDL/DML returns no columns
                return pd.DataFrame({"status": ["Query executed successfully"]})
            df = pd.DataFrame(rows, columns=columns)
        return df.head(limit) if limit > 0 and len(df) > limit else df
    finally:
        cursor.close()
