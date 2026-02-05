"""Segment analytics tracking for af CLI."""

from __future__ import annotations

import atexit
import contextlib
import os
import sys
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

# Global state
_initialized = False
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


def _init_analytics() -> None:
    """Initialize the Segment analytics client."""
    global _initialized

    if _initialized:
        return

    if not SEGMENT_WRITE_KEY:
        _initialized = True
        return

    # Configure analytics client
    analytics.write_key = SEGMENT_WRITE_KEY

    # Use async mode (events are batched and sent in background)
    analytics.send = True
    analytics.sync_mode = False

    # Flush on exit
    atexit.register(analytics.flush)

    _initialized = True


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

    _init_analytics()

    anonymous_id = _get_anonymous_id()
    command_path = _get_command_from_argv()

    # Track the event (suppress errors to never affect CLI operation)
    with contextlib.suppress(Exception):
        analytics.track(
            anonymous_id=anonymous_id,
            event="CLI Command",
            properties={
                "command": command_path,
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            },
        )
