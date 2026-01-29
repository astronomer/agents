"""Snowflake connector using snowflake-connector-python."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import register_connector
from .base import DatabaseConnector

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


@register_connector
@dataclass
class SnowflakeConnector(DatabaseConnector):
    account: str = ""
    user: str = ""
    auth_type: str = "password"
    password: str = ""
    private_key_path: str = ""
    private_key_passphrase: str = ""
    private_key: str = ""
    warehouse: str = ""
    role: str = ""
    schema: str = ""
    databases: list[str] = field(default_factory=list)
    client_session_keep_alive: bool = False
    password_env_var: str | None = None
    private_key_env_var: str | None = None
    private_key_passphrase_env_var: str | None = None

    @classmethod
    def connector_type(cls) -> str:
        return "snowflake"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SnowflakeConnector":
        from .utils import substitute_env_vars

        account, _ = substitute_env_vars(data.get("account", ""))
        user, _ = substitute_env_vars(data.get("user", ""))
        password, pw_env = substitute_env_vars(data.get("password", ""))
        private_key, pk_env = substitute_env_vars(data.get("private_key", ""))
        passphrase, pp_env = substitute_env_vars(data.get("private_key_passphrase", ""))

        return cls(
            account=account,
            user=user,
            auth_type=data.get("auth_type", "password"),
            password=password,
            private_key_path=data.get("private_key_path", ""),
            private_key_passphrase=passphrase,
            private_key=private_key,
            warehouse=data.get("warehouse", ""),
            role=data.get("role", ""),
            schema=data.get("schema", ""),
            databases=data.get("databases", []),
            client_session_keep_alive=data.get("client_session_keep_alive", False),
            password_env_var=pw_env,
            private_key_env_var=pk_env,
            private_key_passphrase_env_var=pp_env,
        )

    def validate(self, name: str) -> None:
        if not self.account or self.account.startswith("${"):
            raise ValueError(f"warehouse '{name}': account required")
        if not self.user or self.user.startswith("${"):
            raise ValueError(f"warehouse '{name}': user required")
        if self.auth_type == "password":
            if not self.password or self.password.startswith("${"):
                raise ValueError(f"warehouse '{name}': password required")
        elif self.auth_type == "private_key":
            if not self.private_key_path and not self.private_key:
                raise ValueError(f"warehouse '{name}': private_key required")

    def get_required_packages(self) -> list[str]:
        pkgs = ["snowflake-connector-python[pandas]"]
        if self.auth_type == "private_key":
            pkgs.append("cryptography")
        return pkgs

    def get_env_vars_for_kernel(self) -> dict[str, str]:
        env_vars = {}
        if self.password_env_var and self.password:
            env_vars[self.password_env_var] = self.password
        if self.private_key_env_var and self.private_key:
            env_vars[self.private_key_env_var] = self.private_key
        if self.private_key_passphrase_env_var and self.private_key_passphrase:
            env_vars[self.private_key_passphrase_env_var] = self.private_key_passphrase
        return env_vars

    def to_python_prelude(self) -> str:
        sections = []

        # Imports
        sections.append("""import snowflake.connector
import polars as pl
import pandas as pd
import os""")

        # Private key loader (if needed)
        if self.auth_type == "private_key":
            from ..templates.private_key_content import TEMPLATE as CONTENT_TEMPLATE
            from ..templates.private_key_file import TEMPLATE as FILE_TEMPLATE

            if self.private_key_passphrase_env_var:
                passphrase_code = f"os.environ.get({self.private_key_passphrase_env_var!r}, '').encode() or None"
            elif self.private_key_passphrase:
                passphrase_code = f"{self.private_key_passphrase!r}.encode()"
            else:
                passphrase_code = "None"

            if self.private_key_path:
                sections.append(
                    FILE_TEMPLATE.substitute(
                        KEY_PATH=repr(self.private_key_path),
                        PASSPHRASE_CODE=passphrase_code,
                    )
                )
            else:
                key_code = (
                    f"os.environ.get({self.private_key_env_var!r})"
                    if self.private_key_env_var
                    else repr(self.private_key)
                )
                sections.append(
                    CONTENT_TEMPLATE.substitute(
                        KEY_CODE=key_code,
                        PASSPHRASE_CODE=passphrase_code,
                    )
                )

        # Connection
        lines = ["_conn = snowflake.connector.connect("]
        lines.append(f"    account={self.account!r},")
        lines.append(f"    user={self.user!r},")
        if self.auth_type == "password":
            if self.password_env_var:
                lines.append(f"    password=os.environ.get({self.password_env_var!r}),")
            else:
                lines.append(f"    password={self.password!r},")
        elif self.auth_type == "private_key":
            lines.append("    private_key=_load_private_key(),")
        if self.warehouse:
            lines.append(f"    warehouse={self.warehouse!r},")
        if self.role:
            lines.append(f"    role={self.role!r},")
        if self.databases:
            lines.append(f"    database={self.databases[0]!r},")
        lines.append(f"    client_session_keep_alive={self.client_session_keep_alive},")
        lines.append(")")
        sections.append("\n".join(lines))

        # Helper functions (from template)
        helpers_code = (TEMPLATES_DIR / "helpers.py").read_text()
        if "def " in helpers_code:
            helpers_code = "def " + helpers_code.split("def ", 1)[1]
        sections.append(helpers_code.strip())

        # Status output
        status_lines = [
            'print("Snowflake connection established")',
            'print(f"   Account: {_conn.account}")',
            'print(f"   User: {_conn.user}")',
        ]
        if self.warehouse:
            status_lines.append(f'print(f"   Warehouse: {self.warehouse}")')
        if self.role:
            status_lines.append(f'print(f"   Role: {self.role}")')
        if self.databases:
            status_lines.append(f'print(f"   Database: {self.databases[0]}")')
        status_lines.append(
            'print("\\nAvailable: run_sql(query) -> polars, run_sql_pandas(query) -> pandas")'
        )
        sections.append("\n".join(status_lines))

        return "\n\n".join(sections)
