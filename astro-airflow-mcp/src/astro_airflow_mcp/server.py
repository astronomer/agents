"""FastMCP server for Airflow integration.

This module contains the core MCP server infrastructure: configuration,
authentication, adapter management, and shared helpers. Tool implementations
are in the ``tools/`` subpackage, resources in ``resources.py``, and prompts
in ``prompts.py``.
"""

import json
import time
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from astro_airflow_mcp.adapters import AirflowAdapter, create_adapter
from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Default configuration values
DEFAULT_AIRFLOW_URL = "http://localhost:8080"
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0
# Buffer time before token expiry to trigger refresh (5 minutes)
TOKEN_REFRESH_BUFFER_SECONDS = 300


class AirflowTokenManager:
    """Manages JWT token lifecycle for Airflow API authentication.

    Handles fetching tokens from /auth/token endpoint (Airflow 3.x),
    automatic refresh when tokens expire, and supports both credential-based
    and credential-less (all_admins mode) authentication.

    For Airflow 2.x (which doesn't have /auth/token), this manager will detect
    the 404 and stop attempting token fetches, falling back to basic auth.
    """

    def __init__(
        self,
        airflow_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        """Initialize the token manager.

        Args:
            airflow_url: Base URL of the Airflow webserver
            username: Optional username for token authentication
            password: Optional password for token authentication
        """
        self.airflow_url = airflow_url
        self.username = username
        self.password = password
        self._token: str | None = None
        self._token_fetched_at: float | None = None
        # Default token lifetime of 30 minutes if not provided by server
        self._token_lifetime_seconds: float = 1800
        # Track if token endpoint is available (False for Airflow 2.x)
        self._token_endpoint_available: bool | None = None

    def get_token(self) -> str | None:
        """Get current token, fetching/refreshing if needed.

        Returns:
            JWT token string, or None if token fetch fails or endpoint unavailable
        """
        # If we've determined the endpoint doesn't exist, don't try again
        if self._token_endpoint_available is False:
            return None
        if self._should_refresh():
            self._fetch_token()
        return self._token

    def get_basic_auth(self) -> tuple[str, str] | None:
        """Get basic auth credentials for Airflow 2.x fallback.

        Returns:
            Tuple of (username, password) if available, None otherwise
        """
        if self.username and self.password:
            return (self.username, self.password)
        return None

    def is_token_endpoint_available(self) -> bool | None:
        """Check if the token endpoint is available.

        Returns:
            True if available (Airflow 3.x), False if not (Airflow 2.x),
            None if not yet determined.
        """
        return self._token_endpoint_available

    def _should_refresh(self) -> bool:
        """Check if token needs refresh (expired or not yet fetched).

        Returns:
            True if token should be refreshed
        """
        if self._token is None:
            return True
        if self._token_fetched_at is None:
            return True
        # Refresh if we're within the buffer time of expiry
        elapsed = time.time() - self._token_fetched_at
        return elapsed >= (self._token_lifetime_seconds - TOKEN_REFRESH_BUFFER_SECONDS)

    def _fetch_token(self) -> None:
        """Fetch new token from /auth/token endpoint.

        Tries credential-less GET first if no username/password provided,
        otherwise uses POST with credentials.

        For Airflow 2.x (404 response), marks the endpoint as unavailable
        and stops future attempts.
        """
        token_url = f"{self.airflow_url}/auth/token"

        try:
            with httpx.Client(timeout=30.0) as client:
                if self.username and self.password:
                    # Use credentials to fetch token
                    logger.debug("Fetching token with username/password credentials")
                    response = client.post(
                        token_url,
                        json={"username": self.username, "password": self.password},
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    # Try credential-less fetch (for all_admins mode)
                    logger.debug("Attempting credential-less token fetch")
                    response = client.get(token_url)

            # Check for 404 - indicates Airflow 2.x without token endpoint
            if response.status_code == 404:
                self._token_endpoint_available = False
                self._token = None
                # Default to admin:admin for Airflow 2.x if no credentials provided
                if not self.username and not self.password:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Defaulting to admin:admin for basic auth."
                    )
                    self.username = "admin"  # nosec B105 - default for local dev
                    self.password = "admin"  # nosec B105 - default for local dev
                else:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Using provided credentials for basic auth."
                    )
                return

            response.raise_for_status()
            data = response.json()

            # Extract token from response
            # Airflow returns {"access_token": "...", "token_type": "bearer"}
            if "access_token" in data:
                self._token = data["access_token"]
                self._token_fetched_at = time.time()
                self._token_endpoint_available = True
                # Use expires_in if provided, otherwise keep default
                if "expires_in" in data:
                    self._token_lifetime_seconds = float(data["expires_in"])
                logger.info("Successfully fetched Airflow API token")
            else:
                logger.warning("Unexpected token response format: %s", data)
                self._token = None

        except httpx.RequestError as e:
            logger.warning("Failed to fetch token from %s: %s", token_url, e)
            self._token = None

    def invalidate(self) -> None:
        """Force token refresh on next request."""
        self._token = None
        self._token_fetched_at = None


# Create MCP server
mcp = FastMCP(
    "Airflow MCP Server",
    instructions="""
    This server provides access to Apache Airflow's REST API through MCP tools.

    Use these tools to:
    - List and inspect DAGs (Directed Acyclic Graphs / workflows)
    - View DAG runs and their execution status
    - Check task instances and their states
    - Inspect Airflow connections, variables, and pools
    - Monitor DAG statistics and warnings
    - View system configuration and version information

    When the user asks about Airflow workflows, pipelines, or data orchestration,
    use these tools to provide detailed, accurate information directly from the
    Airflow instance.
    """,
)

# Add logging middleware to log all MCP tool calls
mcp.add_middleware(LoggingMiddleware(include_payloads=True))


# Global configuration for Airflow API access
class AirflowConfig:
    """Global configuration for Airflow API access."""

    def __init__(self):
        self.url: str = DEFAULT_AIRFLOW_URL
        self.auth_token: str | None = None
        self.token_manager: AirflowTokenManager | None = None
        self.project_dir: str | None = None


_config = AirflowConfig()

# Global adapter instance (lazy-initialized)
_adapter: AirflowAdapter | None = None


def _get_adapter() -> AirflowAdapter:
    """Get or create the global adapter instance.

    The adapter is lazy-initialized on first use and will automatically
    detect the Airflow version and create the appropriate adapter type.

    Returns:
        Version-specific AirflowAdapter instance
    """
    global _adapter
    if _adapter is None:
        logger.info("Initializing adapter for %s", _config.url)
        _adapter = create_adapter(
            airflow_url=_config.url,
            token_getter=_get_auth_token,
            basic_auth_getter=_get_basic_auth,
        )
        logger.info("Created adapter for Airflow %s", _adapter.version)
    return _adapter


def _reset_adapter() -> None:
    """Reset the global adapter (e.g., when config changes)."""
    global _adapter
    _adapter = None


def configure(
    url: str | None = None,
    auth_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    project_dir: str | None = None,
) -> None:
    """Configure global Airflow connection settings.

    Args:
        url: Base URL of Airflow webserver
        auth_token: Direct bearer token for authentication (takes precedence)
        username: Username for token-based authentication
        password: Password for token-based authentication
        project_dir: Project directory where Claude Code is running

    Note:
        If auth_token is provided, it will be used directly.
        If username/password are provided (without auth_token), a token manager
        will be created to fetch and refresh tokens automatically.
        If neither is provided, credential-less token fetch will be attempted.
    """
    if project_dir:
        _config.project_dir = project_dir
    if url:
        _config.url = url
    if auth_token:
        # Direct token takes precedence - no token manager needed
        _config.auth_token = auth_token
        _config.token_manager = None
    elif username or password:
        # Use token manager with credentials
        _config.auth_token = None
        _config.token_manager = AirflowTokenManager(
            airflow_url=_config.url,
            username=username,
            password=password,
        )
    else:
        # No auth provided - try credential-less token manager
        _config.auth_token = None
        _config.token_manager = AirflowTokenManager(
            airflow_url=_config.url,
            username=None,
            password=None,
        )

    # Reset adapter so it will be re-created with new config
    _reset_adapter()


def _get_auth_token() -> str | None:
    """Get the current authentication token.

    Returns:
        Bearer token string, or None if no authentication configured
    """
    # Direct token takes precedence
    if _config.auth_token:
        return _config.auth_token
    # Otherwise use token manager
    if _config.token_manager:
        return _config.token_manager.get_token()
    return None


def _get_basic_auth() -> tuple[str, str] | None:
    """Get basic auth credentials for Airflow 2.x fallback.

    Returns:
        Tuple of (username, password) if available, None otherwise
    """
    if _config.token_manager:
        return _config.token_manager.get_basic_auth()
    return None


def get_project_dir() -> str | None:
    """Get the configured project directory.

    Returns:
        The project directory path, or None if not configured
    """
    return _config.project_dir


def _invalidate_token() -> None:
    """Invalidate the current token to force refresh on next request."""
    if _config.token_manager:
        _config.token_manager.invalidate()


# Helper functions for response formatting
def _wrap_list_response(items: list[dict[str, Any]], key_name: str, data: dict[str, Any]) -> str:
    """Wrap API list response with pagination metadata.

    Args:
        items: List of items from the API
        key_name: Name for the items key in response (e.g., 'dags', 'dag_runs')
        data: Original API response data (for total_entries)

    Returns:
        JSON string with pagination metadata
    """

    total_entries = data.get("total_entries", len(items))
    result: dict[str, Any] = {
        f"total_{key_name}": total_entries,
        "returned_count": len(items),
        key_name: items,
    }
    return json.dumps(result, indent=2)


# Import tool, resource, and prompt modules to register them with the MCP server.
# These must be imported AFTER all definitions above since they depend on mcp,
# _get_adapter, and other symbols defined in this module.
import astro_airflow_mcp.prompts as prompts  # noqa: E402, F401
import astro_airflow_mcp.resources as resources  # noqa: E402, F401
import astro_airflow_mcp.tools as tools  # noqa: E402, F401
