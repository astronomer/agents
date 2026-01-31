"""Main CLI application with Typer."""

import os
from typing import Annotated, Any

import typer

# Import subcommand modules - must be imported after app is defined
# to avoid circular imports, so we import them here and register below
from astro_airflow_mcp.cli import assets as assets_module
from astro_airflow_mcp.cli import config as config_module
from astro_airflow_mcp.cli import dags as dags_module
from astro_airflow_mcp.cli import instances
from astro_airflow_mcp.cli import runs as runs_module
from astro_airflow_mcp.cli import tasks as tasks_module
from astro_airflow_mcp.cli.api import api_command
from astro_airflow_mcp.cli.context import configure_context, get_adapter
from astro_airflow_mcp.cli.output import output_json

app = typer.Typer(
    name="af",
    help="CLI tool for interacting with Apache Airflow.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        from astro_airflow_mcp import __version__

        print(f"af version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    airflow_url: Annotated[
        str | None,
        typer.Option(
            "--airflow-url",
            "-u",
            envvar="AIRFLOW_API_URL",
            help="Airflow API URL (default: http://localhost:8080)",
        ),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option(
            "--username",
            envvar="AIRFLOW_USERNAME",
            help="Username for Airflow authentication",
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            envvar="AIRFLOW_PASSWORD",
            help="Password for Airflow authentication",
        ),
    ] = None,
    auth_token: Annotated[
        str | None,
        typer.Option(
            "--token",
            envvar="AIRFLOW_AUTH_TOKEN",
            help="Bearer token for Airflow authentication (takes precedence)",
        ),
    ] = None,
    instance: Annotated[
        str | None,
        typer.Option(
            "--instance",
            "-i",
            help="Use a specific instance from config file",
        ),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            envvar="AF_CONFIG",
            help="Path to config file (default: ~/.af/config.yaml)",
        ),
    ] = None,
    _version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
) -> None:
    """Airflow CLI - interact with Apache Airflow from the command line.

    Configure connection using environment variables or CLI options:
    - AIRFLOW_API_URL / --airflow-url
    - AIRFLOW_USERNAME / --username
    - AIRFLOW_PASSWORD / --password
    - AIRFLOW_AUTH_TOKEN / --token

    Or use a named instance from ~/.af/config.yaml:
    - --instance <name>
    """
    # Set config path env var so all ConfigManager instances use it
    if config:
        os.environ["AF_CONFIG"] = config

    configure_context(
        airflow_url=airflow_url,
        username=username,
        password=password,
        auth_token=auth_token,
        instance_name=instance,
    )


@app.command()
def health() -> None:
    """Get overall Airflow system health.

    Returns import errors, warnings, and DAG stats to give a quick
    health check of the Airflow system.
    """
    result: dict[str, Any] = {}
    adapter = get_adapter()

    # Get version info
    try:
        result["version"] = adapter.get_version()
    except Exception as e:
        result["version"] = {"error": str(e)}

    # Get import errors
    try:
        errors_data = adapter.list_import_errors(limit=100)
        import_errors = errors_data.get("import_errors", [])
        result["import_errors"] = {
            "count": len(import_errors),
            "errors": import_errors,
        }
    except Exception as e:
        result["import_errors"] = {"error": str(e)}

    # Get DAG warnings
    try:
        warnings_data = adapter.list_dag_warnings(limit=100)
        dag_warnings = warnings_data.get("dag_warnings", [])
        result["dag_warnings"] = {
            "count": len(dag_warnings),
            "warnings": dag_warnings,
        }
    except Exception as e:
        result["dag_warnings"] = {"error": str(e)}

    # Get DAG stats
    try:
        result["dag_stats"] = adapter.get_dag_stats()
    except Exception:
        result["dag_stats"] = {"available": False, "note": "dagStats endpoint not available"}

    # Calculate overall health status
    import_error_count = result.get("import_errors", {}).get("count", 0)
    warning_count = result.get("dag_warnings", {}).get("count", 0)

    if import_error_count > 0:
        result["overall_status"] = "unhealthy"
        result["status_reason"] = f"{import_error_count} import error(s) detected"
    elif warning_count > 0:
        result["overall_status"] = "warning"
        result["status_reason"] = f"{warning_count} DAG warning(s) detected"
    else:
        result["overall_status"] = "healthy"
        result["status_reason"] = "No import errors or warnings"

    output_json(result)


# Register subcommands (modules imported at top)
app.command("api")(api_command)
app.add_typer(dags_module.app, name="dags", help="DAG management commands")
app.add_typer(runs_module.app, name="runs", help="DAG run management commands")
app.add_typer(tasks_module.app, name="tasks", help="Task management commands")
app.add_typer(assets_module.app, name="assets", help="Asset/dataset management commands")
app.add_typer(config_module.app, name="config", help="Configuration and system commands")
app.add_typer(instances.app, name="instance", help="Instance management commands")


def cli_main() -> None:
    """Entry point for the CLI."""
    app()
