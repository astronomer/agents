"""Output formatting utilities for CLI."""

import json
import sys
from typing import Any


def output_json(data: Any, indent: int = 2) -> None:
    """Output data as formatted JSON to stdout.

    Args:
        data: Data to output (must be JSON-serializable)
        indent: Indentation level for pretty printing
    """
    print(json.dumps(data, indent=indent))


def output_error(message: str, exit_code: int = 1) -> None:
    """Output an error message to stderr and exit.

    Args:
        message: Error message to display
        exit_code: Exit code to use (default: 1)
    """
    error_data = {"error": message}
    print(json.dumps(error_data, indent=2), file=sys.stderr)
    raise SystemExit(exit_code)


def wrap_list_response(items: list[dict[str, Any]], key_name: str, data: dict[str, Any]) -> dict:
    """Wrap API list response with pagination metadata.

    Args:
        items: List of items from the API
        key_name: Name for the items key in response (e.g., 'dags', 'dag_runs')
        data: Original API response data (for total_entries)

    Returns:
        Dict with pagination metadata
    """
    total_entries = data.get("total_entries", len(items))
    return {
        f"total_{key_name}": total_entries,
        "returned_count": len(items),
        key_name: items,
    }
