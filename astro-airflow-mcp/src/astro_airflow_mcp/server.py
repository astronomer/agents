"""FastMCP server for Airflow integration.

This module contains the core MCP server infrastructure: configuration,
authentication, adapter management, and shared helpers. Tool implementations
are in the ``tools/`` subpackage, resources in ``resources.py``, and prompts
in ``prompts.py``.
"""

import json
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from astro_airflow_mcp.adapters import AirflowAdapter, create_adapter
from astro_airflow_mcp.auth import TokenManager
from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Default configuration values
DEFAULT_AIRFLOW_URL = "http://localhost:8080"
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0


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
        self.token_manager: TokenManager | None = None
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
        _config.token_manager = TokenManager(
            airflow_url=_config.url,
            username=username,
            password=password,
        )
    else:
        # No auth provided - try credential-less token manager
        _config.auth_token = None
        _config.token_manager = TokenManager(
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
