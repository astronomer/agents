"""Segment analytics tracking for af CLI."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess  # nosec B404 - subprocess is needed for fire-and-forget telemetry
import sys
import uuid
from pathlib import Path

# Segment write keys
SEGMENT_WRITE_KEY_DEV = "Aeudw5dvteD7FmGkZXvYGXWm896bx32V"
SEGMENT_WRITE_KEY_PROD = "E8HOxt5Mg033HsQ32fnOnttOLoDeFdzl"


def _is_dev_install() -> bool:
    """Check if running from a local development install."""
    with contextlib.suppress(Exception):
        # Check if the package source lives inside a git repo,
        # which indicates a local dev environment (uv run, uv sync, uv tool install -e)
        source_dir = Path(__file__).resolve().parent
        for parent in source_dir.parents:
            if (parent / ".git").exists():
                return True
    return False


def _get_write_key() -> str:
    """Get the Segment write key, using dev key for local development."""
    # Env var override takes precedence
    if env_key := os.environ.get("AF_SEGMENT_WRITE_KEY"):
        return env_key

    if _is_dev_install():
        return SEGMENT_WRITE_KEY_DEV

    return SEGMENT_WRITE_KEY_PROD


SEGMENT_WRITE_KEY = _get_write_key()

# Environment variable to disable tracking
TRACKING_DISABLED_ENV = "AF_TRACKING_DISABLED"

# File to store anonymous user ID
ANONYMOUS_ID_FILE = Path.home() / ".af" / ".anonymous_id"

# Global state
_tracked = False


def _get_anonymous_id() -> str:
    """Get or create a persistent anonymous user ID."""
    try:
        if ANONYMOUS_ID_FILE.exists():
            value = ANONYMOUS_ID_FILE.read_text().strip()
            # Validate it looks like a UUID (36 chars: 8-4-4-4-12)
            if len(value) == 36:
                uuid.UUID(value)
                return value
    except (OSError, ValueError):
        pass

    # Generate new ID (also regenerates if existing file was invalid)
    anonymous_id = str(uuid.uuid4())

    # Persist it
    try:
        ANONYMOUS_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANONYMOUS_ID_FILE.write_text(anonymous_id)
    except OSError:
        pass  # Continue even if we can't persist

    return anonymous_id


def _is_tracking_disabled() -> bool:
    """Check if tracking is disabled via environment variable or config file."""
    # Environment variable takes precedence
    disabled = os.environ.get(TRACKING_DISABLED_ENV, "").lower()
    if disabled in ("1", "true", "yes"):
        return True

    # Check config file
    with contextlib.suppress(Exception):
        from astro_airflow_mcp.config.loader import ConfigManager

        config = ConfigManager().load()
        if config.tracking_disabled:
            return True

    return False


def _detect_invocation_context() -> tuple[str, str | None]:
    """Detect if running interactively or via an agent/automation.

    Returns:
        Tuple of (context, agent_name):
        - context: 'agent', 'ci', 'interactive', or 'non-interactive'
        - agent_name: specific agent/CI name if detected, None otherwise
    """
    # Check for known AI agent environment variables
    agent_env_vars = {
        "CLAUDECODE": "claude-code",
        "CLAUDE_CODE_ENTRYPOINT": "claude-code",
        "CURSOR_TRACE_ID": "cursor",
        "AIDER_MODEL": "aider",
        "CONTINUE_GLOBAL_DIR": "continue",
    }
    for var, agent_name in agent_env_vars.items():
        if os.environ.get(var):
            return ("agent", agent_name)

    # Check for CI/CD environments
    ci_env_vars = {
        "GITHUB_ACTIONS": "github-actions",
        "GITLAB_CI": "gitlab-ci",
        "JENKINS_URL": "jenkins",
        "CIRCLECI": "circleci",
        "CI": "ci-unknown",  # Generic CI flag, check last
    }
    for var, ci_name in ci_env_vars.items():
        if os.environ.get(var):
            return ("ci", ci_name)

    # Check if running in an interactive terminal
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ("interactive", None)

    return ("non-interactive", None)


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

    if _is_tracking_disabled():
        return

    if not SEGMENT_WRITE_KEY:
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

    payload = json.dumps(
        {
            "write_key": SEGMENT_WRITE_KEY,
            "anonymous_id": anonymous_id,
            "event": "CLI Command",
            "properties": properties,
        }
    )

    # Spawn a detached subprocess that sends the event and exits.
    # This way the CLI process exits immediately with no delay.
    script = (
        "import json, sys, analytics;"
        "d = json.loads(sys.stdin.read());"
        "c = analytics.Client(write_key=d['write_key'], sync_mode=True, send=True);"
        "c.track(anonymous_id=d['anonymous_id'], event=d['event'], properties=d['properties'])"
    )

    with contextlib.suppress(Exception):
        proc = subprocess.Popen(  # nosec B603 - no untrusted input, script and args are hardcoded
            [sys.executable, "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        proc.stdin.write(payload.encode())
        proc.stdin.close()
