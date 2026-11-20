"""Template code injected into Jupyter kernels.

Contains SQL helper functions and private key loaders for Snowflake auth.
"""

from string import Template

# --- SQL Helpers (injected into kernel after connection) ---

# ruff: noqa: F821
HELPERS_CODE = '''\
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


def run_sql_many(queries, limit: int = 100):
    """Run independent queries concurrently, returning one Polars DataFrame per
    query in input order. Submits all via Snowflake async execution so the
    warehouse runs them in parallel instead of one-at-a-time.

    Fail-fast: raises on the first failing query; the results of sibling queries
    are discarded. Queries already submitted to the warehouse are not cancelled
    and may keep running server-side (same caveat as a single run_sql timeout)."""
    cursors = []
    try:
        for q in queries:
            cur = _conn.cursor()
            cursors.append(cur)  # track before submit so a failure can't leak it
            cur.execute_async(q)
        results = []
        for cur in cursors:
            cur.get_results_from_sfqid(cur.sfqid)  # blocks until this one finishes
            try:
                result = pl.from_pandas(cur.fetch_pandas_all())
            except Exception:
                rows = cur.fetchall()
                columns = (
                    [desc[0] for desc in cur.description] if cur.description else []
                )
                result = pl.DataFrame(rows, schema=columns, orient="row")
            results.append(
                result.head(limit) if limit > 0 and len(result) > limit else result
            )
        return results
    finally:
        # Close every cursor we opened, even if submission/collection failed partway.
        for cur in cursors:
            try:
                cur.close()
            except Exception:
                pass
'''

# --- Private Key Templates (for Snowflake auth) ---

PRIVATE_KEY_CONTENT_TEMPLATE = Template(
    """
def _load_private_key():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    key_content = $KEY_CODE
    p_key = serialization.load_pem_private_key(
        key_content.encode(), password=$PASSPHRASE_CODE, backend=default_backend()
    )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
"""
)

PRIVATE_KEY_FILE_TEMPLATE = Template(
    """
def _load_private_key():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from pathlib import Path

    with open(Path($KEY_PATH).expanduser(), "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=$PASSPHRASE_CODE, backend=default_backend()
        )
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
"""
)
