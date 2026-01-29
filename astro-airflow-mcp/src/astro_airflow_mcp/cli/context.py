"""Context management for CLI - adapter initialization and auth handling."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from astro_airflow_mcp.adapters import AirflowAdapter, create_adapter
from astro_airflow_mcp.auth import TokenManager

if TYPE_CHECKING:
    from astro_airflow_mcp.config import ResolvedConfig


class CLIContext:
    """Manages CLI context including adapter and authentication."""

    _instance: CLIContext | None = None

    def __init__(self):
        self._adapter: AirflowAdapter | None = None
        self._token_manager: TokenManager | None = None
        self._auth_token: str | None = None
        self._airflow_url: str | None = None

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
        except (ConfigError, FileNotFoundError):
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
            self._airflow_url = airflow_url
        elif config_values and config_values.url:
            self._airflow_url = config_values.url
        else:
            self._airflow_url = os.environ.get("AIRFLOW_API_URL") or "http://localhost:8080"

        # Auth token priority
        if auth_token:
            env_token = auth_token
        elif config_values and config_values.token:
            env_token = config_values.token
        else:
            env_token = os.environ.get("AIRFLOW_AUTH_TOKEN")

        # Username/password priority
        if username:
            env_username = username
        elif config_values and config_values.username:
            env_username = config_values.username
        else:
            env_username = os.environ.get("AIRFLOW_USERNAME")

        if password:
            env_password = password
        elif config_values and config_values.password:
            env_password = config_values.password
        else:
            env_password = os.environ.get("AIRFLOW_PASSWORD")

        if env_token:
            self._auth_token = env_token
            self._token_manager = None
        else:
            self._auth_token = None
            self._token_manager = TokenManager(
                airflow_url=self._airflow_url,
                username=env_username,
                password=env_password,
            )

        # Reset adapter
        self._adapter = None

    def get_adapter(self) -> AirflowAdapter:
        """Get or create the adapter instance."""
        if self._adapter is None:
            if self._airflow_url is None:
                # Configure with defaults if not already done
                self.configure()

            self._adapter = create_adapter(
                airflow_url=self._airflow_url,  # type: ignore[arg-type]
                token_getter=self._get_auth_token,
                basic_auth_getter=self._get_basic_auth,
            )
        return self._adapter

    def _get_auth_token(self) -> str | None:
        """Get the current authentication token."""
        if self._auth_token:
            return self._auth_token
        if self._token_manager:
            return self._token_manager.get_token()
        return None

    def _get_basic_auth(self) -> tuple[str, str] | None:
        """Get basic auth credentials."""
        if self._token_manager:
            return self._token_manager.get_basic_auth()
        return None


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
