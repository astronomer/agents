"""Instance management CLI commands for af CLI."""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from astro_airflow_mcp.cli.output import output_error
from astro_airflow_mcp.config import ConfigError, ConfigManager

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
