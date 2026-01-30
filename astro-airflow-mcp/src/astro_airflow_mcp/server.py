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

from astro_airflow_mcp.adapter_manager import AdapterManager
from astro_airflow_mcp.adapters import AirflowAdapter
from astro_airflow_mcp.logging import get_logger
from astro_airflow_mcp.utils import wrap_list_response

logger = get_logger(__name__)


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


# Global adapter manager and project directory
_manager = AdapterManager()
_project_dir: str | None = None


def _get_adapter() -> AirflowAdapter:
    """Get or create the global adapter instance.

    The adapter is lazy-initialized on first use and will automatically
    detect the Airflow version and create the appropriate adapter type.

    Returns:
        Version-specific AirflowAdapter instance
    """
    return _manager.get_adapter()


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
    global _project_dir
    if project_dir:
        _project_dir = project_dir

    _manager.configure(
        url=url,
        auth_token=auth_token,
        username=username,
        password=password,
    )


def get_project_dir() -> str | None:
    """Get the configured project directory.

    Returns:
        The project directory path, or None if not configured
    """
    return _project_dir


def _invalidate_token() -> None:
    """Invalidate the current token to force refresh on next request."""
    _manager.invalidate_token()


def _wrap_list_response(items: list[dict[str, Any]], key_name: str, data: dict[str, Any]) -> str:
    """Wrap API list response with pagination metadata (JSON string version).

    This is a thin wrapper around the shared wrap_list_response that returns
    a JSON string for MCP tool responses.

    Args:
        items: List of items from the API
        key_name: Name for the items key in response (e.g., 'dags', 'dag_runs')
        data: Original API response data (for total_entries)

    Returns:
        JSON string with pagination metadata
    """
    result = wrap_list_response(items, key_name, data)
    return json.dumps(result, indent=2)


# Import tool, resource, and prompt modules to register them with the MCP server.
# These must be imported AFTER all definitions above since they depend on mcp,
# _get_adapter, and other symbols defined in this module.
import astro_airflow_mcp.prompts as prompts  # noqa: E402, F401
import astro_airflow_mcp.resources as resources  # noqa: E402, F401
import astro_airflow_mcp.tools as tools  # noqa: E402, F401
