"""Warehouse configuration loading and connection prelude generation.

This module handles loading warehouse configuration from ~/.astro/ai/config/warehouse.yml
and generating Python prelude code for establishing database connections.

Mirrors functionality from ai-cli/agent/clients/warehouse/.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def get_config_dir() -> Path:
    """Get the path to the config directory.

    Returns:
        Path to ~/.astro/ai/config/
    """
    return Path.home() / ".astro" / "ai" / "config"


def get_env_file_path() -> Path:
    """Get the path to the .env file.

    Returns:
        Path to ~/.astro/ai/config/.env
    """
    return get_config_dir() / ".env"


def get_warehouse_config_path() -> Path:
    """Get the path to the warehouse configuration file.

    Returns:
        Path to ~/.astro/ai/config/warehouse.yml
    """
    return get_config_dir() / "warehouse.yml"


def _load_env_file() -> None:
    """Load environment variables from the .env file if it exists."""
    env_path = get_env_file_path()
    if env_path.exists():
        load_dotenv(env_path)
    # Also try local .env for development
    if Path(".env").exists():
        load_dotenv(".env", override=True)


def _substitute_env_vars(value: str) -> tuple[str, str | None]:
    """Substitute environment variables in a config value.

    Supports ${VAR_NAME} syntax. Returns both the substituted value
    and the original env var name (for runtime lookups).

    If the environment variable is not set, the original ${VAR} pattern
    is preserved so validation can detect it.

    Args:
        value: Config value that may contain ${VAR_NAME}

    Returns:
        Tuple of (substituted_value, env_var_name or None)
    """
    if not isinstance(value, str):
        return value, None

    match = re.match(r"^\$\{([^}]+)\}$", value)
    if match:
        env_var_name = match.group(1)
        env_value = os.environ.get(env_var_name)
        if env_value is not None:
            return env_value, env_var_name
        # Keep original pattern if env var not found (for validation detection)
        return value, env_var_name
    return value, None


@dataclass
class SnowflakeConfig:
    """Snowflake warehouse connection configuration."""

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
    query_timeout: int = 0

    # Env var names for runtime lookups (and error messages)
    account_env_var: str | None = None
    user_env_var: str | None = None
    password_env_var: str | None = None
    private_key_env_var: str | None = None
    private_key_passphrase_env_var: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SnowflakeConfig":
        """Create a SnowflakeConfig from a dictionary.

        Args:
            data: Dictionary with config values (may contain ${ENV_VAR} syntax)

        Returns:
            SnowflakeConfig instance
        """
        # Extract env var names before substitution
        account, account_env = _substitute_env_vars(data.get("account", ""))
        user, user_env = _substitute_env_vars(data.get("user", ""))
        password, password_env = _substitute_env_vars(data.get("password", ""))
        private_key, pk_env = _substitute_env_vars(data.get("private_key", ""))
        passphrase, passphrase_env = _substitute_env_vars(
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
            query_timeout=data.get("query_timeout", 0),
            account_env_var=account_env,
            user_env_var=user_env,
            password_env_var=password_env,
            private_key_env_var=pk_env,
            private_key_passphrase_env_var=passphrase_env,
        )

    def validate(self, name: str) -> None:
        """Validate the configuration.

        Args:
            name: Name of the warehouse config (for error messages)

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.account or self.account.startswith("${"):
            env_hint = f" (set {self.account_env_var})" if self.account_env_var else ""
            raise ValueError(
                f"warehouse '{name}': account is required{env_hint}"
            )

        if not self.user or self.user.startswith("${"):
            env_hint = f" (set {self.user_env_var})" if self.user_env_var else ""
            raise ValueError(
                f"warehouse '{name}': user is required{env_hint}"
            )

        if self.auth_type == "password":
            if not self.password or self.password.startswith("${"):
                env_hint = f" (set {self.password_env_var})" if self.password_env_var else ""
                raise ValueError(
                    f"warehouse '{name}': password is required for password auth{env_hint}"
                )
        elif self.auth_type == "private_key":
            has_key_path = self.private_key_path and not self.private_key_path.startswith("${")
            has_key_content = self.private_key and not self.private_key.startswith("${")
            if not has_key_path and not has_key_content:
                env_hint = f" (set {self.private_key_env_var})" if self.private_key_env_var else ""
                raise ValueError(
                    f"warehouse '{name}': private_key_path or private_key is required "
                    f"for private key authentication{env_hint}"
                )
        else:
            raise ValueError(
                f"warehouse '{name}': unsupported auth_type '{self.auth_type}' "
                "(use 'password' or 'private_key')"
            )

    def required_packages(self) -> list[str]:
        """Return Python packages needed for Snowflake."""
        return ["snowflake-connector-python[pandas]", "polars", "pandas", "cryptography"]

    def get_env_vars_for_kernel(self) -> dict[str, str]:
        """Get environment variables that need to be injected into the kernel.

        Since the kernel runs in a separate process, it doesn't have access to
        the MCP server's environment variables. This method returns the env vars
        that the prelude code needs (e.g., for os.environ.get() calls).

        Returns:
            Dictionary of env var name -> value
        """
        env_vars = {}

        # Password (if using env var)
        if self.password_env_var and self.password:
            env_vars[self.password_env_var] = self.password

        # Private key content (if using env var)
        if self.private_key_env_var and self.private_key:
            env_vars[self.private_key_env_var] = self.private_key

        # Private key passphrase (if using env var)
        if self.private_key_passphrase_env_var and self.private_key_passphrase:
            env_vars[self.private_key_passphrase_env_var] = self.private_key_passphrase

        return env_vars

    def to_python_prelude(self) -> str:
        """Generate Python prelude code for establishing Snowflake connection.

        Returns:
            Python code string to execute in the kernel
        """
        lines = []

        # Imports
        lines.append("""import snowflake.connector
import polars as pl
import pandas as pd
from pathlib import Path
import os
""")

        # Private key helper functions (if needed)
        if self.auth_type == "private_key":
            if self.private_key_path:
                # Generate passphrase code
                if self.private_key_passphrase_env_var:
                    passphrase_code = f"os.environ.get({self.private_key_passphrase_env_var!r}, '').encode() or None"
                elif self.private_key_passphrase:
                    passphrase_code = f"{self.private_key_passphrase!r}.encode()"
                else:
                    passphrase_code = "None"

                lines.append(f"""def _load_private_key():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    
    key_path = Path({self.private_key_path!r}).expanduser()
    passphrase = {passphrase_code}
    
    with open(key_path, 'rb') as f:
        p_key = serialization.load_pem_private_key(
            f.read(),
            password=passphrase,
            backend=default_backend()
        )
    
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

""")
            else:
                # Generate passphrase code
                if self.private_key_passphrase_env_var:
                    passphrase_code = f"os.environ.get({self.private_key_passphrase_env_var!r}, '').encode() or None"
                elif self.private_key_passphrase:
                    passphrase_code = f"{self.private_key_passphrase!r}.encode()"
                else:
                    passphrase_code = "None"

                # Generate key content code
                if self.private_key_env_var:
                    key_content_code = f"os.environ.get({self.private_key_env_var!r})"
                else:
                    key_content_code = f"{self.private_key!r}"

                lines.append(f"""def _load_private_key_content():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    
    key_content = {key_content_code}
    passphrase = {passphrase_code}
    
    p_key = serialization.load_pem_private_key(
        key_content.encode(),
        password=passphrase,
        backend=default_backend()
    )
    
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

""")

        # Connection setup
        lines.append(self._to_python_connection_code())

        # Helper functions
        lines.append("""
def run_sql(query: str, limit: int = 100, return_df: bool = False) -> pl.DataFrame:
    \"\"\"Execute SQL query and return results as a Polars DataFrame.
    
    Args:
        query: SQL query to execute
        limit: Maximum rows to return (default: 100, use -1 for unlimited)
        return_df: If True, return DataFrame instead of printing (for parquet saving)
    
    Returns:
        Polars DataFrame with query results
    \"\"\"
    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        # Try fetch_pandas_all first (works for SELECT queries)
        # Fall back to fetchall for SHOW/DESCRIBE commands
        try:
            df = cursor.fetch_pandas_all()
            result = pl.from_pandas(df)
        except Exception:
            # Fallback for SHOW/DESCRIBE commands that don't support Arrow format
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            result = pl.DataFrame(rows, schema=columns, orient="row")
        if limit > 0 and len(result) > limit:
            result = result.head(limit)
        if return_df:
            return result
        return result
    finally:
        cursor.close()

def run_sql_pandas(query: str, limit: int = 100) -> pd.DataFrame:
    \"\"\"Execute SQL query and return results as a Pandas DataFrame.
    
    Args:
        query: SQL query to execute
        limit: Maximum rows to return (default: 100, use -1 for unlimited)
    
    Returns:
        Pandas DataFrame with query results
    \"\"\"
    cursor = _conn.cursor()
    try:
        cursor.execute(query)
        # Try fetch_pandas_all first, fall back to fetchall
        try:
            df = cursor.fetch_pandas_all()
        except Exception:
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            df = pd.DataFrame(rows, columns=columns)
        if limit > 0 and len(df) > limit:
            df = df.head(limit)
        return df
    finally:
        cursor.close()

print("✅ Snowflake connection established")
print(f"   Account: {_conn.account}")
print(f"   User: {_conn.user}")
""")

        if self.warehouse:
            lines.append(f'print(f"   Warehouse: {self.warehouse}")\n')
        if self.databases:
            lines.append(f'print(f"   Database: {self.databases[0]}")\n')

        lines.append("""print("\\nAvailable functions:")
print("  - run_sql(query, limit=100) -> pl.DataFrame")
print("  - run_sql_pandas(query, limit=100) -> pd.DataFrame")
""")

        return "".join(lines)

    def _to_python_connection_code(self) -> str:
        """Generate Python connection code."""
        lines = ["_conn = snowflake.connector.connect(\n"]
        lines.append(f"    account={self.account!r},\n")
        lines.append(f"    user={self.user!r},\n")

        if self.auth_type == "password":
            if self.password_env_var:
                lines.append(f"    password=os.environ.get({self.password_env_var!r}),\n")
            else:
                lines.append(f"    password={self.password!r},\n")
        elif self.auth_type == "private_key":
            if self.private_key_path:
                lines.append("    private_key=_load_private_key(),\n")
            else:
                lines.append("    private_key=_load_private_key_content(),\n")

        if self.warehouse:
            lines.append(f"    warehouse={self.warehouse!r},\n")
        if self.role:
            lines.append(f"    role={self.role!r},\n")
        if self.schema:
            lines.append(f"    schema={self.schema!r},\n")
        if self.databases:
            lines.append(f"    database={self.databases[0]!r},\n")

        lines.append(f"    client_session_keep_alive={self.client_session_keep_alive},\n")
        lines.append(")\n")

        return "".join(lines)


@dataclass
class WarehouseConfig:
    """Container for all warehouse configurations."""

    connectors: dict[str, SnowflakeConfig] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "WarehouseConfig":
        """Load warehouse configuration from YAML file.

        Args:
            path: Path to config file (defaults to ~/.astro/ai/config/warehouse.yml)

        Returns:
            WarehouseConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config is invalid
        """
        # Load .env file first so env vars are available for substitution
        _load_env_file()

        if path is None:
            path = get_warehouse_config_path()

        if not path.exists():
            raise FileNotFoundError(f"Warehouse config not found: {path}")

        with open(path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"No warehouse configurations found in {path}")

        connectors = {}
        for name, config in data.items():
            warehouse_type = config.get("type", "")
            if warehouse_type == "snowflake":
                connector = SnowflakeConfig.from_dict(config)
                connector.validate(name)
                connectors[name] = connector
            else:
                raise ValueError(f"Unsupported warehouse type: {warehouse_type}")

        if not connectors:
            raise ValueError(f"No valid warehouse configurations found in {path}")

        return cls(connectors=connectors)

    def get_default(self) -> tuple[str, SnowflakeConfig]:
        """Get the first/default warehouse connector.

        Returns:
            Tuple of (name, connector)

        Raises:
            ValueError: If no connectors configured
        """
        if not self.connectors:
            raise ValueError("No warehouse configurations found")
        name = next(iter(self.connectors))
        return name, self.connectors[name]

    def get(self, name: str) -> SnowflakeConfig:
        """Get a specific warehouse connector by name.

        Args:
            name: Warehouse name

        Returns:
            SnowflakeConfig

        Raises:
            KeyError: If warehouse not found
        """
        if name not in self.connectors:
            available = list(self.connectors.keys())
            raise KeyError(f"Warehouse '{name}' not found (available: {available})")
        return self.connectors[name]

