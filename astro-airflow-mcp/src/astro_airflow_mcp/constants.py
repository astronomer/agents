"""Shared constants for CLI and MCP server."""

import os
from pathlib import Path

# Terminal states for DAG runs (polling stops when reached)
TERMINAL_DAG_RUN_STATES = {"success", "failed", "upstream_failed"}

# Task states considered as failures
FAILED_TASK_STATES = {"failed", "upstream_failed"}

# Default pagination values
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0

# Default Airflow URL
DEFAULT_AIRFLOW_URL = "http://localhost:8080"

# Read-only mode environment variable
READ_ONLY_ENV_VAR = "AF_READ_ONLY"

# Astro CLI reverse proxy defaults
DEFAULT_PROXY_PORT = 6563


def get_astro_home() -> Path:
    """Return the Astro CLI home directory, respecting ASTRO_HOME env var."""
    return Path(os.environ.get("ASTRO_HOME", Path.home() / ".astro")).expanduser()


def get_proxy_routes_path() -> Path:
    """Return the path to the proxy routes.json file."""
    return get_astro_home() / "proxy" / "routes.json"


def get_astro_global_config_path() -> Path:
    """Return the path to the global Astro CLI config.yaml."""
    return get_astro_home() / "config.yaml"
