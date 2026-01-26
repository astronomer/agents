"""MCP resources - static, read-only information endpoints.

Note: admin _impl functions are imported lazily inside each resource function
to avoid circular imports (server → resources → tools.admin → server).
"""

from astro_airflow_mcp.server import mcp


@mcp.resource("airflow://version")
def resource_version() -> str:
    """Get Airflow version information as a resource."""
    from astro_airflow_mcp.tools.admin import _get_version_impl

    return _get_version_impl()


@mcp.resource("airflow://providers")
def resource_providers() -> str:
    """Get installed Airflow providers as a resource."""
    from astro_airflow_mcp.tools.admin import _list_providers_impl

    return _list_providers_impl()


@mcp.resource("airflow://plugins")
def resource_plugins() -> str:
    """Get installed Airflow plugins as a resource."""
    from astro_airflow_mcp.tools.admin import _list_plugins_impl

    return _list_plugins_impl()


@mcp.resource("airflow://config")
def resource_config() -> str:
    """Get Airflow configuration as a resource."""
    from astro_airflow_mcp.tools.admin import _get_config_impl

    return _get_config_impl()
