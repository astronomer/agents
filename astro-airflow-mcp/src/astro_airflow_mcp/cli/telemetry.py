"""Telemetry for af CLI."""

from __future__ import annotations

import os
import platform
import sys

from astro_airflow_mcp.telemetry import (
    CLI_TELEMETRY_SOURCE as TELEMETRY_SOURCE,
)
from astro_airflow_mcp.telemetry import (
    TELEMETRY_API_URL,
    TELEMETRY_DEBUG_ENV,
    _detect_invocation_context,
    _get_anonymous_id,
    _is_telemetry_disabled,
    _send,
)

# Global state
_tracked = False


def _get_command_from_argv() -> str:
    """Extract the command path from sys.argv.

    For 'af dags list --limit 10', returns 'dags list'.
    Filters out options (args starting with -) and their values.
    """
    args = sys.argv[1:]  # Skip the program name
    command_parts: list[str] = []
    skip_next = False

    for arg in args:
        if skip_next:
            skip_next = False
            continue

        if arg.startswith("-"):
            # Check if this option takes a value (e.g., --config FILE)
            # Options with = are self-contained (--config=FILE)
            if "=" not in arg and arg in ("--config", "-c"):
                skip_next = True
            continue

        # This is a command/subcommand
        command_parts.append(arg)

    return " ".join(command_parts) if command_parts else "root"


def track_command() -> None:
    """Track a CLI command invocation.

    Uses sys.argv to determine the full command path.
    Spawns a detached subprocess so the CLI exits immediately.
    This function is idempotent - it only tracks once per invocation.
    """
    global _tracked

    # Only track once per CLI invocation
    if _tracked:
        return
    _tracked = True

    if _is_telemetry_disabled():
        return

    # Gather data in main process
    anonymous_id = _get_anonymous_id()
    command_path = _get_command_from_argv()
    context, agent = _detect_invocation_context()

    from astro_airflow_mcp import __version__

    properties = {
        "command": command_path,
        "af_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "context": context,
    }
    if agent:
        properties["agent"] = agent

    api_url = os.environ.get("AF_TELEMETRY_API_URL", TELEMETRY_API_URL)
    debug = os.environ.get(TELEMETRY_DEBUG_ENV, "").lower() in ("1", "true", "yes")

    body = {
        "source": TELEMETRY_SOURCE,
        "event": "CLI Command",
        "anonymousId": anonymous_id,
        "properties": properties,
    }

    _send(api_url, body, debug=debug)
