"""Instance management CLI commands for af CLI."""

from __future__ import annotations

import re
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from astro_airflow_mcp.cli.output import output_error
from astro_airflow_mcp.config import ConfigError, ConfigManager
from astro_airflow_mcp.astro.astro_cli import (
    AstroCli,
    AstroCliError,
    AstroCliNotAuthenticatedError,
    AstroDeployment,
)

app = typer.Typer(help="Manage Airflow instances", no_args_is_help=True)
console = Console()


def _generate_instance_name(deployment: AstroDeployment, prefix: str | None = None) -> str:
    """Generate an instance name from deployment info.

    Format: {prefix}{workspace}-{deployment-name}
    Normalizes to lowercase with hyphens.
    """
    # Normalize workspace and deployment names
    workspace = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.workspace_name.lower()).strip("-")
    name = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.name.lower()).strip("-")

    # Handle empty workspace name
    instance_name = name if not workspace else f"{workspace}-{name}"

    if prefix:
        instance_name = f"{prefix}{instance_name}"

    return instance_name


@app.command("list")
def list_instances() -> None:
    """List all configured instances."""
    try:
        manager = ConfigManager()
        config = manager.load()

        if not config.instances:
            console.print("No instances configured.", style="dim")
            console.print(
                "\nAdd one with: af instance add <name> --url <url> --username <user> --password <pass>",
                style="dim",
            )
            return

        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("", width=1)  # Current marker
        table.add_column("NAME")
        table.add_column("URL")
        table.add_column("AUTH")

        for inst in config.instances:
            marker = "*" if inst.name == config.current_instance else ""
            if inst.auth is None:
                auth = "none"
            elif inst.auth.token:
                auth = "token"
            else:
                auth = "basic"
            table.add_row(marker, inst.name, inst.url, auth)

        console.print(table)
    except ConfigError as e:
        output_error(str(e))


@app.command("current")
def current_instance() -> None:
    """Show the current instance."""
    try:
        manager = ConfigManager()
        current = manager.get_current_instance()

        if current is None:
            console.print("No current instance set.", style="dim")
            console.print("\nSet one with: af instance use <name>", style="dim")
            return

        config = manager.load()
        instance = config.get_instance(current)
        if instance:
            console.print(f"Current instance: [bold]{current}[/bold]")
            console.print(f"URL: {instance.url}")
            if instance.auth is None:
                console.print("Auth: none")
            elif instance.auth.token:
                console.print("Auth: token")
            else:
                console.print("Auth: basic")
    except ConfigError as e:
        output_error(str(e))


@app.command("use")
def use_instance(
    name: Annotated[str, typer.Argument(help="Name of the instance to switch to")],
) -> None:
    """Switch to a different instance."""
    try:
        manager = ConfigManager()
        manager.use_instance(name)
        console.print(f"Switched to instance [bold]{name}[/bold]")
    except (ConfigError, ValueError) as e:
        output_error(str(e))


@app.command("add")
def add_instance(
    name: Annotated[str, typer.Argument(help="Name for the instance")],
    url: Annotated[str, typer.Option("--url", "-u", help="Airflow API URL")],
    username: Annotated[
        str | None,
        typer.Option("--username", "-U", help="Username for basic authentication"),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", "-P", help="Password for basic authentication"),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", "-t", help="Bearer token (can use ${ENV_VAR} syntax)"),
    ] = None,
) -> None:
    """Add or update an Airflow instance.

    Auth is optional. Provide --username and --password for basic auth,
    or --token for token auth. Omit auth options for open instances.
    """
    has_basic = username is not None and password is not None
    has_token = token is not None
    has_partial_basic = (username is not None) != (password is not None)

    if has_partial_basic:
        output_error("Must provide both --username and --password for basic auth")
        return

    if has_basic and has_token:
        output_error("Cannot provide both username/password and token")
        return

    try:
        manager = ConfigManager()
        is_update = manager.load().get_instance(name) is not None
        manager.add_instance(name, url, username=username, password=password, token=token)

        action = "Updated" if is_update else "Added"
        if has_token:
            auth_type = "token"
        elif has_basic:
            auth_type = "basic"
        else:
            auth_type = "none"
        console.print(f"{action} instance [bold]{name}[/bold]")
        console.print(f"URL: {url}")
        console.print(f"Auth: {auth_type}")
    except (ConfigError, ValueError) as e:
        output_error(str(e))


@app.command("delete")
def delete_instance(
    name: Annotated[str, typer.Argument(help="Name of the instance to delete")],
) -> None:
    """Delete an instance."""
    try:
        manager = ConfigManager()
        manager.delete_instance(name)
        console.print(f"Deleted instance [bold]{name}[/bold]")
    except (ConfigError, ValueError) as e:
        output_error(str(e))


@app.command("discover")
def discover_instances(
    all_workspaces: Annotated[
        bool,
        typer.Option("--all", "-a", help="Discover from all accessible workspaces"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without making changes"),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing", "-s", help="Skip deployments that already exist in config"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="Overwrite existing instances without prompting"),
    ] = False,
    prefix: Annotated[
        str | None,
        typer.Option("--prefix", "-p", help="Prefix for instance names (e.g., 'astro-')"),
    ] = None,
) -> None:
    """Auto-discover Astro deployments and add them as instances.

    Uses the Astro CLI to discover deployments and creates deployment tokens
    for authentication. Requires the Astro CLI to be installed and authenticated.

    Examples:
        af instance discover              # Discover from current workspace
        af instance discover --all        # Discover from all workspaces
        af instance discover --dry-run    # Preview without changes
        af instance discover --prefix astro-  # Add 'astro-' prefix to names
    """
    cli = AstroCli()

    # Check if Astro CLI is installed
    if not cli.is_installed():
        output_error(
            "Astro CLI is not installed. Install it with: brew install astro\n"
            "Or visit: https://docs.astronomer.io/astro/cli/install-cli"
        )
        return

    # Show current context (best effort, don't fail if this doesn't work)
    context = cli.get_context()
    if context:
        console.print(f"Astro context: [bold]{context}[/bold]\n")

    # List deployments
    scope = "all workspaces" if all_workspaces else "current workspace"
    console.print(f"Discovering deployments ({scope})...\n")

    try:
        deployments_data = cli.list_deployments(all_workspaces=all_workspaces)
    except AstroCliNotAuthenticatedError:
        output_error("Not authenticated with Astro. Run 'astro login' first to authenticate.")
        return
    except AstroCliError as e:
        output_error(f"Failed to list deployments: {e}")
        return

    if not deployments_data:
        console.print("No deployments found.", style="dim")
        return

    # Load existing config
    try:
        manager = ConfigManager()
        config = manager.load()
        existing_names = {inst.name for inst in config.instances}
    except ConfigError as e:
        output_error(f"Failed to load config: {e}")
        return

    # Inspect each deployment to get full details
    deployments: list[AstroDeployment] = []
    for dep_data in deployments_data:
        dep_name = dep_data.get("name", "")
        dep_id = dep_data.get("deployment_id", "")

        if not dep_id:
            console.print(f"[yellow]Warning:[/yellow] No deployment ID for {dep_name}, skipping")
            continue

        try:
            deployment = cli.inspect_deployment(dep_id)
            deployments.append(deployment)
        except AstroCliError as e:
            console.print(f"[yellow]Warning:[/yellow] Could not inspect {dep_name}: {e}")

    if not deployments:
        console.print("No deployments could be inspected.", style="dim")
        return

    console.print(f"Found {len(deployments)} deployment(s):\n")

    # Build table of deployments with proposed actions
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("INSTANCE NAME")
    table.add_column("WORKSPACE")
    table.add_column("AIRFLOW URL")
    table.add_column("STATUS")
    table.add_column("ACTION")

    # Determine actions for each deployment
    actions: list[tuple[AstroDeployment, str, str]] = []  # (deployment, instance_name, action)

    for dep in deployments:
        instance_name = _generate_instance_name(dep, prefix)

        if instance_name in existing_names:
            if skip_existing:
                action = "skip (--skip-existing)"
            elif overwrite:
                action = "overwrite"
            else:
                action = "skip (exists)"
        else:
            action = "add"

        actions.append((dep, instance_name, action))

        # Determine status color
        status = dep.status
        if status == "HEALTHY":
            status_style = "[green]HEALTHY[/green]"
        elif status == "UNHEALTHY":
            status_style = "[red]UNHEALTHY[/red]"
        else:
            status_style = f"[yellow]{status}[/yellow]"

        # Determine action color
        if action == "add":
            action_style = "[green]add[/green]"
        elif action == "overwrite":
            action_style = "[yellow]overwrite[/yellow]"
        else:
            action_style = f"[dim]{action}[/dim]"

        # Truncate URL for display
        url_display = dep.airflow_api_url
        if len(url_display) > 40:
            url_display = url_display[:37] + "..."

        table.add_row(
            instance_name,
            dep.workspace_name or "-",
            url_display,
            status_style,
            action_style,
        )

    console.print(table)
    console.print()

    # Filter to only deployments we'll act on
    to_add = [(dep, name) for dep, name, action in actions if action in ("add", "overwrite")]

    if not to_add:
        console.print("No new instances to add.")
        return

    if dry_run:
        console.print(f"[dim]Dry run: would add {len(to_add)} instance(s)[/dim]")
        return

    # Add instances
    added_count = 0
    for dep, instance_name in to_add:
        console.print(f"Processing [bold]{instance_name}[/bold]...")

        # Check if token already exists
        try:
            token_exists = cli.token_exists(dep.id, AstroCli.TOKEN_NAME)
        except AstroCliError as e:
            console.print(f"  [yellow]Warning:[/yellow] Could not check tokens: {e}")
            token_exists = False

        if token_exists:
            # Token exists but we can't retrieve its value
            console.print(
                f"  [yellow]Warning:[/yellow] Token '{AstroCli.TOKEN_NAME}' already exists for this deployment.\n"
                f"  Cannot retrieve existing token value. Either:\n"
                f"  - Delete the token in Astro UI and re-run discover\n"
                f"  - Manually add with: af instance add {instance_name} --url {dep.airflow_api_url} --token <token>"
            )
            continue

        # Create new token
        try:
            console.print(f"  Creating token '{AstroCli.TOKEN_NAME}'...")
            token = cli.create_deployment_token(dep.id, AstroCli.TOKEN_NAME)
        except AstroCliError as e:
            console.print(f"  [red]Error:[/red] Failed to create token: {e}")
            continue

        # Add instance to config
        try:
            manager.add_instance(instance_name, dep.airflow_api_url, token=token)
            console.print(f"  [green]Added[/green] {instance_name}")
            added_count += 1
        except (ConfigError, ValueError) as e:
            console.print(f"  [red]Error:[/red] Failed to add instance: {e}")

    console.print()
    if added_count > 0:
        console.print(f"Successfully added {added_count} instance(s).")
    else:
        console.print("No instances were added.")
