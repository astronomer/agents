"""Unified adapter management for CLI and MCP server."""

from astro_airflow_mcp.adapters import AirflowAdapter, create_adapter
from astro_airflow_mcp.auth import TokenManager
from astro_airflow_mcp.constants import DEFAULT_AIRFLOW_URL
from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)


class AdapterManager:
    """Manages Airflow adapter lifecycle and authentication.

    This class provides a unified interface for adapter management
    used by both the CLI and MCP server. It handles:
    - Lazy initialization of the adapter
    - Token-based and basic authentication
    - Adapter reset when configuration changes
    """

    def __init__(self):
        self._adapter: AirflowAdapter | None = None
        self._token_manager: TokenManager | None = None
        self._auth_token: str | None = None
        self._airflow_url: str = DEFAULT_AIRFLOW_URL

    @property
    def airflow_url(self) -> str:
        """Get the configured Airflow URL."""
        return self._airflow_url

    def configure(
        self,
        url: str | None = None,
        auth_token: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Configure adapter connection settings.

        Args:
            url: Base URL of Airflow webserver
            auth_token: Direct bearer token for authentication (takes precedence)
            username: Username for token-based authentication
            password: Password for token-based authentication

        Note:
            If auth_token is provided, it will be used directly.
            If username/password are provided (without auth_token), a token manager
            will be created to fetch and refresh tokens automatically.
            If neither is provided, credential-less token fetch will be attempted.
        """
        if url:
            self._airflow_url = url

        if auth_token:
            # Direct token takes precedence - no token manager needed
            self._auth_token = auth_token
            self._token_manager = None
        elif username or password:
            # Use token manager with credentials
            self._auth_token = None
            self._token_manager = TokenManager(
                airflow_url=self._airflow_url,
                username=username,
                password=password,
            )
        else:
            # No auth provided - try credential-less token manager
            self._auth_token = None
            self._token_manager = TokenManager(
                airflow_url=self._airflow_url,
                username=None,
                password=None,
            )

        # Reset adapter so it will be re-created with new config
        self._reset_adapter()

    def get_adapter(self) -> AirflowAdapter:
        """Get or create the adapter instance.

        The adapter is lazy-initialized on first use and will automatically
        detect the Airflow version and create the appropriate adapter type.

        Returns:
            Version-specific AirflowAdapter instance
        """
        if self._adapter is None:
            logger.info("Initializing adapter for %s", self._airflow_url)
            self._adapter = create_adapter(
                airflow_url=self._airflow_url,
                token_getter=self._get_auth_token,
                basic_auth_getter=self._get_basic_auth,
            )
            logger.info("Created adapter for Airflow %s", self._adapter.version)
        return self._adapter

    def _reset_adapter(self) -> None:
        """Reset the adapter (e.g., when config changes)."""
        self._adapter = None

    def _get_auth_token(self) -> str | None:
        """Get the current authentication token.

        Returns:
            Bearer token string, or None if no authentication configured
        """
        # Direct token takes precedence
        if self._auth_token:
            return self._auth_token
        # Otherwise use token manager
        if self._token_manager:
            return self._token_manager.get_token()
        return None

    def _get_basic_auth(self) -> tuple[str, str] | None:
        """Get basic auth credentials for Airflow 2.x fallback.

        Returns:
            Tuple of (username, password) if available, None otherwise
        """
        if self._token_manager:
            return self._token_manager.get_basic_auth()
        return None

    def invalidate_token(self) -> None:
        """Invalidate the current token to force refresh on next request."""
        if self._token_manager:
            self._token_manager.invalidate()
