"""Configuration and system CLI commands."""

from typing import Annotated

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response
from astro_airflow_mcp.utils import filter_connection_passwords

app = typer.Typer(help="Configuration and system commands", no_args_is_help=True)


@app.command("show")
def get_airflow_config() -> None:
    """Get Airflow instance configuration and settings.

    Returns all Airflow configuration organized by sections
    (core, database, webserver, scheduler, etc.).
    """
    try:
        adapter = get_adapter()
        data = adapter.get_config()

        if "sections" in data:
            result = {"total_sections": len(data["sections"]), "sections": data["sections"]}
            output_json(result)
        else:
            output_json({"message": "No configuration found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("version")
def get_airflow_version() -> None:
    """Get version information for the Airflow instance.

    Returns the Airflow version string and git commit hash if available.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_version()
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("connections")
def list_connections(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of connections to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List connection configurations for external systems.

    Returns connection metadata including connection_id, conn_type,
    host, port, and schema. Passwords are NEVER returned.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_connections(limit=limit, offset=offset)

        if "connections" in data:
            connections = data["connections"]
            total_entries = data.get("total_entries", len(connections))

            # Filter out passwords for security
            filtered_connections = filter_connection_passwords(connections)

            result = {
                "total_connections": total_entries,
                "returned_count": len(filtered_connections),
                "connections": filtered_connections,
            }
            output_json(result)
        else:
            output_json({"message": "No connections found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("variables")
def list_variables(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of variables to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List all Airflow variables.

    Returns key-value configuration pairs. Sensitive variables may have
    their values masked.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_variables(limit=limit, offset=offset)

        if "variables" in data:
            result = wrap_list_response(data["variables"], "variables", data)
            output_json(result)
        else:
            output_json({"message": "No variables found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("variable")
def get_variable(
    key: Annotated[str, typer.Argument(help="The variable key to retrieve")],
) -> None:
    """Get a specific Airflow variable by key.

    Returns the variable's key, value, and description.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_variable(key)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("pools")
def list_pools(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of pools to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List resource pools for managing task concurrency.

    Returns pool information including slots, occupied_slots,
    running_slots, queued_slots, and open_slots.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_pools(limit=limit, offset=offset)

        if "pools" in data:
            result = wrap_list_response(data["pools"], "pools", data)
            output_json(result)
        else:
            output_json({"message": "No pools found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("pool")
def get_pool(
    name: Annotated[str, typer.Argument(help="The pool name to get details for")],
) -> None:
    """Get detailed information about a specific resource pool.

    Returns real-time information about the pool's capacity and utilization.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_pool(name)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("plugins")
def list_plugins(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of plugins to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List installed Airflow plugins.

    Returns information about custom plugins including hooks, executors,
    macros, and UI components they provide.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_plugins(limit=limit, offset=offset)

        if "plugins" in data:
            result = wrap_list_response(data["plugins"], "plugins", data)
            output_json(result)
        else:
            output_json({"message": "No plugins found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("providers")
def list_providers() -> None:
    """List installed Airflow provider packages.

    Returns information about provider packages including package_name,
    version, description, and included operators/hooks.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_providers()

        if "providers" in data:
            result = wrap_list_response(data["providers"], "providers", data)
            output_json(result)
        else:
            output_json({"message": "No providers found", "response": data})
    except Exception as e:
        output_error(str(e))
