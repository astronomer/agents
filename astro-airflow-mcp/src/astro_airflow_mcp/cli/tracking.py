"""Segment analytics tracking for af CLI."""

from __future__ import annotations

import contextlib
import os
import platform
import sys
import threading
import uuid
from pathlib import Path

import analytics

# Segment write key - prod key bundled, can be overridden via env var for dev
SEGMENT_WRITE_KEY_PROD = "Aeudw5dvteD7FmGkZXvYGXWm896bx32V"
SEGMENT_WRITE_KEY = os.environ.get("AF_SEGMENT_WRITE_KEY", SEGMENT_WRITE_KEY_PROD)

# Environment variable to disable tracking
TRACKING_DISABLED_ENV = "AF_TRACKING_DISABLED"

# File to store anonymous user ID
ANONYMOUS_ID_FILE = Path.home() / ".af" / ".anonymous_id"

# Timeout in seconds for the Segment API call
TRACKING_TIMEOUT = 3

# Global state
_client: analytics.Client | None = None
_tracked = False


def _get_anonymous_id() -> str:
    """Get or create a persistent anonymous user ID."""
    try:
        if ANONYMOUS_ID_FILE.exists():
            return ANONYMOUS_ID_FILE.read_text().strip()
    except OSError:
        pass

    # Generate new ID
    anonymous_id = str(uuid.uuid4())

    # Persist it
    try:
        ANONYMOUS_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANONYMOUS_ID_FILE.write_text(anonymous_id)
    except OSError:
        pass  # Continue even if we can't persist

    return anonymous_id


def _is_tracking_disabled() -> bool:
    """Check if tracking is disabled via environment variable."""
    disabled = os.environ.get(TRACKING_DISABLED_ENV, "").lower()
    return disabled in ("1", "true", "yes")


def _get_client() -> analytics.Client | None:
    """Get or create the Segment analytics client with a timeout."""
    global _client

    if _client is not None:
        return _client

    if not SEGMENT_WRITE_KEY:
        return None

    _client = analytics.Client(
        write_key=SEGMENT_WRITE_KEY,
        sync_mode=True,
        timeout=TRACKING_TIMEOUT,
        send=True,
    )

    return _client


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


def _send_track_event(
    anonymous_id: str,
    command_path: str,
    context: str,
    agent: str | None,
) -> None:
    """Send tracking event to Segment. Runs in background thread."""
    with contextlib.suppress(Exception):
        from astro_airflow_mcp import __version__

        client = _get_client()
        if client is None:
            return

        properties = {
            "command": command_path,
            "af_version": __version__,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "os": platform.system().lower(),  # darwin, linux, windows
            "os_version": platform.release(),
            "context": context,
        }
        if agent:
            properties["agent"] = agent

        client.track(
            anonymous_id=anonymous_id,
            event="CLI Command",
            properties=properties,
        )


def track_command() -> None:
    """Track a CLI command invocation.

    Uses sys.argv to determine the full command path.
    Runs in a daemon thread so it never blocks the CLI.
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

    # Gather data in main thread
    anonymous_id = _get_anonymous_id()
    command_path = _get_command_from_argv()
    context, agent = _detect_invocation_context()

    # Fire and forget in daemon thread - won't block CLI exit
    thread = threading.Thread(
        target=_send_track_event,
        args=(anonymous_id, command_path, context, agent),
        daemon=True,
    )
    thread.start()
