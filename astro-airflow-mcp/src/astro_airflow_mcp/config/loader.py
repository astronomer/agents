"""Configuration loading and management for af CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from filelock import FileLock

from astro_airflow_mcp.config.interpolation import interpolate_config_value
from astro_airflow_mcp.config.models import AirflowCliConfig

if TYPE_CHECKING:
    from astro_airflow_mcp.config.models import Instance


class ConfigError(Exception):
    """Error raised for configuration issues."""


@dataclass
class ResolvedConfig:
    """Resolved configuration ready for use."""

    url: str
    username: str | None = None
    password: str | None = None
    token: str | None = None
    instance_name: str | None = None
    sources: dict[str, str] = field(default_factory=dict)


class ConfigManager:
    """Manages af CLI configuration file."""

    DEFAULT_CONFIG_DIR = Path.home() / ".af"
    DEFAULT_CONFIG_FILE = "config.yaml"
    CONFIG_ENV_VAR = "AF_CONFIG"

    def __init__(self, config_path: Path | None = None):
        """Initialize the config manager.

        Args:
            config_path: Optional custom path to config file.
                         Falls back to AF_CONFIG env var,
                         then ~/.af/config.yaml
        """
        if config_path:
            self.config_path = config_path
        elif os.environ.get(self.CONFIG_ENV_VAR):
            self.config_path = Path(os.environ[self.CONFIG_ENV_VAR])
        else:
            self.config_path = self.DEFAULT_CONFIG_DIR / self.DEFAULT_CONFIG_FILE
        self.lock_path = self.config_path.with_suffix(".lock")

    def _ensure_dir(self) -> None:
        """Ensure the config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _create_default_config(self) -> AirflowCliConfig:
        """Create default config with localhost instance."""
        config = AirflowCliConfig()
        config.add_instance("localhost", "http://localhost:8080")
        config.use_instance("localhost")
        return config

    def load(self) -> AirflowCliConfig:
        """Load configuration from file.

        Returns:
            AirflowCliConfig instance (default localhost if file doesn't exist)

        Raises:
            ConfigError: If config file is invalid
        """
        if not self.config_path.exists():
            config = self._create_default_config()
            self.save(config)
            return config

        with FileLock(self.lock_path):
            try:
                with open(self.config_path) as f:
                    data = yaml.safe_load(f)

                if data is None:
                    return AirflowCliConfig()

                return AirflowCliConfig.model_validate(data)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in config file: {e}") from e
            except ValueError as e:
                raise ConfigError(f"Invalid config: {e}") from e

    def save(self, config: AirflowCliConfig) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
        """
        self._ensure_dir()

        with FileLock(self.lock_path):
            data = config.model_dump(by_alias=True, exclude_none=False)
            # Clean up None values at top level for cleaner YAML
            if data.get("current-instance") is None:
                del data["current-instance"]

            with open(self.config_path, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    def resolve_instance(self, instance_name: str | None = None) -> ResolvedConfig | None:
        """Resolve an instance to usable configuration.

        Args:
            instance_name: Name of instance to resolve, or None for current instance

        Returns:
            ResolvedConfig with interpolated values, or None if no instance

        Raises:
            ConfigError: If instance not found
        """
        config = self.load()

        # Determine which instance to use
        name = instance_name or config.current_instance
        if name is None:
            return None

        instance = config.get_instance(name)
        if instance is None:
            raise ConfigError(f"Instance '{name}' not found")

        # Interpolate environment variables in sensitive fields
        try:
            if instance.auth:
                return ResolvedConfig(
                    url=instance.url,
                    username=interpolate_config_value(instance.auth.username),
                    password=interpolate_config_value(instance.auth.password),
                    token=interpolate_config_value(instance.auth.token),
                    instance_name=name,
                    sources={
                        "url": f"instance:{name}",
                        "auth": f"instance:{name}",
                    },
                )
            return ResolvedConfig(
                url=instance.url,
                instance_name=name,
                sources={"url": f"instance:{name}"},
            )
        except ValueError as e:
            raise ConfigError(f"Error resolving instance '{name}': {e}") from e

    # CRUD operations that delegate to config model

    def add_instance(
        self,
        name: str,
        url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> None:
        """Add or update an instance."""
        config = self.load()
        config.add_instance(name, url, username=username, password=password, token=token)
        self.save(config)

    def delete_instance(self, name: str) -> None:
        """Delete an instance."""
        config = self.load()
        config.delete_instance(name)
        self.save(config)

    def use_instance(self, name: str) -> None:
        """Set the current instance."""
        config = self.load()
        config.use_instance(name)
        self.save(config)

    def get_current_instance(self) -> str | None:
        """Get the current instance name."""
        config = self.load()
        return config.current_instance

    def list_instances(self) -> list[Instance]:
        """List all instances."""
        config = self.load()
        return config.instances
