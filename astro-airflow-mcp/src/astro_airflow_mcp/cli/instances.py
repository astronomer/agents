"""Instance management CLI commands for af CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

import typer
from rich.console import Console
from rich.table import Table

from astro_airflow_mcp.cli.output import output_error
from astro_airflow_mcp.config import ConfigError, ConfigManager, LayeredConfig, Scope
from astro_airflow_mcp.discovery import (
    DiscoveredInstance,
    DiscoveryError,
    get_default_registry,
)
from astro_airflow_mcp.discovery.astro import AstroNotAuthenticatedError

if TYPE_CHECKING:
    from astro_airflow_mcp.config.models import Auth


def _resolve_scope_flag(global_: bool, project: bool, local: bool) -> Scope:
    """Combine mutually-exclusive ``--global`` / ``--project`` / ``--local``
    flags into a single ``Scope``. Default is ``AUTO``: LayeredConfig
    decides based on cwd."""
    n = sum(1 for f in (global_, project, local) if f)
    if n > 1:
        raise typer.BadParameter("--global, --project, and --local are mutually exclusive")
    if global_:
        return Scope.GLOBAL
    if project:
        return Scope.PROJECT_SHARED
    if local:
        return Scope.PROJECT_LOCAL
    return Scope.AUTO


_SCOPE_FLAG_HELP = {
    "global": "Write to global config (~/.astro/config.yaml)",
    "project": "Write to project-shared config (.astro/config.yaml, committed)",
    "local": "Write to project-local config (.astro/config.local.yaml, gitignored)",
}


def _describe_auth(auth: Auth | None, *, verbose: bool = False) -> str:
    """Render an Auth value for `instance list` / `instance current` rows.

    ``verbose`` adds the ``(<context>)`` suffix used by ``instance current``.
    """
    if auth is None:
        return "none"
    if auth.kind == "astro_pat":
        if verbose:
            return f"astro pat ({auth.context or 'active context'})"
        return "astro pat"
    if auth.token:
        return "token"
    return "basic"


app = typer.Typer(help="Manage Airflow instances", no_args_is_help=True)
console = Console()


@app.command("list")
def list_instances() -> None:
    """List all configured instances."""
    try:
        layered = LayeredConfig()
        rows = layered.list_instances_with_scope()
        current = layered.get_current_instance()

        if not rows:
            console.print("No instances configured.", style="dim")
            console.print(
                "\nAdd one with: af instance add <name> --url <url> --username <user> --password <pass>",
                style="dim",
            )
            return

        table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        table.add_column("", width=1)  # Current marker
        table.add_column("NAME")
        table.add_column("SCOPE")
        table.add_column("SOURCE")
        table.add_column("URL")
        table.add_column("AUTH")

        for inst, scope in rows:
            marker = "*" if inst.name == current else ""
            table.add_row(
                marker,
                inst.name,
                scope.value,
                inst.source or "-",
                inst.url,
                _describe_auth(inst.auth),
            )

        console.print(table)
    except ConfigError as e:
        output_error(str(e))


@app.command("current")
def current_instance() -> None:
    """Show the current instance."""
    try:
        layered = LayeredConfig()
        current = layered.get_current_instance()

        if current is None:
            console.print("No current instance set.", style="dim")
            console.print("\nSet one with: af instance use <name>", style="dim")
            return

        instance = layered.get_instance(current)
        if instance:
            console.print(f"Current instance: [bold]{current}[/bold]")
            console.print(f"URL: {instance.url}")
            console.print(f"Auth: {_describe_auth(instance.auth, verbose=True)}")
    except ConfigError as e:
        output_error(str(e))


@app.command("use")
def use_instance(
    name: Annotated[str | None, typer.Argument(help="Name of the instance to switch to")] = None,
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Switch to a different instance.

    If no name is provided, an interactive menu will be shown.

    By default writes ``current-instance`` to project-local config when
    in a project (so each developer can target a different deployment
    without conflicting commits) and to global config otherwise.
    """
    try:
        scope = _resolve_scope_flag(global_scope, project_scope, local_scope)
        layered = LayeredConfig()

        # If no name provided, show interactive selector over the merged view.
        if name is None:
            from simple_term_menu import TerminalMenu

            instances = layered.list_instances()
            if not instances:
                console.print("No instances configured.", style="dim")
                console.print(
                    "\nAdd one with: af instance add <name> --url <url>",
                    style="dim",
                )
                return

            instance_names = [inst.name for inst in instances]
            cursor_index = 0
            current = layered.get_current_instance()
            if current and current in instance_names:
                cursor_index = instance_names.index(current)

            menu = TerminalMenu(
                instance_names,
                title="Select instance:",
                cursor_index=cursor_index,
            )
            choice_index = menu.show()

            if choice_index is None:  # User pressed Escape
                console.print("Cancelled.", style="dim")
                return

            name = instance_names[cast("int", choice_index)]

        target = layered.use_instance(name, scope=scope)
        console.print(
            f"Switched to instance [bold]{name}[/bold] ([dim]{target.value}[/dim])",
            highlight=False,
        )
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
    no_verify_ssl: Annotated[
        bool,
        typer.Option("--no-verify-ssl", help="Disable SSL certificate verification"),
    ] = False,
    ca_cert: Annotated[
        str | None,
        typer.Option("--ca-cert", help="Path to custom CA certificate bundle"),
    ] = None,
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Add or update an Airflow instance.

    Auth is optional. Provide --username and --password for basic auth,
    or --token for token auth. Omit auth options for open instances.

    By default writes to project-shared config when in a project, else
    global. Project-shared is committed by default — prefer
    ``${ENV_VAR}`` interpolation or ``--local`` for secrets you don't
    want in git.
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

    if no_verify_ssl and ca_cert:
        output_error("Cannot provide both --no-verify-ssl and --ca-cert")
        return

    try:
        scope = _resolve_scope_flag(global_scope, project_scope, local_scope)
        layered = LayeredConfig()
        is_update = layered.get_instance(name) is not None
        target = layered.add_instance(
            name,
            url,
            username=username,
            password=password,
            token=token,
            source="manual",
            verify_ssl=not no_verify_ssl,
            ca_cert=ca_cert,
            scope=scope,
        )

        action = "Updated" if is_update else "Added"
        if has_token:
            auth_type = "token"
        elif has_basic:
            auth_type = "basic"
        else:
            auth_type = "none"
        console.print(f"{action} instance [bold]{name}[/bold] ([dim]{target.value}[/dim])")
        console.print(f"URL: {url}")
        console.print(f"Auth: {auth_type}")
        if no_verify_ssl:
            console.print("SSL verification: [yellow]disabled[/yellow]")
        if ca_cert:
            console.print(f"CA cert: {ca_cert}")
    except (ConfigError, ValueError) as e:
        output_error(str(e))


@app.command("delete")
def delete_instance(
    name: Annotated[str, typer.Argument(help="Name of the instance to delete")],
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Delete an instance.

    By default deletes from the most-specific scope that has the name
    (project-local, then project-shared, then global). Same-named
    instances in less-specific scopes are kept; rerun delete to peel
    them off one at a time, or use a scope flag to target one directly.
    """
    try:
        scope = _resolve_scope_flag(global_scope, project_scope, local_scope)
        target = LayeredConfig().delete_instance(name, scope=scope)
        console.print(f"Deleted instance [bold]{name}[/bold] ([dim]{target.value}[/dim])")
    except (ConfigError, ValueError) as e:
        output_error(str(e))


@app.command("show")
def show_instance(
    name: Annotated[str, typer.Argument(help="Name of the instance to show")],
) -> None:
    """Show details for an instance, including which file it came from.

    Mirrors ``git config --show-origin`` — useful for answering "where
    is this instance defined?" when the same name lives in multiple
    scopes (the most-specific wins).
    """
    try:
        layered = LayeredConfig()
        found = layered.find_instance(name)
        if found is None:
            output_error(f"Instance '{name}' not found")
            return
        instance, scope, file_path = found

        console.print(f"Instance: [bold]{name}[/bold]")
        console.print(f"Scope: [dim]{scope.value}[/dim] ({file_path})")
        console.print(f"URL: {instance.url}")
        console.print(f"Auth: {_describe_auth(instance.auth, verbose=True)}")
        if instance.auth and instance.auth.deployment_id:
            console.print(f"Deployment ID: {instance.auth.deployment_id}")
        if instance.source:
            console.print(f"Source: {instance.source}")
        if not instance.verify_ssl:
            console.print("SSL verification: [yellow]disabled[/yellow]")
        if instance.ca_cert:
            console.print(f"CA cert: {instance.ca_cert}")
    except ConfigError as e:
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


def _format_discovered_auth(inst: DiscoveredInstance) -> str:
    """Render the auth column for the discovery table (rich-markup variant)."""
    if inst.auth_kind == "astro_pat":
        return "[cyan]astro pat[/cyan]"
    if inst.auth_kind == "token" or inst.auth_token:
        return "token"
    if inst.auth_kind == "basic":
        return "basic"
    return "[dim]none[/dim]"


def _display_and_add_instances(
    all_instances: list[tuple[DiscoveredInstance, str]],
    layered: LayeredConfig,
    dry_run: bool,
    scope: Scope = Scope.AUTO,
) -> None:
    """Display discovered instances and add them to config.

    Astro-source instances are added with ``auth.kind="astro_pat"``: af
    resolves the user's ``astro login`` session at request time. No
    deployment tokens are minted.

    ``scope`` selects the target file. AUTO writes to project-shared
    when in a project (so ``af instance discover`` populates the
    committable project inventory), else global.
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
    table.add_column("AUTH")
    table.add_column("STATUS")
    table.add_column("ACTION")

    for inst, action in all_instances:
        status = inst.metadata.get("status") if inst.metadata else None
        table.add_row(
            inst.name,
            inst.source,
            _truncate_url(inst.url),
            _format_discovered_auth(inst),
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
    target_scope: Scope | None = None
    for inst, _ in to_add:
        console.print(f"Processing [bold]{inst.name}[/bold]...")

        try:
            if inst.auth_kind == "astro_pat":
                deployment_id = inst.metadata.get("deployment_id") if inst.metadata else None
                target_scope = layered.add_instance(
                    inst.name,
                    inst.url,
                    kind="astro_pat",
                    context=inst.astro_context,
                    deployment_id=deployment_id,
                    source=inst.source,
                    scope=scope,
                )
                auth_info = f"astro pat ({inst.astro_context or 'active context'})"
            elif inst.auth_token:
                target_scope = layered.add_instance(
                    inst.name, inst.url, token=inst.auth_token, source=inst.source, scope=scope
                )
                auth_info = "token"
            else:
                target_scope = layered.add_instance(
                    inst.name, inst.url, source=inst.source, scope=scope
                )
                auth_info = "none"
            console.print(f"  [green]Added[/green] {inst.name} (auth: {auth_info})")
            added_count += 1
        except (ConfigError, ValueError) as e:
            console.print(f"  [red]Error:[/red] Failed to add instance: {e}")

    console.print()
    if added_count > 0:
        suffix = f" to [dim]{target_scope.value}[/dim] config" if target_scope is not None else ""
        console.print(f"Successfully added {added_count} instance(s){suffix}.")
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
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Discover from all available backends.

    For backend-specific options, use subcommands:
        af instance discover astro    # Astro-specific options
        af instance discover local    # Local-specific options
    """
    # If a subcommand was invoked, skip the callback logic
    if ctx.invoked_subcommand is not None:
        return

    write_scope = _resolve_scope_flag(global_scope, project_scope, local_scope)

    # Validate write scope before doing discovery work (which can hit
    # the Astro API or scan ports). Otherwise --project outside a
    # project would scan, then fail at write time.
    try:
        layered = LayeredConfig()
        layered.assert_writable(write_scope)
        existing_names = {inst.name for inst in layered.list_instances()}
    except ConfigError as e:
        output_error(str(e))
        return

    registry = get_default_registry()
    available = registry.get_available_backends()

    if not available:
        output_error("No discovery backends available.")
        return

    backends_to_use = [b.name for b in available]
    console.print(f"Discovery backends: {', '.join(backends_to_use)}\n")

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

            instances = backend_obj.discover()
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

    _display_and_add_instances(all_instances, layered, dry_run, scope=write_scope)


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
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Discover Astro deployments via the Astro CLI.

    Examples:
        af instance discover astro                  # Current workspace only
        af instance discover astro --all-workspaces # All accessible workspaces
    """
    write_scope = _resolve_scope_flag(global_scope, project_scope, local_scope)

    # Validate write scope before hitting the Astro API.
    try:
        layered = LayeredConfig()
        layered.assert_writable(write_scope)
        existing_names = {inst.name for inst in layered.list_instances()}
    except ConfigError as e:
        output_error(str(e))
        return

    registry = get_default_registry()
    backend = registry.get_backend("astro")

    if backend is None:
        output_error("Astro backend not available.")
        return

    if not backend.is_available():
        output_error("Astro CLI is not installed. Install with: brew install astro")
        return

    # Show context info
    get_context = getattr(backend, "get_context", None)
    if callable(get_context):
        context = get_context()
        if context:
            console.print(f"Astro context: [bold]{context}[/bold]")
    discovery_scope = "all workspaces" if all_workspaces else "current workspace"
    console.print(f"Scope: {discovery_scope}\n")

    console.print("Discovering Astro deployments...\n")

    try:
        instances = backend.discover(all_workspaces=all_workspaces)
        all_instances = [
            (inst, _determine_action(inst, existing_names, overwrite)) for inst in instances
        ]
    except AstroNotAuthenticatedError:
        output_error("Not authenticated with Astro. Run 'astro login' first.")
        return
    except DiscoveryError as e:
        output_error(f"Discovery failed: {e}")
        return

    _display_and_add_instances(all_instances, layered, dry_run, scope=write_scope)


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
    global_scope: Annotated[
        bool, typer.Option("--global", help=_SCOPE_FLAG_HELP["global"])
    ] = False,
    project_scope: Annotated[
        bool, typer.Option("--project", help=_SCOPE_FLAG_HELP["project"])
    ] = False,
    local_scope: Annotated[bool, typer.Option("--local", help=_SCOPE_FLAG_HELP["local"])] = False,
) -> None:
    """Discover local Airflow instances by scanning ports.

    Examples:
        af instance discover local         # Scan common Airflow ports
        af instance discover local --scan  # Deep scan all ports 1024-65535
    """
    from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend

    write_scope = _resolve_scope_flag(global_scope, project_scope, local_scope)

    # Validate write scope before scanning ports.
    try:
        layered = LayeredConfig()
        layered.assert_writable(write_scope)
        existing_names = {inst.name for inst in layered.list_instances()}
    except ConfigError as e:
        output_error(str(e))
        return

    registry = get_default_registry()
    backend = registry.get_backend("local")

    if backend is None or not isinstance(backend, LocalDiscoveryBackend):
        output_error("Local backend not available.")
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

    _display_and_add_instances(all_instances, layered, dry_run, scope=write_scope)
