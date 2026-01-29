"""SQLAlchemy connector for any SQLAlchemy-compatible database."""

import re
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from . import register_connector
from .base import DatabaseConnector


class DialectInfo(NamedTuple):
    """Database dialect configuration.

    To add a new database:
    1. Add an entry to DIALECTS below with (display_name, [packages])
    2. Run tests: uv run pytest tests/test_connectors.py -v
    """

    display_name: str
    packages: list[str]


# Mapping of dialect/driver names to their configuration.
# The dialect is extracted from URLs like "dialect+driver://..." or "dialect://..."
# When a driver is specified (e.g., mysql+pymysql), the driver name is looked up first.
DIALECTS: dict[str, DialectInfo] = {
    # PostgreSQL variants
    "postgresql": DialectInfo("PostgreSQL", ["psycopg[binary]"]),
    "postgres": DialectInfo("PostgreSQL", ["psycopg[binary]"]),
    "psycopg": DialectInfo("PostgreSQL", ["psycopg[binary]"]),
    "psycopg2": DialectInfo("PostgreSQL", ["psycopg2-binary"]),
    "pg8000": DialectInfo("PostgreSQL", ["pg8000"]),
    "asyncpg": DialectInfo("PostgreSQL", ["asyncpg"]),
    # MySQL variants
    "mysql": DialectInfo("MySQL", ["pymysql"]),
    "pymysql": DialectInfo("MySQL", ["pymysql"]),
    "mysqlconnector": DialectInfo("MySQL", ["mysql-connector-python"]),
    "mysqldb": DialectInfo("MySQL", ["mysqlclient"]),
    "mariadb": DialectInfo("MariaDB", ["mariadb"]),
    # SQLite (built-in, no extra packages)
    "sqlite": DialectInfo("SQLite", []),
    # Oracle
    "oracle": DialectInfo("Oracle", ["oracledb"]),
    "oracledb": DialectInfo("Oracle", ["oracledb"]),
    # SQL Server
    "mssql": DialectInfo("SQL Server", ["pyodbc"]),
    "pyodbc": DialectInfo("SQL Server", ["pyodbc"]),
    "pymssql": DialectInfo("SQL Server", ["pymssql"]),
    # Cloud data warehouses
    "redshift": DialectInfo("Redshift", ["redshift_connector"]),
    "redshift_connector": DialectInfo("Redshift", ["redshift_connector"]),
    "snowflake": DialectInfo(
        "Snowflake", ["snowflake-sqlalchemy", "snowflake-connector-python"]
    ),
    "bigquery": DialectInfo("BigQuery", ["sqlalchemy-bigquery"]),
    # DuckDB
    "duckdb": DialectInfo("DuckDB", ["duckdb", "duckdb-engine"]),
    # Other databases
    "trino": DialectInfo("Trino", ["trino"]),
    "clickhouse": DialectInfo(
        "ClickHouse", ["clickhouse-driver", "clickhouse-sqlalchemy"]
    ),
    "cockroachdb": DialectInfo(
        "CockroachDB", ["sqlalchemy-cockroachdb", "psycopg[binary]"]
    ),
    "databricks": DialectInfo("Databricks", ["databricks-sql-connector"]),
    "teradata": DialectInfo("Teradata", ["teradatasqlalchemy"]),
    "vertica": DialectInfo("Vertica", ["vertica-python"]),
    "hana": DialectInfo("SAP HANA", ["hdbcli"]),
    "db2": DialectInfo("IBM Db2", ["ibm_db_sa"]),
    "firebird": DialectInfo("Firebird", ["fdb"]),
    "awsathena": DialectInfo("Amazon Athena", ["pyathena"]),
    "spanner": DialectInfo("Cloud Spanner", ["sqlalchemy-spanner"]),
}


def _extract_dialect(url: str) -> str | None:
    """Extract dialect name from SQLAlchemy URL.

    URLs can be:
    - dialect://user:pass@host/db
    - dialect+driver://user:pass@host/db

    When a driver is specified, returns the driver name (looked up first in DIALECTS).
    Falls back to dialect name if driver isn't in DIALECTS.
    """
    match = re.match(r"^([a-zA-Z0-9_-]+)(?:\+([a-zA-Z0-9_-]+))?://", url)
    if match:
        dialect = match.group(1).lower()
        driver = match.group(2).lower() if match.group(2) else None
        # Prefer driver if specified AND it's in our dialects mapping
        # Otherwise fall back to dialect (e.g., postgresql+asyncpg -> asyncpg if known)
        if driver and driver in DIALECTS:
            return driver
        return dialect
    return None


@register_connector
@dataclass
class SQLAlchemyConnector(DatabaseConnector):
    url: str = ""
    databases: list[str] = field(default_factory=list)
    pool_size: int = 5
    echo: bool = False
    url_env_var: str | None = None

    @classmethod
    def connector_type(cls) -> str:
        return "sqlalchemy"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SQLAlchemyConnector":
        from .utils import substitute_env_vars

        url, url_env = substitute_env_vars(data.get("url", ""))

        return cls(
            url=url,
            databases=data.get("databases", []),
            pool_size=data.get("pool_size", 5),
            echo=data.get("echo", False),
            url_env_var=url_env,
        )

    def validate(self, name: str) -> None:
        if not self.url or self.url.startswith("${"):
            raise ValueError(f"warehouse '{name}': url required for sqlalchemy")
        if not self.databases:
            raise ValueError(
                f"warehouse '{name}': databases list required for sqlalchemy"
            )

    def get_required_packages(self) -> list[str]:
        packages = ["sqlalchemy"]
        dialect = _extract_dialect(self.url)
        if dialect and dialect in DIALECTS:
            packages.extend(DIALECTS[dialect].packages)
        return packages

    def get_env_vars_for_kernel(self) -> dict[str, str]:
        env_vars = {}
        if self.url_env_var and self.url:
            env_vars[self.url_env_var] = self.url
        return env_vars

    def to_python_prelude(self) -> str:
        if self.url_env_var:
            url_code = f"os.environ.get({self.url_env_var!r})"
        else:
            url_code = repr(self.url)

        # Infer DB type for status message
        dialect = _extract_dialect(self.url)
        db_type = (
            DIALECTS[dialect].display_name
            if dialect and dialect in DIALECTS
            else "Database"
        )

        databases_str = ", ".join(self.databases)

        return f'''from sqlalchemy import create_engine, text
import polars as pl
import pandas as pd
import os
import atexit

_engine = create_engine({url_code}, pool_size={self.pool_size}, echo={self.echo})
_conn = _engine.connect()
atexit.register(lambda: (_conn.close(), _engine.dispose()))

def run_sql(query: str, limit: int = 100):
    """Execute SQL and return Polars DataFrame."""
    result = _conn.execute(text(query))
    if result.returns_rows:
        columns = list(result.keys())
        rows = result.fetchall()
        df = pl.DataFrame(rows, schema=columns, orient="row")
        return df.head(limit) if limit > 0 and len(df) > limit else df
    return pl.DataFrame()


def run_sql_pandas(query: str, limit: int = 100):
    """Execute SQL and return Pandas DataFrame."""
    result = _conn.execute(text(query))
    if result.returns_rows:
        columns = list(result.keys())
        rows = result.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        return df.head(limit) if limit > 0 and len(df) > limit else df
    return pd.DataFrame()

print("{db_type} connection established (via SQLAlchemy)")
print(f"   Database(s): {databases_str}")
print("\\nAvailable: run_sql(query) -> polars, run_sql_pandas(query) -> pandas")'''
