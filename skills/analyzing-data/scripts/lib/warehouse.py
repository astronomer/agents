"""Warehouse configuration and Snowflake connection prelude generation."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .config import get_config_dir

# Template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


def get_warehouse_config_path() -> Path:
    return get_config_dir() / "warehouse.yml"


def _load_env_file() -> None:
    env_path = get_config_dir() / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    if Path(".env").exists():
        load_dotenv(".env", override=True)


def _substitute_env_vars(value: str) -> tuple[str, str | None]:
    if not isinstance(value, str):
        return value, None
    match = re.match(r"^\$\{([^}]+)\}$", value)
    if match:
        env_var_name = match.group(1)
        env_value = os.environ.get(env_var_name)
        return (env_value if env_value else value), env_var_name
    return value, None


def _load_template(name: str) -> str:
    """Load a template file from the templates directory."""
    return (TEMPLATES_DIR / name).read_text()


@dataclass
class SnowflakeConfig:
    account: str
    user: str
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
    def from_dict(cls, data: dict[str, Any]) -> "SnowflakeConfig":
        account, _ = _substitute_env_vars(data.get("account", ""))
        user, _ = _substitute_env_vars(data.get("user", ""))
        password, pw_env = _substitute_env_vars(data.get("password", ""))
        private_key, pk_env = _substitute_env_vars(data.get("private_key", ""))
        passphrase, pp_env = _substitute_env_vars(
            data.get("private_key_passphrase", "")
        )

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
        pkgs = ["snowflake-connector-python[pandas]", "sqlglot"]
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

    def _get_passphrase_code(self) -> str:
        """Get code snippet for passphrase handling."""
        if self.private_key_passphrase_env_var:
            return f"os.environ.get({self.private_key_passphrase_env_var!r}, '').encode() or None"
        elif self.private_key_passphrase:
            return f"{self.private_key_passphrase!r}.encode()"
        return "None"

    def _generate_private_key_loader(self) -> str:
        """Generate the _load_private_key() function code."""
        from .templates.private_key_file import TEMPLATE as FILE_TEMPLATE
        from .templates.private_key_content import TEMPLATE as CONTENT_TEMPLATE

        passphrase_code = self._get_passphrase_code()

        if self.private_key_path:
            return FILE_TEMPLATE.substitute(
                KEY_PATH=repr(self.private_key_path),
                PASSPHRASE_CODE=passphrase_code,
            )
        else:
            if self.private_key_env_var:
                key_code = f"os.environ.get({self.private_key_env_var!r})"
            else:
                key_code = repr(self.private_key)
            return CONTENT_TEMPLATE.substitute(
                KEY_CODE=key_code,
                PASSPHRASE_CODE=passphrase_code,
            )

    def _generate_connection_code(self) -> str:
        """Generate the Snowflake connection code."""
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

        return "\n".join(lines)

    def _generate_status_output(self) -> str:
        """Generate the connection status print statements."""
        lines = [
            'print("Snowflake connection established")',
            'print(f"   Account: {_conn.account}")',
            'print(f"   User: {_conn.user}")',
        ]
        if self.warehouse:
            lines.append(f'print(f"   Warehouse: {self.warehouse}")')
        if self.role:
            lines.append(f'print(f"   Role: {self.role}")')
        if self.databases:
            lines.append(f'print(f"   Database: {self.databases[0]}")')
        lines.append(
            'print("\\nAvailable functions:")'
        )
        lines.append(
            'print("  run_sql(query, limit=100) -> Polars (safe, auto-LIMIT)")'
        )
        lines.append(
            'print("  run_sql_pandas(query, limit=100) -> Pandas (safe, auto-LIMIT)")'
        )
        lines.append(
            'print("  run_sql_unsafe(query) -> Polars (bypasses safety for DDL/DML)")'
        )
        lines.append(
            'print("  run_sql_pandas_unsafe(query) -> Pandas (bypasses safety for DDL/DML)")'
        )
        return "\n".join(lines)

    def to_python_prelude(self) -> str:
        """Generate the complete Python prelude for the kernel."""
        sections = []

        # 1. Imports
        sections.append(
            """import snowflake.connector
import polars as pl
import pandas as pd
import os
import sqlglot"""
        )

        # 2. Private key loader (if needed)
        if self.auth_type == "private_key":
            sections.append(self._generate_private_key_loader())

        # 3. Connection
        sections.append(self._generate_connection_code())

        # 4. Helper functions (from template file)
        helpers_code = _load_template("helpers.py")
        # Strip the module docstring (everything before first 'def')
        if "def " in helpers_code:
            helpers_code = "def " + helpers_code.split("def ", 1)[1]
        sections.append(helpers_code.strip())

        # 5. Status output
        sections.append(self._generate_status_output())

        return "\n\n".join(sections)


@dataclass
class WarehouseConfig:
    connectors: dict[str, SnowflakeConfig] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "WarehouseConfig":
        _load_env_file()
        if path is None:
            path = get_warehouse_config_path()
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {path}")
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data:
            raise ValueError(f"No configs in {path}")
        connectors = {}
        for name, config in data.items():
            if config.get("type") == "snowflake":
                conn = SnowflakeConfig.from_dict(config)
                conn.validate(name)
                connectors[name] = conn
        return cls(connectors=connectors)

    def get_default(self) -> tuple[str, SnowflakeConfig]:
        if not self.connectors:
            raise ValueError("No warehouse configs")
        name = next(iter(self.connectors))
        return name, self.connectors[name]
