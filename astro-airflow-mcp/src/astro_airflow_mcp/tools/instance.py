"""Instance management tools - list and switch Airflow instances."""

import json
from typing import Any

from astro_airflow_mcp.config import ConfigError, ConfigManager
from astro_airflow_mcp.logging import get_logger
from astro_airflow_mcp.server import configure, mcp

logger = get_logger(__name__)


def _get_config_manager() -> ConfigManager:
    """Get a ConfigManager instance."""
    return ConfigManager()


def _get_auth_type(instance: Any) -> str:
    """Determine auth type string from an instance.

    Args:
        instance: An Instance model with an optional auth field

    Returns:
        One of "none", "token", or "basic"
    """
    if instance.auth is None:
        return "none"
    if instance.auth.token:
        return "token"
    return "basic"


def _apply_instance_config(manager: ConfigManager, instance_name: str) -> None:
    """Apply an instance's configuration to the global MCP server adapter.

    Resolves the instance credentials and reconfigures the server's adapter
    manager to point to the new instance.

    Args:
        manager: ConfigManager to resolve instance from
        instance_name: Name of the instance to apply
    """
    resolved = manager.resolve_instance(instance_name)
    if resolved is None:
        raise ConfigError(f"Could not resolve instance '{instance_name}'")

    configure(
        url=resolved.url,
        auth_token=resolved.token,
        username=resolved.username,
        password=resolved.password,
    )

    logger.info("Switched MCP server to instance '%s' at %s", instance_name, resolved.url)


def _list_instances_impl() -> str:
    """Internal implementation for listing all configured Airflow instances.

    Returns:
        JSON string containing the list of instances with their metadata
    """
    try:
        manager = _get_config_manager()
        config = manager.load()

        instances: list[dict[str, Any]] = []
        for inst in config.instances:
            instances.append(
                {
                    "name": inst.name,
                    "url": inst.url,
                    "auth": _get_auth_type(inst),
                    "source": inst.source or "unknown",
                    "is_current": inst.name == config.current_instance,
                }
            )

        result: dict[str, Any] = {
            "total_instances": len(instances),
            "current_instance": config.current_instance,
            "instances": instances,
        }

        return json.dumps(result, indent=2)
    except ConfigError as e:
        return str(e)


def _switch_instance_impl(instance_name: str) -> str:
    """Internal implementation for switching the active Airflow instance.

    Args:
        instance_name: Name of the instance to switch to

    Returns:
        JSON string confirming the switch with the new instance details
    """
    try:
        manager = _get_config_manager()

        # Verify the instance exists
        config = manager.load()
        instance = config.get_instance(instance_name)
        if instance is None:
            available = [inst.name for inst in config.instances]
            return json.dumps(
                {
                    "error": f"Instance '{instance_name}' not found",
                    "available_instances": available,
                    "hint": "Use list_instances to see all available instances",
                },
                indent=2,
            )

        # Persist the switch in config
        manager.use_instance(instance_name)

        # Reconfigure the MCP server's adapter
        _apply_instance_config(manager, instance_name)

        result: dict[str, Any] = {
            "switched": True,
            "instance": {
                "name": instance.name,
                "url": instance.url,
                "auth": _get_auth_type(instance),
                "source": instance.source or "unknown",
            },
            "message": f"Successfully switched to '{instance_name}'. All subsequent Airflow operations will target {instance.url}",
        }

        return json.dumps(result, indent=2)
    except ConfigError as e:
        return str(e)
    except Exception as e:
        return json.dumps(
            {
                "switched": False,
                "error": str(e),
                "message": "Failed to switch instance. The previous instance remains active.",
            },
            indent=2,
        )


# =============================================================================
# MCP TOOL WRAPPERS
# =============================================================================


@mcp.tool()
def list_instances() -> str:
    """List all configured Airflow instances and show which one is active.

    Use this tool when the user asks about:
    - "What Airflow instances are configured?" or "Show me my deployments"
    - "Which Airflow environments are available?" or "List my instances"
    - "What deployments can I connect to?"
    - "Which instance am I connected to?"

    Returns information about all configured instances including:
    - name: Unique identifier for this instance
    - url: Base URL of the Airflow webserver
    - auth: Authentication type (none, basic, token)
    - source: How the instance was discovered (manual, astro, local)
    - is_current: Whether this is the currently active instance

    Returns:
        JSON with list of all configured Airflow instances
    """
    return _list_instances_impl()


@mcp.tool()
def switch_instance(instance_name: str) -> str:
    """Switch the active Airflow instance to a different deployment.

    USE THIS TOOL when you need to connect to a different Airflow environment.
    This changes which Airflow instance all subsequent tool calls will target.

    Use this tool when the user asks about:
    - "Switch to production" or "Connect to staging"
    - "Use the dev Airflow" or "Change to instance X"
    - "I want to check the production environment"
    - "Switch deployment" or "Change Airflow instance"

    After switching, all Airflow tools (list_dags, explore_dag, etc.) will
    operate against the newly selected instance.

    Args:
        instance_name: Name of the instance to switch to (use list_instances to see available names)

    Returns:
        JSON confirming the switch with the new instance details
    """
    return _switch_instance_impl(instance_name=instance_name)
