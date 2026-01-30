"""Instance management CLI commands for af CLI."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from astro_airflow_mcp.astro.astro_cli import AstroCli, AstroCliError
from astro_airflow_mcp.cli.output import output_error
from astro_airflow_mcp.config import ConfigError, ConfigManager
from astro_airflow_mcp.discovery import (
    DiscoveredInstance,
    DiscoveryError,
    get_default_registry,
)
from astro_airflow_mcp.discovery.astro import (
    AstroDiscoveryBackend,
    AstroNotAuthenticatedError,
)

app = typer.Typer(help="Manage Airflow instances", no_args_is_help=True)
console = Console()


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


def _format_status(status: str | None) -> str:
    """Format status with color."""
    if not status:
        return "[dim]-[/dim]"
    if status == "HEALTHY":
        return "[green]HEALTHY[/green]"
    if status == "UNHEALTHY":
        return "[red]UNHEALTHY[/red]"
    return f"[yellow]{status}[/yellow]"


def _format_action(action: str) -> str:
    """Format action with color."""
    if action == "add":
        return "[green]add[/green]"
    if action == "overwrite":
        return "[yellow]overwrite[/yellow]"
    return f"[dim]{action}[/dim]"


def _truncate_url(url: str, max_len: int = 40) -> str:
    """Truncate URL for display."""
    if len(url) <= max_len:
        return url
    return url[: max_len - 3] + "..."


def _determine_action(
    instance: DiscoveredInstance, existing_names: set[str], overwrite: bool
) -> str:
    """Determine what action to take for an instance."""
    if instance.name in existing_names:
        return "overwrite" if overwrite else "skip (exists)"
    return "add"


@app.command("discover")
def discover_instances(
    all_workspaces: Annotated[
        bool,
        typer.Option("--all", "-a", help="Discover from all accessible Astro workspaces"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without making changes"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="Overwrite existing instances without prompting"),
    ] = False,
    prefix: Annotated[
        str | None,
        typer.Option("--prefix", "-p", help="Prefix for instance names (e.g., 'astro-')"),
    ] = None,
    backend: Annotated[
        list[str] | None,
        typer.Option("--backend", "-b", help="Specific backend(s) to use (default: all)"),
    ] = None,
    port: Annotated[
        list[int] | None,
        typer.Option("--port", help="Additional ports for local scan (repeatable)"),
    ] = None,
    wide: Annotated[
        bool,
        typer.Option("--wide", "-w", help="Deep scan ports 1024-65535 (local backend only)"),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", "-c", help="Concurrent connections for wide scan"),
    ] = 200,
) -> None:
    """Auto-discover Airflow instances and add them to the configuration.

    Uses multiple discovery backends:
    - astro: Discovers Astro deployments via the Astro CLI
    - local: Scans local ports for running Airflow instances

    Examples:
        af instance discover                    # Discover from all backends
        af instance discover --all              # Include all Astro workspaces
        af instance discover --backend astro    # Only use Astro backend
        af instance discover --backend local    # Only scan local ports
        af instance discover --port 9090        # Add custom port to scan
        af instance discover --wide             # Deep scan all ports 1024-65535
        af instance discover --dry-run          # Preview without changes
        af instance discover --prefix dev-      # Add prefix to names
    """
    # Get the registry and available backends
    registry = get_default_registry()

    # Show available backends
    available = registry.get_available_backends()
    if not available:
        output_error("No discovery backends available.")
        return

    # Validate requested backends
    if backend:
        for b in backend:
            if registry.get_backend(b) is None:
                output_error(f"Unknown backend: {b}")
                return
        backends_to_use = backend
    else:
        backends_to_use = [b.name for b in available]

    console.print(f"Discovery backends: {', '.join(backends_to_use)}\n")

    # Show Astro context if using astro backend
    if "astro" in backends_to_use:
        astro_backend = registry.get_backend("astro")
        if isinstance(astro_backend, AstroDiscoveryBackend):
            context = astro_backend.get_context()
            if context:
                console.print(f"Astro context: [bold]{context}[/bold]")
            scope = "all workspaces" if all_workspaces else "current workspace"
            console.print(f"Astro scope: {scope}\n")

    # Load existing config
    try:
        manager = ConfigManager()
        config = manager.load()
        existing_names = {inst.name for inst in config.instances}
    except ConfigError as e:
        output_error(f"Failed to load config: {e}")
        return

    # Prepare options for discovery
    discovery_options = {
        "all_workspaces": all_workspaces,
        "prefix": prefix,
        "create_tokens": False,  # Don't create tokens during discovery phase
    }

    # Add custom ports for local backend
    if port:
        from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend

        default_ports = LocalDiscoveryBackend.DEFAULT_PORTS
        discovery_options["ports"] = list(set(default_ports + port))

    # Run discovery
    console.print("Discovering instances...\n")
    all_instances: list[tuple[DiscoveredInstance, str]] = []  # (instance, action)

    for backend_name in backends_to_use:
        try:
            backend_obj = registry.get_backend(backend_name)
            if backend_obj is None:
                continue

            if not backend_obj.is_available():
                if backend_name == "astro":
                    console.print(
                        f"[yellow]Skipping {backend_name}:[/yellow] Astro CLI not installed"
                    )
                else:
                    console.print(f"[yellow]Skipping {backend_name}:[/yellow] Not available")
                continue

            # Use wide scan for local backend if requested
            if backend_name == "local" and wide:
                from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend

                if isinstance(backend_obj, LocalDiscoveryBackend):
                    instances = backend_obj.discover_wide(
                        host="localhost",
                        start_port=1024,
                        end_port=65535,
                        concurrency=concurrency,
                        verbose=True,
                    )
                else:
                    instances = backend_obj.discover(**discovery_options)
            else:
                instances = backend_obj.discover(**discovery_options)

            for inst in instances:
                action = _determine_action(inst, existing_names, overwrite)
                all_instances.append((inst, action))

        except AstroNotAuthenticatedError:
            console.print(
                f"[yellow]Skipping {backend_name}:[/yellow] Not authenticated. "
                "Run 'astro login' first."
            )
        except DiscoveryError as e:
            console.print(f"[yellow]Skipping {backend_name}:[/yellow] {e}")

    if not all_instances:
        console.print("No instances discovered.", style="dim")
        return

    console.print(f"Found {len(all_instances)} instance(s):\n")

    # Build table of discovered instances
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("NAME")
    table.add_column("SOURCE")
    table.add_column("URL")
    table.add_column("STATUS")
    table.add_column("ACTION")

    for inst, action in all_instances:
        status = inst.metadata.get("status") if inst.metadata else None
        table.add_row(
            inst.name,
            inst.source,
            _truncate_url(inst.url),
            _format_status(status),
            _format_action(action),
        )

    console.print(table)
    console.print()

    # Filter to instances we'll act on
    to_add = [(inst, action) for inst, action in all_instances if action in ("add", "overwrite")]

    if not to_add:
        console.print("No new instances to add.")
        return

    if dry_run:
        console.print(f"[dim]Dry run: would add {len(to_add)} instance(s)[/dim]")
        return

    # Add instances
    added_count = 0
    for inst, _ in to_add:
        console.print(f"Processing [bold]{inst.name}[/bold]...")

        token = inst.auth_token

        # For Astro instances without a token, try to create one
        if inst.source == "astro" and token is None:
            deployment_id = inst.metadata.get("deployment_id") if inst.metadata else None
            if deployment_id:
                token = _create_astro_token(deployment_id, inst.name, inst.url)
                if token is None:
                    continue

        # Add instance to config
        try:
            manager.add_instance(inst.name, inst.url, token=token)
            auth_info = "token" if token else "none"
            console.print(f"  [green]Added[/green] {inst.name} (auth: {auth_info})")
            added_count += 1
        except (ConfigError, ValueError) as e:
            console.print(f"  [red]Error:[/red] Failed to add instance: {e}")

    console.print()
    if added_count > 0:
        console.print(f"Successfully added {added_count} instance(s).")
    else:
        console.print("No instances were added.")


def _create_astro_token(deployment_id: str, instance_name: str, url: str) -> str | None:
    """Create an Astro deployment token.

    Args:
        deployment_id: The deployment ID
        instance_name: The instance name (for error messages)
        url: The instance URL (for error messages)

    Returns:
        Token value or None if creation failed
    """
    cli = AstroCli()

    try:
        token_exists = cli.token_exists(deployment_id, AstroCli.TOKEN_NAME)
    except AstroCliError as e:
        console.print(f"  [yellow]Warning:[/yellow] Could not check tokens: {e}")
        token_exists = False

    if token_exists:
        console.print(
            f"  [yellow]Warning:[/yellow] Token '{AstroCli.TOKEN_NAME}' already exists.\n"
            f"  Cannot retrieve existing token value. Either:\n"
            f"  - Delete the token in Astro UI and re-run discover\n"
            f"  - Manually add with: af instance add {instance_name} --url {url} --token <token>"
        )
        return None

    try:
        console.print(f"  Creating token '{AstroCli.TOKEN_NAME}'...")
        return cli.create_deployment_token(deployment_id, AstroCli.TOKEN_NAME)
    except AstroCliError as e:
        console.print(f"  [red]Error:[/red] Failed to create token: {e}")
        return None
