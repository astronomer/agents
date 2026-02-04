"""Instance management CLI commands for af CLI."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from astro_airflow_mcp.cli.output import output_error
from astro_airflow_mcp.config import ConfigError, ConfigManager
from astro_airflow_mcp.discovery import (
    DiscoveredInstance,
    DiscoveryError,
    DiscoveryRegistry,
    get_default_registry,
)
from astro_airflow_mcp.discovery.astro import (
    AstroDiscoveryBackend,
    AstroDiscoveryError,
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
        table.add_column("SOURCE")
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
            table.add_row(marker, inst.name, inst.source or "-", inst.url, auth)

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
    name: Annotated[str | None, typer.Argument(help="Name of the instance to switch to")] = None,
) -> None:
    """Switch to a different instance.

    If no name is provided, an interactive menu will be shown.
    """
    try:
        manager = ConfigManager()

        # If no name provided, show interactive selector
        if name is None:
            from simple_term_menu import TerminalMenu

            config = manager.load()
            if not config.instances:
                console.print("No instances configured.", style="dim")
                console.print(
                    "\nAdd one with: af instance add <name> --url <url>",
                    style="dim",
                )
                return

            instance_names = [inst.name for inst in config.instances]

            # Pre-select current instance if set
            cursor_index = 0
            if config.current_instance and config.current_instance in instance_names:
                cursor_index = instance_names.index(config.current_instance)

            menu = TerminalMenu(
                instance_names,
                title="Select instance:",
                cursor_index=cursor_index,
            )
            choice_index = menu.show()

            if choice_index is None:  # User pressed Escape
                console.print("Cancelled.", style="dim")
                return

            name = instance_names[choice_index]

        manager.use_instance(name)
        console.print(f"Switched to instance [bold]{name}[/bold]", highlight=False)
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
        manager.add_instance(
            name, url, username=username, password=password, token=token, source="manual"
        )

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


@app.command("reset")
def reset_instances(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Reset configuration to default (localhost only).

    Removes all configured instances and restores the default
    localhost instance at http://localhost:8080.
    """
    try:
        manager = ConfigManager()
        config = manager.load()

        if not config.instances:
            console.print("No instances to clean.", style="dim")
            return

        # Show what will be removed
        non_default = [i for i in config.instances if i.name != "localhost:8080"]
        if not non_default and len(config.instances) == 1:
            console.print("Already at default configuration.", style="dim")
            return

        console.print("This will remove the following instances:")
        for inst in config.instances:
            if inst.name == "localhost:8080":
                console.print(f"  [dim]{inst.name}[/dim] (will be reset)")
            else:
                console.print(f"  [red]{inst.name}[/red]")

        if not force:
            confirm = typer.confirm("\nProceed?")
            if not confirm:
                console.print("Cancelled.", style="dim")
                return

        # Reset to default
        default_config = manager._create_default_config()
        manager.save(default_config)
        console.print("\nReset to default configuration.")
        console.print("  Instance: [bold]localhost:8080[/bold]")
        console.print("  URL: http://localhost:8080")

    except ConfigError as e:
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


def _display_and_add_instances(
    all_instances: list[tuple[DiscoveredInstance, str]],
    manager: ConfigManager,
    registry: DiscoveryRegistry,
    dry_run: bool,
) -> None:
    """Display discovered instances and add them to config.

    Args:
        all_instances: List of (instance, action) tuples
        manager: Config manager for adding instances
        registry: Discovery registry for getting backends
        dry_run: If True, preview without making changes
    """
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
            astro_backend = registry.get_backend("astro")
            if deployment_id and isinstance(astro_backend, AstroDiscoveryBackend):
                token = _create_astro_token(astro_backend, deployment_id, inst.name, inst.url)
                if token is None:
                    continue

        # Add instance to config
        try:
            manager.add_instance(inst.name, inst.url, token=token, source=inst.source)
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


# Discover subcommands
discover_app = typer.Typer(help="Auto-discover Airflow instances", no_args_is_help=False)
app.add_typer(discover_app, name="discover")


@discover_app.callback(invoke_without_command=True)
def discover_all(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without making changes"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="Overwrite existing instances"),
    ] = False,
) -> None:
    """Discover from all available backends.

    For backend-specific options, use subcommands:
        af instance discover astro    # Astro-specific options
        af instance discover local    # Local-specific options
    """
    # If a subcommand was invoked, skip the callback logic
    if ctx.invoked_subcommand is not None:
        return

    registry = get_default_registry()
    available = registry.get_available_backends()

    if not available:
        output_error("No discovery backends available.")
        return

    backends_to_use = [b.name for b in available]
    console.print(f"Discovery backends: {', '.join(backends_to_use)}\n")

    # Load existing config
    try:
        manager = ConfigManager()
        config = manager.load()
        existing_names = {inst.name for inst in config.instances}
    except ConfigError as e:
        output_error(f"Failed to load config: {e}")
        return

    console.print("Discovering instances...\n")
    all_instances: list[tuple[DiscoveredInstance, str]] = []

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

            instances = backend_obj.discover(create_tokens=False)
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

    _display_and_add_instances(all_instances, manager, registry, dry_run)


@discover_app.command("astro")
def discover_astro(
    all_workspaces: Annotated[
        bool,
        typer.Option("--all-workspaces", "-a", help="Discover from all accessible workspaces"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without making changes"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="Overwrite existing instances"),
    ] = False,
) -> None:
    """Discover Astro deployments via the Astro CLI.

    Examples:
        af instance discover astro                  # Current workspace only
        af instance discover astro --all-workspaces # All accessible workspaces
    """
    registry = get_default_registry()
    backend = registry.get_backend("astro")

    if backend is None:
        output_error("Astro backend not available.")
        return

    if not backend.is_available():
        output_error("Astro CLI is not installed. Install with: brew install astro")
        return

    if not isinstance(backend, AstroDiscoveryBackend):
        output_error("Invalid backend type.")
        return

    # Show context info
    context = backend.get_context()
    if context:
        console.print(f"Astro context: [bold]{context}[/bold]")
    scope = "all workspaces" if all_workspaces else "current workspace"
    console.print(f"Scope: {scope}\n")

    # Load existing config
    try:
        manager = ConfigManager()
        config = manager.load()
        existing_names = {inst.name for inst in config.instances}
    except ConfigError as e:
        output_error(f"Failed to load config: {e}")
        return

    console.print("Discovering Astro deployments...\n")

    try:
        instances = backend.discover(all_workspaces=all_workspaces, create_tokens=False)
        all_instances = [
            (inst, _determine_action(inst, existing_names, overwrite)) for inst in instances
        ]
    except AstroNotAuthenticatedError:
        output_error("Not authenticated with Astro. Run 'astro login' first.")
        return
    except DiscoveryError as e:
        output_error(f"Discovery failed: {e}")
        return

    _display_and_add_instances(all_instances, manager, registry, dry_run)


@discover_app.command("local")
def discover_local(
    scan: Annotated[
        bool,
        typer.Option("--scan", "-s", help="Deep scan all ports 1024-65535"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Preview without making changes"),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-o", help="Overwrite existing instances"),
    ] = False,
) -> None:
    """Discover local Airflow instances by scanning ports.

    Examples:
        af instance discover local         # Scan common Airflow ports
        af instance discover local --scan  # Deep scan all ports 1024-65535
    """
    from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend

    registry = get_default_registry()
    backend = registry.get_backend("local")

    if backend is None or not isinstance(backend, LocalDiscoveryBackend):
        output_error("Local backend not available.")
        return

    # Load existing config
    try:
        manager = ConfigManager()
        config = manager.load()
        existing_names = {inst.name for inst in config.instances}
    except ConfigError as e:
        output_error(f"Failed to load config: {e}")
        return

    if scan:
        console.print("Deep scanning ports 1024-65535...\n")
        instances = backend.discover_wide(
            host="localhost",
            start_port=1024,
            end_port=65535,
            verbose=True,
        )
    else:
        console.print("Scanning common Airflow ports...\n")
        instances = backend.discover()

    all_instances = [
        (inst, _determine_action(inst, existing_names, overwrite)) for inst in instances
    ]

    _display_and_add_instances(all_instances, manager, registry, dry_run)


def _create_astro_token(
    backend: AstroDiscoveryBackend, deployment_id: str, instance_name: str, url: str
) -> str | None:
    """Create an Astro deployment token.

    Args:
        backend: The Astro discovery backend
        deployment_id: The deployment ID
        instance_name: The instance name (for error messages)
        url: The instance URL (for error messages)

    Returns:
        Token value or None if creation failed
    """
    if backend.token_exists(deployment_id):
        console.print(
            f"  [yellow]Warning:[/yellow] Token '{backend.TOKEN_NAME}' already exists.\n"
            f"  Cannot retrieve existing token value. Either:\n"
            f"  - Delete the token in Astro UI and re-run discover\n"
            f"  - Manually add with: af instance add {instance_name} --url {url} --token <token>"
        )
        return None

    try:
        console.print(f"  Creating token '{backend.TOKEN_NAME}'...")
        return backend.create_token(deployment_id)
    except AstroDiscoveryError as e:
        console.print(f"  [red]Error:[/red] {e}")
        return None
