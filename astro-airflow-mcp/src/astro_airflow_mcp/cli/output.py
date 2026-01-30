"""Output formatting utilities for CLI."""

import json
import sys
from typing import Any

# Re-export wrap_list_response from shared utils for backwards compatibility
from astro_airflow_mcp.utils import wrap_list_response

__all__ = ["output_error", "output_json", "wrap_list_response"]


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
