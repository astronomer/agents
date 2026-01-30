"""FastMCP server for Astro Cloud Observability API.

This module contains the core MCP server infrastructure: configuration,
authentication, client management. Tool implementations are in the
``tools/`` subpackage.
"""

import logging

from fastmcp import FastMCP

from astro_observe_mcp.auth import AstroTokenManager
from astro_observe_mcp.client import DEFAULT_API_URL, AstroClient

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULT_LIMIT = 20

# Create MCP server
mcp = FastMCP(
    "Astro Observe MCP Server",
    instructions="""
    This server provides access to Astro Cloud's Observability API through MCP tools.

    Use these tools to:
    - Search and discover data assets (tables, DAGs, tasks, datasets)
    - Get detailed information about specific assets
    - Explore available filter values for refining searches

    Supported asset types:
    - Tables: Snowflake, Databricks, BigQuery
    - Airflow: DAGs, tasks, datasets
    - OpenLineage datasets

    When the user asks about data assets, tables, pipelines, or data lineage,
    use these tools to provide accurate information from the Astro Cloud catalog.
    """,
)


# Global configuration for Astro API access
class AstroConfig:
    """Global configuration for Astro Cloud API access."""

    def __init__(self):
        self.organization_id: str | None = None
        self.api_url: str = DEFAULT_API_URL
        self.token_manager: AstroTokenManager | None = None


_config = AstroConfig()

# Global client instance (lazy-initialized)
_client: AstroClient | None = None


def _get_client() -> AstroClient:
    """Get or create the global Astro API client.

    The client is lazy-initialized on first use.

    Returns:
        Configured AstroClient instance

    Raises:
        RuntimeError: If organization_id is not configured
    """
    global _client
    if _client is None:
        if not _config.organization_id:
            raise RuntimeError(
                "Organization ID not configured. Use configure() or --org-id argument."
            )
        if not _config.token_manager:
            raise RuntimeError(
                "Token manager not configured. Use configure() to set up authentication."
            )
        logger.info(
            "Initializing Astro client for org %s at %s",
            _config.organization_id,
            _config.api_url,
        )
        _client = AstroClient(
            organization_id=_config.organization_id,
            token_manager=_config.token_manager,
            api_url=_config.api_url,
        )
    return _client


def _reset_client() -> None:
    """Reset the global client (e.g., when config changes)."""
    global _client
    _client = None


def configure(
    organization_id: str,
    token: str | None = None,
    api_url: str | None = None,
) -> None:
    """Configure global Astro Cloud API settings.

    Args:
        organization_id: The Astro organization ID (required)
        token: Direct bearer token for authentication
        api_url: Base URL for Astro Cloud API (defaults to https://api.astronomer.io)
    """
    _config.organization_id = organization_id
    _config.token_manager = AstroTokenManager(token=token)

    if api_url:
        _config.api_url = api_url

    # Reset client so it will be re-created with new config
    _reset_client()

    logger.info(
        "Configured Astro Observe MCP for org %s (token source: %s)",
        organization_id,
        _config.token_manager.get_token_source() or "none",
    )


def get_organization_id() -> str | None:
    """Get the configured organization ID.

    Returns:
        The organization ID, or None if not configured
    """
    return _config.organization_id


# Import tool modules to register them with the MCP server.
# These must be imported AFTER all definitions above since they depend on mcp
# and _get_client defined in this module.
import astro_observe_mcp.tools as tools  # noqa: E402, F401
