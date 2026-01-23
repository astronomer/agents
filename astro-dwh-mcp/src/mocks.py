"""Mock response system for DRY_RUN mode with flow tracing.

Provides pattern-based mock responses for MCP tools, enabling
fast iteration on skill flows without hitting real warehouse.

Features:
- Pattern-based mock responses
- Flow tracing to JSON file (for Ralph Loop comparison)
- Early exit detection when real queries are executed

Usage:
    Set environment variables:
    - DRY_RUN_MODE=true
    - MOCK_RESPONSES_FILE=/path/to/mocks.yaml
    - FLOW_TRACE_FILE=/path/to/trace.json (logs all tool calls)

    Mock file format (YAML):
    ```yaml
    run_sql:
      - pattern: "OPERATOR.*ILIKE.*hitl"
        response: |
          shape: (3, 2)
          | OPERATOR | COUNT |
          | HITLOperator | 10 |
          | HITLBranchOperator | 5 |
    ```
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Global mock state
_mock_responses: dict[str, list[dict]] = {}
_mock_loaded: bool = False

# Flow trace state
_flow_trace: list[dict] = []
_trace_file: Path | None = None


def is_dry_run() -> bool:
    """Check if DRY_RUN mode is enabled."""
    return os.environ.get("DRY_RUN_MODE", "false").lower() == "true"


def get_mock_file_path() -> str | None:
    """Get the mock responses file path from environment."""
    return os.environ.get("MOCK_RESPONSES_FILE")


def get_trace_file_path() -> Path | None:
    """Get the flow trace file path from environment."""
    path = os.environ.get("FLOW_TRACE_FILE")
    if path:
        return Path(path)
    # Default trace file location
    if is_dry_run():
        return Path("/tmp/flow-trace.json")
    return None


def _init_trace() -> None:
    """Initialize trace file if configured."""
    global _trace_file
    _trace_file = get_trace_file_path()
    if _trace_file:
        _trace_file.parent.mkdir(parents=True, exist_ok=True)
        # Write initial trace structure
        _save_trace()
        logger.info(f"Flow tracing enabled: {_trace_file}")


def _save_trace() -> None:
    """Save current trace to file."""
    if _trace_file:
        trace_data = {
            "dry_run": is_dry_run(),
            "mock_file": get_mock_file_path(),
            "timestamp": datetime.now().isoformat(),
            "trace": _flow_trace,
        }
        _trace_file.write_text(json.dumps(trace_data, indent=2))


def log_tool_call(
    tool: str,
    action: str,
    details: dict[str, Any],
    is_mock: bool = True,
) -> None:
    """Log a tool call to the trace.

    Args:
        tool: Tool name (e.g., "run_sql", "list_schemas")
        action: Action type (e.g., "mock_response", "real_query")
        details: Additional details about the call
        is_mock: Whether this was a mock response or real query
    """
    global _flow_trace

    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool,
        "action": action,
        "is_mock": is_mock,
        **details,
    }
    _flow_trace.append(entry)
    _save_trace()

    # Log warning if real query executed in DRY_RUN mode
    if is_dry_run() and not is_mock:
        logger.warning(f"[EARLY_EXIT] Real query executed in DRY_RUN mode: {tool}")
        # Write early exit marker
        if _trace_file:
            exit_marker = _trace_file.with_suffix(".early_exit")
            exit_marker.write_text(
                json.dumps(
                    {
                        "reason": "real_query_in_dry_run",
                        "tool": tool,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            )


def check_early_exit() -> dict[str, Any] | None:
    """Check if early exit conditions are met.

    Returns:
        Dict with exit reason if should exit, None otherwise.
    """
    trace_file = get_trace_file_path()
    if not trace_file:
        return None

    exit_marker = trace_file.with_suffix(".early_exit")
    if exit_marker.exists():
        return json.loads(exit_marker.read_text())

    return None


def load_mocks(file_path: str | None = None) -> bool:
    """Load mock responses from YAML file.

    Args:
        file_path: Path to mock YAML file. If None, uses MOCK_RESPONSES_FILE env var.

    Returns:
        True if mocks were loaded successfully, False otherwise.
    """
    global _mock_responses, _mock_loaded

    if _mock_loaded:
        return True

    path_str = file_path or get_mock_file_path()
    if not path_str:
        logger.debug("No mock responses file configured")
        return False

    path = Path(path_str)
    if not path.exists():
        logger.warning(f"Mock responses file not found: {path}")
        return False

    try:
        # Import yaml only when needed (optional dependency)
        import yaml

        _mock_responses = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _mock_loaded = True
        logger.info(f"Loaded mock responses from {path}")

        # Initialize tracing
        _init_trace()

        return True
    except ImportError:
        logger.warning("PyYAML not installed, cannot load mock responses")
        return False
    except Exception as e:
        logger.warning(f"Failed to load mock responses: {e}")
        return False


def get_mock_response(query: str, tool: str = "run_sql") -> str:
    """Get mock response for a query based on pattern matching.

    Args:
        query: The query or input to match against patterns
        tool: The tool name (e.g., "run_sql", "list_tables")

    Returns:
        Mock response string, or a default message if no match
    """
    # Ensure mocks are loaded
    load_mocks()

    if tool not in _mock_responses:
        log_tool_call(tool, "no_mock_configured", {"query": query[:200]}, is_mock=True)
        return f"[DRY_RUN] No mock configured for tool: {tool}"

    mocks = _mock_responses[tool]
    if not isinstance(mocks, list):
        return f"[DRY_RUN] Invalid mock config for {tool}"

    for mock in mocks:
        pattern = mock.get("pattern", "")
        if not pattern:
            continue

        try:
            if re.search(pattern, query, re.IGNORECASE | re.DOTALL):
                response = mock.get("response", "[DRY_RUN] Empty response")
                log_tool_call(
                    tool,
                    "mock_response",
                    {
                        "pattern": pattern[:100],
                        "query": query[:200],
                    },
                    is_mock=True,
                )
                logger.debug(f"Mock match for {tool}: pattern={pattern[:50]}...")
                return response
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            continue

    # No match - return truncated query for debugging
    truncated = query[:200] + "..." if len(query) > 200 else query
    log_tool_call(tool, "no_pattern_match", {"query": truncated}, is_mock=True)
    return f"[DRY_RUN] No pattern match for {tool}:\n{truncated}"


def get_mock_list_schemas() -> str:
    """Get mock response for list_schemas."""
    return get_mock_response("list_schemas", "list_schemas")


def get_mock_list_tables(database: str, schema: str) -> str:
    """Get mock response for list_tables."""
    return get_mock_response(f"{database}.{schema}", "list_tables")


def get_mock_tables_info(database: str, schema: str, tables: list[str]) -> str:
    """Get mock response for get_tables_info."""
    query = f"{database}.{schema}: {', '.join(tables)}"
    return get_mock_response(query, "get_tables_info")


def clear_mocks() -> None:
    """Clear loaded mocks (useful for testing)."""
    global _mock_responses, _mock_loaded, _flow_trace
    _mock_responses = {}
    _mock_loaded = False
    _flow_trace = []


def get_mock_stats() -> dict[str, Any]:
    """Get statistics about loaded mocks."""
    return {
        "loaded": _mock_loaded,
        "file": get_mock_file_path(),
        "tools": list(_mock_responses.keys()),
        "pattern_counts": {tool: len(patterns) for tool, patterns in _mock_responses.items()},
    }


def get_flow_trace() -> list[dict]:
    """Get the current flow trace."""
    return _flow_trace.copy()


def get_trace_summary() -> dict[str, Any]:
    """Get a summary of the flow trace for quick analysis."""
    tool_counts: dict[str, int] = {}
    mock_count = 0
    real_count = 0

    for entry in _flow_trace:
        tool = entry.get("tool", "unknown")
        tool_counts[tool] = tool_counts.get(tool, 0) + 1
        if entry.get("is_mock"):
            mock_count += 1
        else:
            real_count += 1

    return {
        "total_calls": len(_flow_trace),
        "mock_calls": mock_count,
        "real_calls": real_count,
        "by_tool": tool_counts,
        "trace_file": str(_trace_file) if _trace_file else None,
    }
