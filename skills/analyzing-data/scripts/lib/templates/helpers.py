# ruff: noqa: F821
"""SQL helper functions for the Jupyter kernel.

This code is injected directly into the kernel after the connection is established.
The _conn, pl, and pd variables are defined in the kernel before this runs.
"""


def run_sql(query: str, limit: int = 100):
    """Execute SQL and return Polars DataFrame."""
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
        return result.head(limit) if limit > 0 and len(result) > limit else result
    finally:
        cursor.close()


def run_sql_pandas(query: str, limit: int = 100):
    """Execute SQL and return Pandas DataFrame."""
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
        return df.head(limit) if limit > 0 and len(df) > limit else df
    finally:
        cursor.close()
