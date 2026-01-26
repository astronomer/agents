"""Task management tools - get, list, instance, logs, clear."""

import json

from astro_airflow_mcp.server import _get_adapter, _wrap_list_response, mcp


def _get_task_impl(dag_id: str, task_id: str) -> str:
    """Internal implementation for getting task details from Airflow.

    Args:
        dag_id: The ID of the DAG
        task_id: The ID of the task

    Returns:
        JSON string containing the task details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_task(dag_id, task_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_tasks_impl(dag_id: str) -> str:
    """Internal implementation for listing tasks in a DAG from Airflow.

    Args:
        dag_id: The ID of the DAG to list tasks for

    Returns:
        JSON string containing the list of tasks with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_tasks(dag_id)

        if "tasks" in data:
            return _wrap_list_response(data["tasks"], "tasks", data)
        return f"No tasks found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_task_instance_impl(dag_id: str, dag_run_id: str, task_id: str) -> str:
    """Internal implementation for getting task instance details from Airflow.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run
        task_id: The ID of the task

    Returns:
        JSON string containing the task instance details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_task_instance(dag_id, dag_run_id, task_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _get_task_logs_impl(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    try_number: int = 1,
    map_index: int = -1,
) -> str:
    """Internal implementation for getting task instance logs from Airflow.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run
        task_id: The ID of the task
        try_number: The task try number (1-indexed, default: 1)
        map_index: For mapped tasks, which map index (-1 for unmapped, default: -1)

    Returns:
        JSON string containing the task logs
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_task_logs(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_id=task_id,
            try_number=try_number,
            map_index=map_index,
            full_content=True,
        )
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _clear_task_instances_impl(
    dag_id: str,
    dag_run_id: str,
    task_ids: list[str],
    dry_run: bool = True,
    only_failed: bool = False,
    include_downstream: bool = False,
) -> str:
    """Internal implementation for clearing task instances.

    Note: The adapter also supports ``include_upstream`` and ``reset_dag_runs``
    parameters, but they are intentionally omitted from the tool surface.
    ``include_upstream`` is rarely desired for retries (and risks re-processing
    already-succeeded tasks), and ``reset_dag_runs=True`` is the correct default
    for virtually all retry scenarios.  The adapter sends sensible defaults for
    both.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run
        task_ids: List of task IDs to clear
        dry_run: If True, return what would be cleared without clearing
        only_failed: Only clear failed task instances
        include_downstream: Also clear downstream tasks

    Returns:
        JSON string with the cleared task instances
    """
    try:
        adapter = _get_adapter()
        data = adapter.clear_task_instances(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_ids=task_ids,
            dry_run=dry_run,
            only_failed=only_failed,
            include_downstream=include_downstream,
        )
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def get_task(dag_id: str, task_id: str) -> str:
    """Get detailed information about a specific task definition in a DAG.

    Use this tool when the user asks about:
    - "Show me details for task X in DAG Y" or "What does task Z do?"
    - "What operator does task A use?" or "What's the configuration of task B?"
    - "Tell me about task C" or "Get task definition for D"
    - "What are the dependencies of task E?" or "Which tasks does F depend on?"

    Returns task definition information including:
    - task_id: Unique identifier for the task
    - task_display_name: Human-readable display name
    - owner: Who owns this task
    - start_date: When this task becomes active
    - end_date: When this task becomes inactive (if set)
    - trigger_rule: When this task should run (all_success, one_failed, etc.)
    - depends_on_past: Whether task depends on previous run's success
    - wait_for_downstream: Whether to wait for downstream tasks
    - retries: Number of retry attempts
    - retry_delay: Time between retries
    - execution_timeout: Maximum execution time
    - operator_name: Type of operator (PythonOperator, BashOperator, etc.)
    - pool: Resource pool assignment
    - queue: Queue for executor
    - downstream_task_ids: List of tasks that depend on this task
    - upstream_task_ids: List of tasks this task depends on

    Args:
        dag_id: The ID of the DAG containing the task
        task_id: The ID of the task to get details for

    Returns:
        JSON with complete task definition details
    """
    return _get_task_impl(dag_id=dag_id, task_id=task_id)


@mcp.tool()
def list_tasks(dag_id: str) -> str:
    """Get all tasks defined in a specific DAG.

    Use this tool when the user asks about:
    - "What tasks are in DAG X?" or "List all tasks for DAG Y"
    - "Show me the tasks in this workflow" or "What's in the DAG?"
    - "What are the steps in DAG Z?" or "Show me the task structure"
    - "What does this DAG do?" or "Explain the workflow steps"

    Returns information about all tasks in the DAG including:
    - task_id: Unique identifier for the task
    - task_display_name: Human-readable display name
    - owner: Who owns this task
    - operator_name: Type of operator (PythonOperator, BashOperator, etc.)
    - start_date: When this task becomes active
    - end_date: When this task becomes inactive (if set)
    - trigger_rule: When this task should run
    - retries: Number of retry attempts
    - pool: Resource pool assignment
    - downstream_task_ids: List of tasks that depend on this task
    - upstream_task_ids: List of tasks this task depends on

    Args:
        dag_id: The ID of the DAG to list tasks for

    Returns:
        JSON with list of all tasks in the DAG and their configurations
    """
    return _list_tasks_impl(dag_id=dag_id)


@mcp.tool()
def get_task_instance(dag_id: str, dag_run_id: str, task_id: str) -> str:
    """Get detailed information about a specific task instance execution.

    Use this tool when the user asks about:
    - "Show me details for task X in DAG run Y" or "What's the status of task Z?"
    - "Why did task A fail?" or "When did task B start/finish?"
    - "What's the duration of task C?" or "Show me task execution details"
    - "Get logs for task D" or "What operator does task E use?"

    Returns detailed task instance information including:
    - task_id: Name of the task
    - state: Current state (success, failed, running, queued, etc.)
    - start_date: When the task started
    - end_date: When the task finished
    - duration: How long the task ran
    - try_number: Which attempt this is
    - max_tries: Maximum retry attempts
    - operator: What operator type (PythonOperator, BashOperator, etc.)
    - executor_config: Executor configuration
    - pool: Resource pool assignment

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run (e.g., "manual__2024-01-01T00:00:00+00:00")
        task_id: The ID of the task within the DAG

    Returns:
        JSON with complete task instance details
    """
    return _get_task_instance_impl(dag_id=dag_id, dag_run_id=dag_run_id, task_id=task_id)


@mcp.tool()
def get_task_logs(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    try_number: int = 1,
    map_index: int = -1,
) -> str:
    """Get logs for a specific task instance execution.

    Use this tool when the user asks about:
    - "Show me the logs for task X" or "Get logs for task Y"
    - "What did task Z output?" or "Show me task execution logs"
    - "Why did task A fail?" (to see error messages in logs)
    - "What happened during task B execution?"
    - "Show me the stdout/stderr for task C"
    - "Debug task D" or "Troubleshoot task E"

    Returns the actual log output from the task execution, which includes:
    - Task execution output (stdout/stderr)
    - Error messages and stack traces (if task failed)
    - Timing information
    - Any logged messages from the task code

    This is essential for debugging failed tasks or understanding what
    happened during task execution.

    Args:
        dag_id: The ID of the DAG (e.g., "example_dag")
        dag_run_id: The ID of the DAG run (e.g., "manual__2024-01-01T00:00:00+00:00")
        task_id: The ID of the task within the DAG (e.g., "extract_data")
        try_number: The task try/attempt number, 1-indexed (default: 1).
                    Use higher numbers to get logs from retry attempts.
        map_index: For mapped tasks, which map index to get logs for.
                   Use -1 for non-mapped tasks (default: -1).

    Returns:
        JSON with the task logs content
    """
    return _get_task_logs_impl(
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_id=task_id,
        try_number=try_number,
        map_index=map_index,
    )


@mcp.tool()
def clear_task_instances(
    dag_id: str,
    dag_run_id: str,
    task_ids: list[str],
    dry_run: bool = True,
    only_failed: bool = False,
    include_downstream: bool = False,
) -> str:
    """Clear task instances to retry their execution.

    Use this tool when the user asks about:
    - "Retry task X" or "Clear task Y and run again"
    - "Rerun the failed tasks" or "Reset task Z"
    - "Clear and retry from task A onwards"
    - "Re-execute task B" or "Run task C again"
    - "Fix the failed task and retry"

    This clears the state of task instances, allowing them to be re-executed.
    By default, it runs in dry_run mode to show what would be cleared.
    Set dry_run=False to actually clear the tasks.

    Returns information about cleared task instances including:
    - task_id: The ID of the cleared task
    - dag_id: The DAG containing the task
    - dag_run_id: The DAG run containing the task
    - state: The previous state of the task (before clearing)

    Args:
        dag_id: The ID of the DAG (e.g., "example_dag")
        dag_run_id: The ID of the DAG run (e.g., "manual__2024-01-01T00:00:00+00:00")
        task_ids: List of task IDs to clear (e.g., ["extract_data", "transform_data"])
        dry_run: If True (default), only show what would be cleared without actually
                 clearing. Set to False to actually clear the tasks.
        only_failed: If True, only clear task instances that are in a failed state.
                     Useful for retrying just the failures.
        include_downstream: If True, also clear all downstream tasks that depend
                           on the specified tasks. Useful for "retry from here onwards".

    Returns:
        JSON with list of task instances that were (or would be) cleared
    """
    return _clear_task_instances_impl(
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_ids=task_ids,
        dry_run=dry_run,
        only_failed=only_failed,
        include_downstream=include_downstream,
    )
