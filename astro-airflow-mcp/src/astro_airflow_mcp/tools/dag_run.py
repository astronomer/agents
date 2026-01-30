"""DAG run management tools - list, get, trigger, trigger and wait."""

import json
import time
from typing import Any

from astro_airflow_mcp.constants import DEFAULT_LIMIT, DEFAULT_OFFSET, TERMINAL_DAG_RUN_STATES
from astro_airflow_mcp.server import (
    _get_adapter,
    _wrap_list_response,
    mcp,
)
from astro_airflow_mcp.utils import extract_failed_tasks


def _list_dag_runs_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing DAG runs from Airflow.

    Args:
        limit: Maximum number of DAG runs to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of DAG runs with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_dag_runs(limit=limit, offset=offset)

        if "dag_runs" in data:
            return _wrap_list_response(data["dag_runs"], "dag_runs", data)
        return f"No DAG runs found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_dag_run_impl(
    dag_id: str,
    dag_run_id: str,
) -> str:
    """Internal implementation for getting a specific DAG run from Airflow.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run

    Returns:
        JSON string containing the DAG run details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_dag_run(dag_id, dag_run_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _trigger_dag_impl(
    dag_id: str,
    conf: dict | None = None,
) -> str:
    """Internal implementation for triggering a new DAG run.

    Args:
        dag_id: The ID of the DAG to trigger
        conf: Optional configuration dictionary to pass to the DAG run

    Returns:
        JSON string containing the triggered DAG run details
    """
    try:
        adapter = _get_adapter()
        data = adapter.trigger_dag_run(dag_id=dag_id, conf=conf)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _get_failed_task_instances(
    dag_id: str,
    dag_run_id: str,
) -> list[dict[str, Any]]:
    """Fetch task instances that failed in a DAG run.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run

    Returns:
        List of failed task instance details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_task_instances(dag_id, dag_run_id)
        task_instances = data.get("task_instances", [])
        return extract_failed_tasks(task_instances)
    except Exception:
        # If we can't fetch failed tasks, return empty list rather than failing
        return []


def _trigger_dag_and_wait_impl(
    dag_id: str,
    conf: dict | None = None,
    poll_interval: float = 5.0,
    timeout: float = 3600.0,
) -> str:
    """Internal implementation for triggering a DAG and waiting for completion.

    Args:
        dag_id: The ID of the DAG to trigger
        conf: Optional configuration dictionary to pass to the DAG run
        poll_interval: Seconds between status checks (default: 5.0)
        timeout: Maximum time to wait in seconds (default: 3600.0 / 60 minutes)

    Returns:
        JSON string containing the final DAG run status and any failed task details
    """
    # Step 1: Trigger the DAG
    trigger_response = _trigger_dag_impl(
        dag_id=dag_id,
        conf=conf,
    )

    try:
        trigger_data = json.loads(trigger_response)
    except json.JSONDecodeError:
        return json.dumps(
            {
                "error": f"Failed to trigger DAG: {trigger_response}",
                "timed_out": False,
            },
            indent=2,
        )

    dag_run_id = trigger_data.get("dag_run_id")
    if not dag_run_id:
        return json.dumps(
            {
                "error": f"No dag_run_id in trigger response: {trigger_response}",
                "timed_out": False,
            },
            indent=2,
        )

    # Step 2: Poll for completion
    start_time = time.time()
    current_state = trigger_data.get("state", "queued")

    while True:
        elapsed = time.time() - start_time

        # Check timeout
        if elapsed >= timeout:
            result: dict[str, Any] = {
                "dag_id": dag_id,
                "dag_run_id": dag_run_id,
                "state": current_state,
                "timed_out": True,
                "elapsed_seconds": round(elapsed, 2),
                "message": f"Timed out after {timeout} seconds. DAG run is still {current_state}.",
            }
            return json.dumps(result, indent=2)

        # Wait before polling
        time.sleep(poll_interval)

        # Get current status
        status_response = _get_dag_run_impl(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
        )

        try:
            status_data = json.loads(status_response)
        except json.JSONDecodeError:
            # If we can't parse, continue polling
            continue

        current_state = status_data.get("state", current_state)

        # Check if we've reached a terminal state
        if current_state in TERMINAL_DAG_RUN_STATES:
            result = {
                "dag_run": status_data,
                "timed_out": False,
                "elapsed_seconds": round(time.time() - start_time, 2),
            }

            # Fetch failed task details if not successful
            if current_state != "success":
                failed_tasks = _get_failed_task_instances(
                    dag_id=dag_id,
                    dag_run_id=dag_run_id,
                )
                if failed_tasks:
                    result["failed_tasks"] = failed_tasks

            return json.dumps(result, indent=2)


@mcp.tool()
def list_dag_runs() -> str:
    """Get execution history and status of DAG runs (workflow executions).

    Use this tool when the user asks about:
    - "What DAG runs have executed?" or "Show me recent runs"
    - "Which runs failed/succeeded?"
    - "What's the status of my workflows?"
    - "When did DAG X last run?"
    - Execution times, durations, or states
    - Finding runs by date or status

    Returns execution metadata including:
    - dag_run_id: Unique identifier for this execution
    - dag_id: Which DAG this run belongs to
    - state: Current state (running, success, failed, queued)
    - execution_date: When this run was scheduled to execute
    - start_date: When execution actually started
    - end_date: When execution completed (if finished)
    - run_type: manual, scheduled, or backfill
    - conf: Configuration passed to this run

    Returns:
        JSON with list of DAG runs across all DAGs, sorted by most recent
    """
    return _list_dag_runs_impl()


@mcp.tool()
def get_dag_run(dag_id: str, dag_run_id: str) -> str:
    """Get detailed information about a specific DAG run execution.

    Use this tool when the user asks about:
    - "Show me details for DAG run X" or "What's the status of run Y?"
    - "When did this run start/finish?" or "How long did run Z take?"
    - "Why did this run fail?" or "Get execution details for run X"
    - "What was the configuration for this run?" or "Show me run metadata"
    - "What's the state of DAG run X?" or "Did run Y succeed?"

    Returns detailed information about a specific DAG run execution including:
    - dag_run_id: Unique identifier for this execution
    - dag_id: Which DAG this run belongs to
    - state: Current state (running, success, failed, queued, etc.)
    - execution_date: When this run was scheduled to execute
    - start_date: When execution actually started
    - end_date: When execution completed (if finished)
    - duration: How long the run took (in seconds)
    - run_type: Type of run (manual, scheduled, backfill, etc.)
    - conf: Configuration parameters passed to this run
    - external_trigger: Whether this was triggered externally
    - data_interval_start: Start of the data interval
    - data_interval_end: End of the data interval
    - last_scheduling_decision: Last scheduling decision timestamp
    - note: Optional note attached to the run

    Args:
        dag_id: The ID of the DAG (e.g., "example_dag")
        dag_run_id: The ID of the DAG run (e.g., "manual__2024-01-01T00:00:00+00:00")

    Returns:
        JSON with complete details about the specified DAG run
    """
    return _get_dag_run_impl(dag_id=dag_id, dag_run_id=dag_run_id)


@mcp.tool()
def trigger_dag(dag_id: str, conf: dict | None = None) -> str:
    """Trigger a new DAG run (start a workflow execution manually).

    Use this tool when the user asks to:
    - "Run DAG X" or "Start DAG Y" or "Execute DAG Z"
    - "Trigger a run of DAG X" or "Kick off DAG Y"
    - "Run this workflow" or "Start this pipeline"
    - "Execute DAG X with config Y" or "Trigger DAG with parameters"
    - "Start a manual run" or "Manually execute this DAG"

    This creates a new DAG run that will be picked up by the scheduler and executed.
    You can optionally pass configuration parameters that will be available to the
    DAG during execution via the `conf` context variable.

    IMPORTANT: This is a write operation that modifies Airflow state by creating
    a new DAG run. Use with caution.

    Returns information about the newly triggered DAG run including:
    - dag_run_id: Unique identifier for the new execution
    - dag_id: Which DAG was triggered
    - state: Initial state (typically 'queued')
    - execution_date: When this run is scheduled to execute
    - start_date: When execution started (may be null if queued)
    - run_type: Type of run (will be 'manual')
    - conf: Configuration passed to the run
    - external_trigger: Set to true for manual triggers

    Args:
        dag_id: The ID of the DAG to trigger (e.g., "example_dag")
        conf: Optional configuration dictionary to pass to the DAG run.
              This will be available in the DAG via context['dag_run'].conf

    Returns:
        JSON with details about the newly triggered DAG run
    """
    return _trigger_dag_impl(
        dag_id=dag_id,
        conf=conf,
    )


@mcp.tool()
def trigger_dag_and_wait(
    dag_id: str,
    conf: dict | None = None,
    timeout: float = 3600.0,
) -> str:
    """Trigger a DAG run and wait for it to complete before returning.

    Use this tool when the user asks to:
    - "Run DAG X and wait for it to finish" or "Execute DAG Y and tell me when it's done"
    - "Trigger DAG Z and wait for completion" or "Run this pipeline synchronously"
    - "Start DAG X and let me know the result" or "Execute and monitor DAG Y"
    - "Run DAG X and show me if it succeeds or fails"

    This is a BLOCKING operation that will:
    1. Trigger the specified DAG
    2. Poll for status automatically (interval scales with timeout)
    3. Return once the DAG run reaches a terminal state (success, failed, upstream_failed)
    4. Include details about any failed tasks if the run was not successful

    IMPORTANT: This tool blocks until the DAG completes or times out. For long-running
    DAGs, consider using `trigger_dag` instead and checking status separately with
    `get_dag_run`.

    Default timeout is 60 minutes. Adjust the `timeout` parameter for longer DAGs.

    Returns information about the completed DAG run including:
    - dag_id: Which DAG was run
    - dag_run_id: Unique identifier for this execution
    - state: Final state (success, failed, upstream_failed)
    - start_date: When execution started
    - end_date: When execution completed
    - elapsed_seconds: How long we waited
    - timed_out: Whether we hit the timeout before completion
    - failed_tasks: List of failed task details (only if state != success)

    Args:
        dag_id: The ID of the DAG to trigger (e.g., "example_dag")
        conf: Optional configuration dictionary to pass to the DAG run.
              This will be available in the DAG via context['dag_run'].conf
        timeout: Maximum time to wait in seconds (default: 3600.0 / 60 minutes)

    Returns:
        JSON with final DAG run status and any failed task details
    """
    # Calculate poll interval based on timeout (2-10 seconds range)
    poll_interval = max(2.0, min(10.0, timeout / 120))

    return _trigger_dag_and_wait_impl(
        dag_id=dag_id,
        conf=conf,
        poll_interval=poll_interval,
        timeout=timeout,
    )
