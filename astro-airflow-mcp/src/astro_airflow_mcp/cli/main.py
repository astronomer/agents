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
from astro_airflow_mcp.cli import registry as registry_module
from astro_airflow_mcp.cli import runs as runs_module
from astro_airflow_mcp.cli import tasks as tasks_module
from astro_airflow_mcp.cli.api import api_command
from astro_airflow_mcp.cli.context import get_adapter, init_context
from astro_airflow_mcp.cli.output import output_error, output_json
from astro_airflow_mcp.cli.telemetry import track_command
from astro_airflow_mcp.config import legacy_default_path
from astro_airflow_mcp.config.loader import ConfigManager

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

    Configure connection using environment variables:
    - AIRFLOW_API_URL: Airflow webserver URL
    - AIRFLOW_USERNAME: Username for basic auth
    - AIRFLOW_PASSWORD: Password for basic auth
    - AIRFLOW_AUTH_TOKEN: Bearer token (takes precedence over basic auth)

    Or configure named instances in ~/.af/config.yaml and switch with:
        af instance use <name>

    Setting AIRFLOW_API_URL to an empty string signals "no Airflow is
    configured"; the CLI will exit with a clear error instead of falling back
    to the http://localhost:8080 default. This lets programmatic callers
    safely propagate "nothing is configured" without risking a query against
    whatever happens to be listening on localhost:8080.
    """
    # Set config path env var so all ConfigManager instances use it
    if config:
        os.environ["AF_CONFIG"] = config

    init_context()

    # Track command invocation (async, non-blocking)
    track_command()


@app.command()
def telemetry(
    action: Annotated[
        str | None,
        typer.Argument(help="Action: 'enable', 'disable', or omit to show current status"),
    ] = None,
) -> None:
    """Enable or disable anonymous telemetry collection.

    The af CLI collects anonymous usage telemetry to help improve the tool.
    No personally identifiable information is ever collected.

    With no argument, shows the current telemetry status.
    Use 'enable' or 'disable' to change the setting.

    Telemetry can also be disabled via the AF_TELEMETRY_DISABLED=1 environment variable.
    """
    try:
        manager = ConfigManager()

        if action is None:
            config = manager.load()
            status = "enabled" if config.telemetry.enabled else "disabled"
            output_json({"telemetry": status})
            return

        action_lower = action.lower()
        if action_lower == "disable":
            manager.set_telemetry_disabled(True)
            output_json({"telemetry": "disabled"})
        elif action_lower == "enable":
            manager.set_telemetry_disabled(False)
            output_json({"telemetry": "enabled"})
        else:
            output_error(f"Unknown action '{action}'. Use 'enable' or 'disable'.")
    except Exception as e:
        output_error(str(e))


@app.command()
def migrate() -> None:
    """Migrate ~/.af/config.yaml → ~/.astro/config.yaml.

    af originally stored its config at ``~/.af/config.yaml``. The new
    location ``~/.astro/config.yaml`` is shared with astro-cli, so a
    single ``astro login`` powers both tools and ``af`` can sit next to
    astro-cli's project config in ``.astro/config.yaml``.

    This command:
      1. Reads ``~/.af/config.yaml`` if present.
      2. Merges its instances/current-instance/telemetry into
         ``~/.astro/config.yaml``, preserving any astro-cli content.
      3. Renames the old file to ``~/.af/config.yaml.bak``.

    Idempotent — re-runs are safe and report "nothing to migrate".
    """
    legacy_path = legacy_default_path()
    new_manager = ConfigManager()  # default path: ~/.astro/config.yaml

    if not legacy_path.is_file():
        if new_manager.config_path.is_file():
            output_json(
                {
                    "status": "already-migrated",
                    "config": str(new_manager.config_path),
                }
            )
        else:
            output_json({"status": "nothing-to-migrate"})
        return

    try:
        # Read the legacy file directly (no fallback chain). We use the
        # same ConfigManager primitive load+save the implicit fallback
        # uses, so the migration result is byte-equivalent to what would
        # eventually happen on the next save() call.
        legacy_manager = ConfigManager(config_path=legacy_path)
        legacy_config = legacy_manager.load(create_default_if_missing=False)

        # save() merges af-owned keys into whatever astro-cli has already
        # written to the new path; foreign keys (project, contexts, etc.)
        # are preserved.
        new_manager.save(legacy_config)

        # Preserve a backup so users can roll back if something looks
        # wrong. Find the first available .bak slot.
        backup = legacy_path.parent / (legacy_path.name + ".bak")
        i = 1
        while backup.exists():
            backup = legacy_path.parent / f"{legacy_path.name}.bak.{i}"
            i += 1
        legacy_path.rename(backup)

        output_json(
            {
                "status": "migrated",
                "from": str(legacy_path),
                "to": str(new_manager.config_path),
                "backup": str(backup),
            }
        )
    except Exception as e:
        output_error(str(e))


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
app.add_typer(instances.app, name="instances", hidden=True)  # Alias for "instance"
app.add_typer(instances.app, name="inst", hidden=True)  # Short alias for "instance"
app.add_typer(registry_module.app, name="registry", help="Query the Airflow Provider Registry")


def cli_main() -> None:
    """Entry point for the CLI."""
    app()
