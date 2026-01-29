"""PostgreSQL connector using psycopg."""

from dataclasses import dataclass, field
from typing import Any

from . import register_connector
from .base import DatabaseConnector


@register_connector
@dataclass
class PostgresConnector(DatabaseConnector):
    host: str = ""
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""
    sslmode: str = ""
    databases: list[str] = field(default_factory=list)
    password_env_var: str | None = None

    @classmethod
    def connector_type(cls) -> str:
        return "postgres"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PostgresConnector":
        from .utils import substitute_env_vars

        host, _ = substitute_env_vars(data.get("host", ""))
        user, _ = substitute_env_vars(data.get("user", ""))
        password, pw_env = substitute_env_vars(data.get("password", ""))
        database, _ = substitute_env_vars(data.get("database", ""))

        return cls(
            host=host,
            port=data.get("port", 5432),
            user=user,
            password=password,
            database=database,
            sslmode=data.get("sslmode", ""),
            databases=data.get("databases", [database] if database else []),
            password_env_var=pw_env,
        )

    def validate(self, name: str) -> None:
        if not self.host or self.host.startswith("${"):
            raise ValueError(f"warehouse '{name}': host required for postgres")
        if not self.user or self.user.startswith("${"):
            raise ValueError(f"warehouse '{name}': user required for postgres")
        if not self.database or self.database.startswith("${"):
            raise ValueError(f"warehouse '{name}': database required for postgres")

    def get_required_packages(self) -> list[str]:
        return ["psycopg[binary,pool]"]

    def get_env_vars_for_kernel(self) -> dict[str, str]:
        env_vars = {}
        if self.password_env_var and self.password:
            env_vars[self.password_env_var] = self.password
        return env_vars

    def to_python_prelude(self) -> str:
        lines = ["_conn = psycopg.connect("]
        lines.append(f"    host={self.host!r},")
        lines.append(f"    port={self.port},")
        lines.append(f"    user={self.user!r},")
        if self.password_env_var:
            lines.append(f"    password=os.environ.get({self.password_env_var!r}),")
        elif self.password:
            lines.append(f"    password={self.password!r},")
        lines.append(f"    dbname={self.database!r},")
        if self.sslmode:
            lines.append(f"    sslmode={self.sslmode!r},")
        lines.append("    autocommit=True,")
        lines.append(")")
        connection_code = "\n".join(lines)

        status_lines = [
            'print("PostgreSQL connection established")',
            f'print("   Host: {self.host}:{self.port}")',
            f'print("   User: {self.user}")',
            f'print("   Database: {self.database}")',
            'print("\\nAvailable: run_sql(query) -> polars, run_sql_pandas(query) -> pandas")',
        ]
        status_code = "\n".join(status_lines)

        return f'''import psycopg
import polars as pl
import pandas as pd
import os

{connection_code}

def run_sql(query: str, limit: int = 100):
    """Execute SQL and return Polars DataFrame."""
    with _conn.cursor() as cursor:
        cursor.execute(query)
        if cursor.description is None:
            return pl.DataFrame()
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        result = pl.DataFrame(rows, schema=columns, orient="row")
        return result.head(limit) if limit > 0 and len(result) > limit else result


def run_sql_pandas(query: str, limit: int = 100):
    """Execute SQL and return Pandas DataFrame."""
    with _conn.cursor() as cursor:
        cursor.execute(query)
        if cursor.description is None:
            return pd.DataFrame()
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        return df.head(limit) if limit > 0 and len(df) > limit else df

{status_code}'''
