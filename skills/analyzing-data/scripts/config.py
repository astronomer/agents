"""Configuration utilities for the analyzing-data skill."""

import os
import sys
import warnings
from pathlib import Path

# When set and non-empty, this directory holds warehouse.yml, .env and
# warehouse.md instead of ~/.astro/agents, so concurrent sessions can each
# point at their own warehouses.
CONFIG_DIR_ENV_VAR = "ASTRO_AGENTS_CONFIG_DIR"

# Legacy path (deprecated)
_LEGACY_CONFIG_DIR = Path.home() / ".astro" / "ai" / "config"
# New path
_NEW_CONFIG_DIR = Path.home() / ".astro" / "agents"

_legacy_warning_shown = False


def _check_legacy_path() -> Path | None:
    """Check if legacy config path exists and warn user to migrate.

    Returns the legacy path if it exists and should be used, None otherwise.
    """
    global _legacy_warning_shown

    if _LEGACY_CONFIG_DIR.exists() and not _NEW_CONFIG_DIR.exists():
        if not _legacy_warning_shown:
            warnings.warn(
                f"Deprecated config path: {_LEGACY_CONFIG_DIR}\n"
                f"  Please move your config to: {_NEW_CONFIG_DIR}\n"
                f"  Run: mv ~/.astro/ai/config ~/.astro/agents",
                DeprecationWarning,
                stacklevel=3,
            )
            # Also print to stderr for CLI visibility
            print(
                "WARNING: Using deprecated config path ~/.astro/ai/config/\n"
                "  Please migrate: mv ~/.astro/ai/config ~/.astro/agents",
                file=sys.stderr,
            )
            _legacy_warning_shown = True
        return _LEGACY_CONFIG_DIR
    return None


def get_config_dir_override() -> Path | None:
    """Return ``ASTRO_AGENTS_CONFIG_DIR`` (``~`` expanded) if set and non-empty."""
    value = os.environ.get(CONFIG_DIR_ENV_VAR, "").strip()
    return Path(value).expanduser() if value else None


def warehouse_yml_hint() -> str:
    """Where warehouse.yml is expected, for messages: the override dir's when
    ``ASTRO_AGENTS_CONFIG_DIR`` is set, else the wording it always had."""
    override = get_config_dir_override()
    if override:
        return str(override / "warehouse.yml")
    return "~/.astro/agents/warehouse.yml"


def get_default_config_dir() -> Path:
    """The config directory with no override: ``~/.astro/agents``, or the
    legacy ``~/.astro/ai/config`` when only that exists.

    With an override set, the user's own ``.env`` and ``warehouse.md`` here
    are still read, after the override's.
    """
    legacy = _check_legacy_path()
    if legacy:
        return legacy
    return _NEW_CONFIG_DIR


def get_kernel_venv_dir() -> Path:
    """Get the path to the kernel virtual environment directory.

    Shared across sessions even when ``ASTRO_AGENTS_CONFIG_DIR`` is set: it
    holds only the Python environment, no warehouse state.
    """
    legacy = _check_legacy_path()
    if legacy:
        return legacy.parent / "kernel_venv"
    return _NEW_CONFIG_DIR / "kernel_venv"


def get_kernel_connection_file() -> Path:
    """Get the path to the kernel connection file.

    Follows ``ASTRO_AGENTS_CONFIG_DIR`` so each config dir gets its own
    kernel, which carries that dir's warehouse connection.
    """
    override = get_config_dir_override()
    if override:
        return override / "kernel.json"
    legacy = _check_legacy_path()
    if legacy:
        return legacy.parent / "kernel.json"
    return _NEW_CONFIG_DIR / "kernel.json"


def get_config_dir() -> Path:
    """Get the path to the config directory.

    ``ASTRO_AGENTS_CONFIG_DIR`` wins when set and non-empty (``~`` is
    expanded). Otherwise ``~/.astro/agents``, or the legacy
    ``~/.astro/ai/config`` when only that exists.
    """
    return get_config_dir_override() or get_default_config_dir()
