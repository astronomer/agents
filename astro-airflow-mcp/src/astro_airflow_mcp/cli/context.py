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
        self._initialized = False

    @classmethod
    def get_instance(cls) -> CLIContext:
        """Get singleton instance of CLIContext."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_from_config(self) -> ResolvedConfig | None:
        """Load configuration from config file.

        Returns:
            ResolvedConfig if available, None otherwise
        """
        try:
            from astro_airflow_mcp.config import ConfigError, ConfigManager

            manager = ConfigManager()
            return manager.resolve_instance()
        except FileNotFoundError:
            # No config file - this is normal for first-time users
            return None
        except ConfigError as e:
            # Config exists but has errors - warn the user
            print(f"Warning: Failed to load config: {e}", file=sys.stderr)
            print("Falling back to default settings (localhost:8080)", file=sys.stderr)
            return None

    def init(self) -> None:
        """Initialize the CLI context with connection settings.

        Priority order (standard CLI convention):
        1. Environment variables
        2. Config file (current instance)
        3. Defaults

        This is called once at startup.
        """
        if self._initialized:
            return

        # Load config for base values
        config_values = self._load_from_config()

        # Determine final values with priority: env > config > default
        if os.environ.get("AIRFLOW_API_URL"):
            final_url = os.environ["AIRFLOW_API_URL"]
        elif config_values and config_values.url:
            final_url = config_values.url
        else:
            final_url = DEFAULT_AIRFLOW_URL

        # Auth token priority
        if os.environ.get("AIRFLOW_AUTH_TOKEN"):
            final_token = os.environ["AIRFLOW_AUTH_TOKEN"]
        elif config_values and config_values.token:
            final_token = config_values.token
        else:
            final_token = None

        # Username/password priority
        if os.environ.get("AIRFLOW_USERNAME"):
            final_username = os.environ["AIRFLOW_USERNAME"]
        elif config_values and config_values.username:
            final_username = config_values.username
        else:
            final_username = None

        if os.environ.get("AIRFLOW_PASSWORD"):
            final_password = os.environ["AIRFLOW_PASSWORD"]
        elif config_values and config_values.password:
            final_password = config_values.password
        else:
            final_password = None

        # SSL verification priority: env > config > default
        verify_ssl = True
        ca_cert: str | None = None

        env_verify = os.environ.get("AIRFLOW_VERIFY_SSL")
        if env_verify is not None:
            verify_ssl = env_verify.lower() not in ("false", "0", "no")
        elif config_values:
            verify_ssl = config_values.verify_ssl

        env_ca_cert = os.environ.get("AIRFLOW_CA_CERT")
        if env_ca_cert:
            ca_cert = env_ca_cert
        elif config_values:
            ca_cert = config_values.ca_cert

        # Conflict: ca_cert wins over verify_ssl=False (ca_cert implies custom verification)
        if ca_cert and not verify_ssl:
            print(
                "Warning: Both ca_cert and verify_ssl=False are set. "
                "Using ca_cert for SSL verification.",
                file=sys.stderr,
            )

        # Compute final verify value for httpx: ca_cert path > False > True
        verify: bool | str = True
        if ca_cert:
            verify = ca_cert
        elif not verify_ssl:
            verify = False

        # Configure the underlying adapter manager
        self._manager.configure(
            url=final_url,
            auth_token=final_token,
            username=final_username,
            password=final_password,
            verify=verify,
        )
        self._initialized = True

    def get_adapter(self) -> AirflowAdapter:
        """Get or create the adapter instance."""
        if not self._initialized:
            self.init()
        return self._manager.get_adapter()


def get_adapter() -> AirflowAdapter:
    """Get the configured adapter instance.

    This is the main entry point for CLI commands to get the adapter.
    """
    return CLIContext.get_instance().get_adapter()


def init_context() -> None:
    """Initialize the CLI context.

    Called once at startup from main callback.
    """
    CLIContext.get_instance().init()
