"""MCP resources - static, read-only information endpoints."""

from astro_airflow_mcp.server import mcp
from astro_airflow_mcp.tools.admin import (
    _get_config_impl,
    _get_version_impl,
    _list_plugins_impl,
    _list_providers_impl,
)


@mcp.resource("airflow://version")
def resource_version() -> str:
    """Get Airflow version information as a resource."""
    return _get_version_impl()


@mcp.resource("airflow://providers")
def resource_providers() -> str:
    """Get installed Airflow providers as a resource."""
    return _list_providers_impl()


@mcp.resource("airflow://plugins")
def resource_plugins() -> str:
    """Get installed Airflow plugins as a resource."""
    return _list_plugins_impl()


@mcp.resource("airflow://config")
def resource_config() -> str:
    """Get Airflow configuration as a resource."""
    return _get_config_impl()
