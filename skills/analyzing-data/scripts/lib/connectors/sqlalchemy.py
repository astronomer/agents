"""SQLAlchemy connector for any SQLAlchemy-compatible database."""

from dataclasses import dataclass, field
from typing import Any

from . import register_connector
from .base import DatabaseConnector


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
        url_lower = self.url.lower()
        if "postgresql" in url_lower or "postgres" in url_lower:
            packages.append("psycopg[binary]")
        elif "mysql" in url_lower:
            packages.append(
                "pymysql"
                if "pymysql" in url_lower or "mysqlconnector" not in url_lower
                else "mysql-connector-python"
            )
        elif "duckdb" in url_lower:
            packages.extend(["duckdb", "duckdb-engine"])
        elif "mssql" in url_lower or "pyodbc" in url_lower:
            packages.append("pyodbc")
        elif "oracle" in url_lower:
            packages.append("oracledb")
        elif "redshift" in url_lower:
            packages.append("redshift_connector")
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
        url_lower = self.url.lower()
        if "postgresql" in url_lower or "postgres" in url_lower:
            db_type = "PostgreSQL"
        elif "mysql" in url_lower:
            db_type = "MySQL"
        elif "duckdb" in url_lower:
            db_type = "DuckDB"
        elif "sqlite" in url_lower:
            db_type = "SQLite"
        elif "mssql" in url_lower:
            db_type = "SQL Server"
        elif "oracle" in url_lower:
            db_type = "Oracle"
        elif "redshift" in url_lower:
            db_type = "Redshift"
        else:
            db_type = "Database"

        databases_str = ", ".join(self.databases)

        return f'''from sqlalchemy import create_engine, text
import polars as pl
import pandas as pd
import os

_engine = create_engine({url_code}, pool_size={self.pool_size}, echo={self.echo})
_conn = _engine.connect()

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
