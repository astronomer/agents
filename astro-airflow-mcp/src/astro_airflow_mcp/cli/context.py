"""Context management for CLI - adapter initialization and auth handling."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from astro_airflow_mcp.adapter_manager import AdapterManager
from astro_airflow_mcp.constants import DEFAULT_AIRFLOW_URL

if TYPE_CHECKING:
    from astro_airflow_mcp.adapters import AirflowAdapter
    from astro_airflow_mcp.config import ResolvedConfig


class CLIContext:
    """Manages CLI context including adapter and authentication.

    Extends AdapterManager with CLI-specific features like config file
    loading and environment variable resolution.
    """

    _instance: CLIContext | None = None

    def __init__(self):
        self._manager = AdapterManager()

    @classmethod
    def get_instance(cls) -> CLIContext:
        """Get singleton instance of CLIContext."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_from_config(self, instance_name: str | None = None) -> ResolvedConfig | None:
        """Load configuration from config file.

        Args:
            instance_name: Specific instance to load, or None for current instance

        Returns:
            ResolvedConfig if available, None otherwise
        """
        try:
            from astro_airflow_mcp.config import ConfigError, ConfigManager

            manager = ConfigManager()
            return manager.resolve_instance(instance_name)
        except FileNotFoundError:
            # No config file - this is normal for first-time users
            return None
        except ConfigError as e:
            # Config exists but has errors - warn the user
            print(f"Warning: Failed to load config: {e}", file=sys.stderr)
            print("Falling back to default settings (localhost:8080)", file=sys.stderr)
            return None

    def configure(
        self,
        airflow_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        auth_token: str | None = None,
        instance_name: str | None = None,
    ) -> None:
        """Configure the CLI context with connection settings.

        Priority order:
        1. CLI arguments (airflow_url, username, password, auth_token)
        2. Config file (instance_name or current instance)
        3. Environment variables
        4. Defaults
        """
        # Try to load from config file if instance specified or no CLI args
        config_values: ResolvedConfig | None = None
        if instance_name is not None or (
            airflow_url is None and username is None and password is None and auth_token is None
        ):
            config_values = self._load_from_config(instance_name)

        # Determine final values with priority: CLI > config > env > default
        if airflow_url:
            final_url = airflow_url
        elif config_values and config_values.url:
            final_url = config_values.url
        else:
            final_url = os.environ.get("AIRFLOW_API_URL") or DEFAULT_AIRFLOW_URL

        # Auth token priority
        if auth_token:
            final_token = auth_token
        elif config_values and config_values.token:
            final_token = config_values.token
        else:
            final_token = os.environ.get("AIRFLOW_AUTH_TOKEN")

        # Username/password priority
        if username:
            final_username = username
        elif config_values and config_values.username:
            final_username = config_values.username
        else:
            final_username = os.environ.get("AIRFLOW_USERNAME")

        if password:
            final_password = password
        elif config_values and config_values.password:
            final_password = config_values.password
        else:
            final_password = os.environ.get("AIRFLOW_PASSWORD")

        # Configure the underlying adapter manager
        self._manager.configure(
            url=final_url,
            auth_token=final_token,
            username=final_username,
            password=final_password,
        )

    def get_adapter(self) -> AirflowAdapter:
        """Get or create the adapter instance."""
        # Configure with defaults if not already done
        if self._manager.airflow_url == DEFAULT_AIRFLOW_URL:
            # Check if we need to load config
            self.configure()
        return self._manager.get_adapter()


def get_adapter() -> AirflowAdapter:
    """Get the configured adapter instance.

    This is the main entry point for CLI commands to get the adapter.
    """
    return CLIContext.get_instance().get_adapter()


def configure_context(
    airflow_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    auth_token: str | None = None,
    instance_name: str | None = None,
) -> None:
    """Configure the CLI context with connection settings.

    Args:
        airflow_url: Base URL of Airflow webserver
        username: Username for authentication
        password: Password for authentication
        auth_token: Direct bearer token (takes precedence over username/password)
        instance_name: Name of instance to load from config file
    """
    CLIContext.get_instance().configure(
        airflow_url=airflow_url,
        username=username,
        password=password,
        auth_token=auth_token,
        instance_name=instance_name,
    )
