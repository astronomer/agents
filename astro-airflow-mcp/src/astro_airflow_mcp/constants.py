"""Shared constants for CLI and MCP server."""

# Terminal states for DAG runs (polling stops when reached)
TERMINAL_DAG_RUN_STATES = {"success", "failed", "upstream_failed"}

# Task states considered as failures
FAILED_TASK_STATES = {"failed", "upstream_failed"}

# Default pagination values
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0

# Default Airflow URL
DEFAULT_AIRFLOW_URL = "http://localhost:8080"
