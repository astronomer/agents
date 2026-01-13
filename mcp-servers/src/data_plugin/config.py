"""Shared configuration loading for data-plugin.

Config hierarchy:
- Base directory: ~/.astro (overridable with ASTRO_HOME)
- AI config directory: ~/.astro/ai/config/
- Warehouse config: ~/.astro/ai/config/warehouse.yml
- Environment secrets: ~/.astro/ai/config/.env
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# Path Configuration
# ==============================================================================


def get_base_dir() -> Path:
    """Get the base directory for Astro data.

    Can be overridden with ASTRO_HOME environment variable.
    Defaults to ~/.astro
    """
    if env_dir := os.environ.get("ASTRO_HOME"):
        return Path(env_dir)
    return Path.home() / ".astro"


def get_config_dir() -> Path:
    """Get the AI config directory (~/.astro/ai/config/)."""
    return get_base_dir() / "ai" / "config"


def get_kernel_venv_dir() -> Path:
    """Get the kernel virtualenv directory (~/.astro/ai/kernel_venv/)."""
    return get_base_dir() / "ai" / "kernel_venv"


def get_sessions_dir() -> Path:
    """Get the sessions directory (~/.astro/ai/sessions/)."""
    return get_base_dir() / "ai" / "sessions"


def get_env_file_path() -> Path:
    """Get the .env file path (~/.astro/ai/config/.env)."""
    return get_config_dir() / ".env"


def get_warehouse_config_path() -> Path:
    """Get the warehouse config path (~/.astro/ai/config/warehouse.yml)."""
    return get_config_dir() / "warehouse.yml"


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_session_dir(session_id: str) -> Path:
    """Ensure session directory exists and return its path."""
    session_dir = get_sessions_dir() / session_id
    return ensure_dir(session_dir)


# ==============================================================================
# Environment Variable Expansion
# ==============================================================================


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports ${VAR} and $VAR syntax.
    """
    if not isinstance(value, str):
        return value

    # Pattern matches ${VAR} or $VAR
    pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

    def replacer(match: re.Match) -> str:
        var_name = match.group(1) or match.group(2)
        return os.environ.get(var_name, match.group(0))

    return pattern.sub(replacer, value)


def expand_config_values(config: dict[str, Any]) -> dict[str, Any]:
    """Recursively expand environment variables in config values."""
    result = {}
    for key, value in config.items():
        if isinstance(value, dict):
            result[key] = expand_config_values(value)
        elif isinstance(value, str):
            result[key] = expand_env_vars(value)
        elif isinstance(value, list):
            result[key] = [
                expand_env_vars(item) if isinstance(item, str) else item for item in value
            ]
        else:
            result[key] = value
    return result


# ==============================================================================
# Warehouse Configuration Models
# ==============================================================================


class SnowflakeConfig(BaseModel):
    """Snowflake warehouse configuration."""

    type: str = "snowflake"
    auth_type: str = Field(default="password", description="Authentication type: password or private_key")
    account: str = Field(..., description="Snowflake account identifier")
    user: str = Field(..., description="Snowflake username")
    password: str | None = Field(default=None, description="Password for password auth")
    private_key: str | None = Field(default=None, description="Private key for key-pair auth")
    private_key_passphrase: str | None = Field(default=None, description="Passphrase for encrypted private key")
    warehouse: str = Field(..., description="Default warehouse to use")
    role: str | None = Field(default=None, description="Role to use")
    databases: list[str] = Field(default_factory=list, description="List of accessible databases")

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, v: str) -> str:
        if v not in ("password", "private_key"):
            raise ValueError("auth_type must be 'password' or 'private_key'")
        return v


class WarehouseConfig(BaseModel):
    """Generic warehouse configuration that can hold any warehouse type."""

    name: str
    type: str
    config: dict[str, Any]

    def as_snowflake(self) -> SnowflakeConfig:
        """Convert to SnowflakeConfig if type is snowflake."""
        if self.type != "snowflake":
            raise ValueError(f"Cannot convert {self.type} config to Snowflake")
        return SnowflakeConfig(**self.config)


# ==============================================================================
# Configuration Loading
# ==============================================================================


def load_env() -> None:
    """Load environment variables from the Astro config .env file."""
    env_path = get_env_file_path()
    if env_path.exists():
        load_dotenv(env_path)


def load_warehouse_config(path: Path | None = None) -> dict[str, WarehouseConfig]:
    """Load warehouse configuration from YAML file.

    Args:
        path: Optional path to warehouse.yml. Defaults to ~/.astro/ai/config/warehouse.yml

    Returns:
        Dictionary mapping connection names to WarehouseConfig objects.

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    # Load environment variables first
    load_env()

    config_path = path or get_warehouse_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Warehouse config not found: {config_path}")

    with open(config_path) as f:
        raw_config = yaml.safe_load(f)

    if not raw_config:
        raise ValueError(f"Empty warehouse config: {config_path}")

    # Expand environment variables
    expanded_config = expand_config_values(raw_config)

    # Parse each warehouse connection
    warehouses: dict[str, WarehouseConfig] = {}
    for name, config in expanded_config.items():
        if not isinstance(config, dict):
            continue
        warehouse_type = config.get("type", "unknown")
        warehouses[name] = WarehouseConfig(
            name=name,
            type=warehouse_type,
            config=config,
        )

    if not warehouses:
        raise ValueError(f"No warehouse configurations found in {config_path}")

    return warehouses


def get_default_warehouse() -> tuple[str, WarehouseConfig] | None:
    """Get the default (first) warehouse configuration.

    Returns:
        Tuple of (name, config) or None if no warehouses configured.
    """
    try:
        warehouses = load_warehouse_config()
        for name, config in warehouses.items():
            return name, config
        return None
    except (FileNotFoundError, ValueError):
        return None


def get_warehouse(name: str) -> WarehouseConfig | None:
    """Get a specific warehouse configuration by name.

    Args:
        name: The connection name from warehouse.yml

    Returns:
        WarehouseConfig or None if not found.
    """
    try:
        warehouses = load_warehouse_config()
        return warehouses.get(name)
    except (FileNotFoundError, ValueError):
        return None

