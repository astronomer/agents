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
        # If the URL is overridden by env var, don't inherit auth from config
        # since the config's auth is for a different instance.
        #
        # An explicitly empty AIRFLOW_API_URL ("" in the environment) is treated
        # as "no Airflow is configured right now" -- do NOT fall back to the
        # config file or DEFAULT_AIRFLOW_URL. This lets programmatic callers
        # (automation, agent frameworks) propagate "nothing is configured"
        # without risking queries against whatever happens to be listening on
        # localhost:8080.
        airflow_url_env = os.environ.get("AIRFLOW_API_URL")
        url_from_env = bool(airflow_url_env)

        if airflow_url_env is not None and not airflow_url_env:
            message = (
                "Error: AIRFLOW_API_URL is set but empty. "
                "No Airflow instance is configured.\n"
                "To configure one, either:\n"
                "  - set AIRFLOW_API_URL to a webserver URL, or\n"
                "  - run `af instance add <name> --url <url>` "
                "and `af instance use <name>`.\n"
                "To use the default (http://localhost:8080), "
                "unset AIRFLOW_API_URL."
            )
            print(message, file=sys.stderr)
            sys.exit(2)

        if url_from_env:
            final_url = os.environ["AIRFLOW_API_URL"]
        elif config_values and config_values.url:
            final_url = config_values.url
        else:
            final_url = DEFAULT_AIRFLOW_URL

        # Auth token priority
        if os.environ.get("AIRFLOW_AUTH_TOKEN"):
            final_token = os.environ["AIRFLOW_AUTH_TOKEN"]
        elif not url_from_env and config_values and config_values.token:
            final_token = config_values.token
        else:
            final_token = None

        # Username/password priority
        if os.environ.get("AIRFLOW_USERNAME"):
            final_username = os.environ["AIRFLOW_USERNAME"]
        elif not url_from_env and config_values and config_values.username:
            final_username = config_values.username
        else:
            final_username = None

        if os.environ.get("AIRFLOW_PASSWORD"):
            final_password = os.environ["AIRFLOW_PASSWORD"]
        elif not url_from_env and config_values and config_values.password:
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

        # When the resolved instance is configured for astro_pat AND the
        # caller hasn't overridden auth via env vars, route through the PAT
        # resolver instead of treating no-token as "no auth".
        env_overrode_auth = bool(
            os.environ.get("AIRFLOW_AUTH_TOKEN")
            or os.environ.get("AIRFLOW_USERNAME")
            or os.environ.get("AIRFLOW_PASSWORD")
        )
        if (
            not url_from_env
            and not env_overrode_auth
            and config_values is not None
            and config_values.auth_kind == "astro_pat"
        ):
            self._manager.configure(
                url=final_url,
                auth_kind="astro_pat",
                astro_context=config_values.astro_context,
                verify=verify,
            )
        else:
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
