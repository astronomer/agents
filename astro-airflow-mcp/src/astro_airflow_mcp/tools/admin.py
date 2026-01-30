"""Admin tools - connections, variables, pools, plugins, providers, config, version."""

import json
from typing import Any

from astro_airflow_mcp.constants import DEFAULT_LIMIT, DEFAULT_OFFSET
from astro_airflow_mcp.server import (
    _get_adapter,
    _wrap_list_response,
    mcp,
)
from astro_airflow_mcp.utils import filter_connection_passwords


def _list_connections_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing connections from Airflow.

    NOTE: This endpoint uses explicit field filtering (unlike other endpoints)
    to exclude sensitive information like passwords for security reasons.

    Args:
        limit: Maximum number of connections to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of connections with their metadata
    """

    try:
        adapter = _get_adapter()
        data = adapter.list_connections(limit=limit, offset=offset)

        if "connections" in data:
            connections = data["connections"]
            total_entries = data.get("total_entries", len(connections))

            # Note: Adapter's _filter_passwords already filters password field
            # but we apply additional explicit filtering for defense in depth
            filtered_connections = filter_connection_passwords(connections)

            result: dict[str, Any] = {
                "total_connections": total_entries,
                "returned_count": len(filtered_connections),
                "connections": filtered_connections,
            }

            return json.dumps(result, indent=2)
        return f"No connections found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_variable_impl(
    variable_key: str,
) -> str:
    """Internal implementation for getting a specific variable from Airflow.

    Args:
        variable_key: The key of the variable to get

    Returns:
        JSON string containing the variable details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_variable(variable_key)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_variables_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing variables from Airflow.

    Args:
        limit: Maximum number of variables to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of variables with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_variables(limit=limit, offset=offset)

        if "variables" in data:
            return _wrap_list_response(data["variables"], "variables", data)
        return f"No variables found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_version_impl() -> str:
    """Internal implementation for getting Airflow version information.

    Returns:
        JSON string containing the Airflow version information
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_version()
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _get_config_impl() -> str:
    """Internal implementation for getting Airflow configuration.

    Returns:
        JSON string containing the Airflow configuration organized by sections
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_config()

        if "sections" in data:
            # Add summary metadata and pass through sections
            result = {"total_sections": len(data["sections"]), "sections": data["sections"]}
            return json.dumps(result, indent=2)
        return f"No configuration found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_pool_impl(
    pool_name: str,
) -> str:
    """Internal implementation for getting details about a specific pool.

    Args:
        pool_name: The name of the pool to get details for

    Returns:
        JSON string containing the pool details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_pool(pool_name)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_pools_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing pools from Airflow.

    Args:
        limit: Maximum number of pools to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of pools with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_pools(limit=limit, offset=offset)

        if "pools" in data:
            return _wrap_list_response(data["pools"], "pools", data)
        return f"No pools found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_plugins_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing installed plugins from Airflow.

    Args:
        limit: Maximum number of plugins to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of installed plugins
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_plugins(limit=limit, offset=offset)

        if "plugins" in data:
            return _wrap_list_response(data["plugins"], "plugins", data)
        return f"No plugins found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_providers_impl() -> str:
    """Internal implementation for listing installed providers from Airflow.

    Returns:
        JSON string containing the list of installed providers
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_providers()

        if "providers" in data:
            return _wrap_list_response(data["providers"], "providers", data)
        return f"No providers found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def list_connections() -> str:
    """Get connection configurations for external systems (databases, APIs, services).

    Use this tool when the user asks about:
    - "What connections are configured?" or "List all connections"
    - "How do I connect to database X?"
    - "What's the connection string for Y?"
    - "Which databases/services are available?"
    - Finding connection details by name or type

    Connections store credentials and connection info for external systems
    that DAGs interact with (databases, S3, APIs, etc.).

    Returns connection metadata including:
    - connection_id: Unique name for this connection
    - conn_type: Type (postgres, mysql, s3, http, etc.)
    - description: Human-readable description
    - host: Server hostname or IP
    - port: Port number
    - schema: Database schema or path
    - login: Username (passwords excluded for security)
    - extra: Additional connection parameters as JSON

    IMPORTANT: Passwords are NEVER returned for security reasons.

    Returns:
        JSON with list of all connections (credentials excluded)
    """
    return _list_connections_impl()


@mcp.tool()
def get_variable(variable_key: str) -> str:
    """Get a specific Airflow variable by key.

    Use this tool when the user asks about:
    - "What's the value of variable X?" or "Show me variable Y"
    - "Get variable Z" or "What does variable A contain?"
    - "What's stored in variable B?" or "Look up variable C"

    Variables are key-value pairs stored in Airflow's metadata database that
    can be accessed by DAGs at runtime. They're commonly used for configuration
    values, API keys, or other settings that need to be shared across DAGs.

    Returns variable information including:
    - key: The variable's key/name
    - value: The variable's value (may be masked if marked as sensitive)
    - description: Optional description of the variable's purpose

    Args:
        variable_key: The key/name of the variable to retrieve

    Returns:
        JSON with the variable's key, value, and metadata
    """
    return _get_variable_impl(variable_key=variable_key)


@mcp.tool()
def list_variables() -> str:
    """Get all Airflow variables (key-value configuration pairs).

    Use this tool when the user asks about:
    - "What variables are configured?" or "List all variables"
    - "Show me the variables" or "What variables exist?"
    - "What configuration variables are available?"
    - "Show me all variable keys"

    Variables are key-value pairs stored in Airflow's metadata database that
    can be accessed by DAGs at runtime. They're commonly used for configuration
    values, environment-specific settings, or other data that needs to be
    shared across DAGs without hardcoding in the DAG files.

    Returns variable information including:
    - key: The variable's key/name
    - value: The variable's value (may be masked if marked as sensitive)
    - description: Optional description of the variable's purpose

    IMPORTANT: Sensitive variables (like passwords, API keys) may have their
    values masked in the response for security reasons.

    Returns:
        JSON with list of all variables and their values
    """
    return _list_variables_impl()


@mcp.tool()
def get_airflow_version() -> str:
    """Get version information for the Airflow instance.

    Use this tool when the user asks about:
    - "What version of Airflow is running?" or "Show me the Airflow version"
    - "What's the Airflow version?" or "Which Airflow release is this?"
    - "What version is installed?" or "Check Airflow version"
    - "Is this Airflow 2 or 3?" or "What's the version number?"

    Returns version information including:
    - version: The Airflow version string (e.g., "2.8.0", "3.0.0")
    - git_version: Git commit hash if available

    This is useful for:
    - Determining API compatibility
    - Checking if features are available in this version
    - Troubleshooting version-specific issues
    - Verifying upgrade success

    Returns:
        JSON with Airflow version information
    """
    return _get_version_impl()


@mcp.tool()
def get_airflow_config() -> str:
    """Get Airflow instance configuration and settings.

    Use this tool when the user asks about:
    - "What's the Airflow configuration?" or "Show me Airflow settings"
    - "What's the executor type?" or "How is Airflow configured?"
    - "What's the parallelism setting?"
    - Database connection, logging, or scheduler settings
    - Finding specific configuration values

    Returns all Airflow configuration organized by sections:
    - [core]: Basic Airflow settings (executor, dags_folder, parallelism)
    - [database]: Database connection and settings
    - [webserver]: Web UI configuration (port, workers, auth)
    - [scheduler]: Scheduler behavior and intervals
    - [logging]: Log locations and formatting
    - [api]: REST API configuration
    - [operators]: Default operator settings
    - And many more sections...

    Each setting includes:
    - key: Configuration parameter name
    - value: Current value
    - source: Where the value came from (default, env var, config file)

    Returns:
        JSON with complete Airflow configuration organized by sections
    """
    return _get_config_impl()


@mcp.tool()
def get_pool(pool_name: str) -> str:
    """Get detailed information about a specific resource pool.

    Use this tool when the user asks about:
    - "Show me details for pool X" or "What's the status of pool Y?"
    - "How many slots are available in pool Z?" or "Is pool X full?"
    - "What's using pool Y?" or "How many tasks are running in pool X?"
    - "Get information about the default_pool" or "Show me pool details"

    Pools are used to limit parallelism for specific sets of tasks. This returns
    detailed real-time information about a specific pool's capacity and utilization.

    Returns detailed pool information including:
    - name: Name of the pool
    - slots: Total number of available slots in the pool
    - occupied_slots: Number of currently occupied slots (running + queued)
    - running_slots: Number of slots with currently running tasks
    - queued_slots: Number of slots with queued tasks waiting to run
    - open_slots: Number of available slots (slots - occupied_slots)
    - description: Human-readable description of the pool's purpose

    Args:
        pool_name: The name of the pool to get details for (e.g., "default_pool")

    Returns:
        JSON with complete details about the specified pool
    """
    return _get_pool_impl(pool_name=pool_name)


@mcp.tool()
def list_pools() -> str:
    """Get resource pools for managing task concurrency and resource allocation.

    Use this tool when the user asks about:
    - "What pools are configured?" or "List all pools"
    - "Show me the resource pools" or "What pools exist?"
    - "How many slots does pool X have?" or "What's the pool capacity?"
    - "Which pools are available?" or "What's the pool configuration?"

    Pools are used to limit parallelism for specific sets of tasks. Each pool
    has a certain number of slots, and tasks assigned to a pool will only run
    if there are available slots. This is useful for limiting concurrent access
    to resources like databases or external APIs.

    Returns pool information including:
    - name: Name of the pool
    - slots: Total number of available slots in the pool
    - occupied_slots: Number of currently occupied slots
    - running_slots: Number of slots with running tasks
    - queued_slots: Number of slots with queued tasks
    - open_slots: Number of available slots (slots - occupied_slots)
    - description: Human-readable description of the pool's purpose

    Returns:
        JSON with list of all pools and their current utilization
    """
    return _list_pools_impl()


@mcp.tool()
def list_plugins() -> str:
    """Get information about installed Airflow plugins.

    Use this tool when the user asks about:
    - "What plugins are installed?" or "List all plugins"
    - "Show me the plugins" or "Which plugins are enabled?"
    - "Is plugin X installed?" or "Do we have any custom plugins?"
    - "What's in the plugins directory?"

    Plugins extend Airflow functionality by adding custom operators, hooks,
    views, menu items, or other components. This returns information about
    all plugins discovered by Airflow's plugin system.

    Returns information about installed plugins including:
    - name: Name of the plugin
    - hooks: Custom hooks provided by the plugin
    - executors: Custom executors provided by the plugin
    - macros: Custom macros provided by the plugin
    - flask_blueprints: Flask blueprints for custom UI pages
    - appbuilder_views: Flask-AppBuilder views for admin interface
    - appbuilder_menu_items: Custom menu items in the UI

    Returns:
        JSON with list of all installed plugins and their components
    """
    return _list_plugins_impl()


@mcp.tool()
def list_providers() -> str:
    """Get information about installed Airflow provider packages.

    Use this tool when the user asks about:
    - "What providers are installed?" or "List all providers"
    - "What integrations are available?" or "Show me installed packages"
    - "Do we have the AWS provider?" or "Is the Snowflake provider installed?"
    - "What version of provider X is installed?"

    Returns information about installed provider packages including:
    - package_name: Name of the provider package (e.g., "apache-airflow-providers-amazon")
    - version: Version of the provider package
    - description: What the provider does
    - provider_info: Details about operators, hooks, and sensors included

    Returns:
        JSON with list of all installed provider packages and their details
    """
    return _list_providers_impl()
