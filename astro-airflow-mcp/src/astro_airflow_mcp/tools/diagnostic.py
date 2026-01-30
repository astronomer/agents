"""Diagnostic tools - warnings, errors, explore, diagnose, system health."""

import json
from typing import Any

from astro_airflow_mcp.constants import DEFAULT_LIMIT, DEFAULT_OFFSET
from astro_airflow_mcp.server import (
    _get_adapter,
    _wrap_list_response,
    mcp,
)


def _list_dag_warnings_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing DAG warnings from Airflow.

    Args:
        limit: Maximum number of warnings to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of DAG warnings
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_dag_warnings(limit=limit, offset=offset)

        if "dag_warnings" in data:
            return _wrap_list_response(data["dag_warnings"], "dag_warnings", data)
        return f"No DAG warnings found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_import_errors_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing import errors from Airflow.

    Args:
        limit: Maximum number of import errors to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of import errors
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_import_errors(limit=limit, offset=offset)

        if "import_errors" in data:
            return _wrap_list_response(data["import_errors"], "import_errors", data)
        return f"No import errors found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def list_dag_warnings() -> str:
    """Get warnings and issues detected in DAG definitions.

    Use this tool when the user asks about:
    - "Are there any DAG warnings?" or "Show me DAG issues"
    - "What problems exist with my DAGs?" or "Any DAG errors?"
    - "Check DAG health" or "Show me DAG validation warnings"
    - "What's wrong with my workflows?"

    Returns warnings about DAG configuration issues including:
    - dag_id: Which DAG has the warning
    - warning_type: Type of warning (e.g., deprecation, configuration issue)
    - message: Description of the warning
    - timestamp: When the warning was detected

    Returns:
        JSON with list of DAG warnings and their details
    """
    return _list_dag_warnings_impl()


@mcp.tool()
def list_import_errors() -> str:
    """Get import errors from DAG files that failed to parse or load.

    Use this tool when the user asks about:
    - "Are there any import errors?" or "Show me import errors"
    - "Why isn't my DAG showing up?" or "DAG not appearing in Airflow"
    - "What DAG files have errors?" or "Show me broken DAGs"
    - "Check for syntax errors" or "Are there any parsing errors?"
    - "Why is my DAG file failing to load?"

    Import errors occur when DAG files have problems that prevent Airflow
    from parsing them, such as:
    - Python syntax errors
    - Missing imports or dependencies
    - Module not found errors
    - Invalid DAG definitions
    - Runtime errors during file parsing

    Returns import error details including:
    - import_error_id: Unique identifier for the error
    - timestamp: When the error was detected
    - filename: Path to the DAG file with the error
    - stack_trace: Complete error message and traceback

    Returns:
        JSON with list of import errors and their stack traces
    """
    return _list_import_errors_impl()


# =============================================================================
# CONSOLIDATED TOOLS (Agent-optimized for complex investigations)
# =============================================================================


@mcp.tool()
def explore_dag(dag_id: str) -> str:
    """Comprehensive investigation of a DAG - get all relevant info in one call.

    USE THIS TOOL WHEN you need to understand a DAG completely. Instead of making
    multiple calls, this returns everything about a DAG in a single response.

    This is the preferred first tool when:
    - User asks "Tell me about DAG X" or "What is this DAG?"
    - You need to understand a DAG's structure before diagnosing issues
    - You want to know the schedule, tasks, and source code together

    Returns combined data:
    - DAG metadata (schedule, owners, tags, paused status)
    - All tasks with their operators and dependencies
    - DAG source code
    - Any import errors or warnings for this DAG

    Args:
        dag_id: The ID of the DAG to explore

    Returns:
        JSON with comprehensive DAG information
    """
    result: dict[str, Any] = {"dag_id": dag_id}
    adapter = _get_adapter()

    # Get DAG details
    try:
        result["dag_info"] = adapter.get_dag(dag_id)
    except Exception as e:
        result["dag_info"] = {"error": str(e)}

    # Get tasks
    try:
        tasks_data = adapter.list_tasks(dag_id)
        result["tasks"] = tasks_data.get("tasks", [])
    except Exception as e:
        result["tasks"] = {"error": str(e)}

    # Get DAG source
    try:
        result["source"] = adapter.get_dag_source(dag_id)
    except Exception as e:
        result["source"] = {"error": str(e)}

    return json.dumps(result, indent=2)


@mcp.tool()
def diagnose_dag_run(dag_id: str, dag_run_id: str) -> str:
    """Diagnose issues with a specific DAG run - get run details and failed tasks.

    USE THIS TOOL WHEN troubleshooting a failed or problematic DAG run. Returns
    all the information you need to understand what went wrong.

    This is the preferred tool when:
    - User asks "Why did this DAG run fail?"
    - User asks "What's wrong with run X?"
    - You need to investigate task failures in a specific run

    Returns combined data:
    - DAG run metadata (state, start/end times, trigger type)
    - All task instances for this run with their states
    - Highlighted failed/upstream_failed tasks with details
    - Summary of task states

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run (e.g., "manual__2024-01-01T00:00:00+00:00")

    Returns:
        JSON with diagnostic information about the DAG run
    """
    result: dict[str, Any] = {"dag_id": dag_id, "dag_run_id": dag_run_id}
    adapter = _get_adapter()

    # Get DAG run details
    try:
        result["run_info"] = adapter.get_dag_run(dag_id, dag_run_id)
    except Exception as e:
        result["run_info"] = {"error": str(e)}
        return json.dumps(result, indent=2)

    # Get task instances for this run
    try:
        tasks_data = adapter.get_task_instances(dag_id, dag_run_id)
        task_instances = tasks_data.get("task_instances", [])
        result["task_instances"] = task_instances

        # Summarize task states
        state_counts: dict[str, int] = {}
        failed_tasks = []
        for ti in task_instances:
            state = ti.get("state", "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
            if state in ("failed", "upstream_failed"):
                failed_tasks.append(
                    {
                        "task_id": ti.get("task_id"),
                        "state": state,
                        "start_date": ti.get("start_date"),
                        "end_date": ti.get("end_date"),
                        "try_number": ti.get("try_number"),
                    }
                )

        result["summary"] = {
            "total_tasks": len(task_instances),
            "state_counts": state_counts,
            "failed_tasks": failed_tasks,
        }
    except Exception as e:
        result["task_instances"] = {"error": str(e)}

    return json.dumps(result, indent=2)


@mcp.tool()
def get_system_health() -> str:
    """Get overall Airflow system health - import errors, warnings, and DAG stats.

    USE THIS TOOL WHEN you need a quick health check of the Airflow system.
    Returns a consolidated view of potential issues across the entire system.

    This is the preferred tool when:
    - User asks "Are there any problems with Airflow?"
    - User asks "Show me the system health" or "Any errors?"
    - You want to do a morning health check
    - You're starting an investigation and want to see the big picture

    Returns combined data:
    - Import errors (DAG files that failed to parse)
    - DAG warnings (deprecations, configuration issues)
    - DAG statistics (run counts by state) if available
    - Version information

    Returns:
        JSON with system health overview
    """
    result: dict[str, Any] = {}
    adapter = _get_adapter()

    # Get version info
    try:
        result["version"] = adapter.get_version()
    except Exception as e:
        result["version"] = {"error": str(e)}

    # Get import errors
    try:
        errors_data = adapter.list_import_errors(limit=100)
        import_errors = errors_data.get("import_errors", [])
        result["import_errors"] = {
            "count": len(import_errors),
            "errors": import_errors,
        }
    except Exception as e:
        result["import_errors"] = {"error": str(e)}

    # Get DAG warnings
    try:
        warnings_data = adapter.list_dag_warnings(limit=100)
        dag_warnings = warnings_data.get("dag_warnings", [])
        result["dag_warnings"] = {
            "count": len(dag_warnings),
            "warnings": dag_warnings,
        }
    except Exception as e:
        result["dag_warnings"] = {"error": str(e)}

    # Get DAG stats
    try:
        result["dag_stats"] = adapter.get_dag_stats()
    except Exception:
        result["dag_stats"] = {"available": False, "note": "dagStats endpoint not available"}

    # Calculate overall health status
    import_error_count = result.get("import_errors", {}).get("count", 0)
    warning_count = result.get("dag_warnings", {}).get("count", 0)

    if import_error_count > 0:
        result["overall_status"] = "unhealthy"
        result["status_reason"] = f"{import_error_count} import error(s) detected"
    elif warning_count > 0:
        result["overall_status"] = "warning"
        result["status_reason"] = f"{warning_count} DAG warning(s) detected"
    else:
        result["overall_status"] = "healthy"
        result["status_reason"] = "No import errors or warnings"

    return json.dumps(result, indent=2)
