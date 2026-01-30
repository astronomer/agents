"""DAG management tools - get, list, source, stats, pause, unpause."""

import json

from astro_airflow_mcp.constants import DEFAULT_LIMIT, DEFAULT_OFFSET
from astro_airflow_mcp.server import (
    _get_adapter,
    _wrap_list_response,
    mcp,
)


def _get_dag_details_impl(dag_id: str) -> str:
    """Internal implementation for getting details about a specific DAG.

    Args:
        dag_id: The ID of the DAG to get details for

    Returns:
        JSON string containing the DAG details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_dag(dag_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def get_dag_details(dag_id: str) -> str:
    """Get detailed information about a specific Apache Airflow DAG.

    Use this tool when the user asks about:
    - "Show me details for DAG X" or "What are the details of DAG Y?"
    - "Tell me about DAG Z" or "Get information for this specific DAG"
    - "What's the schedule for DAG X?" or "When does this DAG run?"
    - "Is DAG Y paused?" or "Show me the configuration of DAG Z"
    - "Who owns this DAG?" or "What are the tags for this workflow?"

    Returns complete DAG information including:
    - dag_id: Unique identifier for the DAG
    - is_paused: Whether the DAG is currently paused
    - is_active: Whether the DAG is active
    - is_subdag: Whether this is a SubDAG
    - fileloc: File path where the DAG is defined
    - file_token: Unique token for the DAG file
    - owners: List of DAG owners
    - description: Human-readable description of what the DAG does
    - schedule_interval: Cron expression or timedelta for scheduling
    - tags: List of tags/labels for categorization
    - max_active_runs: Maximum number of concurrent runs
    - max_active_tasks: Maximum number of concurrent tasks
    - has_task_concurrency_limits: Whether task concurrency limits are set
    - has_import_errors: Whether the DAG has import errors
    - next_dagrun: When the next DAG run is scheduled
    - next_dagrun_create_after: Earliest time for next DAG run creation

    Args:
        dag_id: The ID of the DAG to get details for

    Returns:
        JSON with complete details about the specified DAG
    """
    return _get_dag_details_impl(dag_id=dag_id)


def _list_dags_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing DAGs from Airflow.

    Args:
        limit: Maximum number of DAGs to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of DAGs with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_dags(limit=limit, offset=offset)

        if "dags" in data:
            return _wrap_list_response(data["dags"], "dags", data)
        return f"No DAGs found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def list_dags() -> str:
    """Get information about all Apache Airflow DAGs (Directed Acyclic Graphs).

    Use this tool when the user asks about:
    - "What DAGs are available?" or "List all DAGs"
    - "Show me the workflows" or "What pipelines exist?"
    - "Which DAGs are paused/active?"
    - DAG schedules, descriptions, or tags
    - Finding a specific DAG by name

    Returns comprehensive DAG metadata including:
    - dag_id: Unique identifier for the DAG
    - is_paused: Whether the DAG is currently paused
    - is_active: Whether the DAG is active
    - schedule_interval: How often the DAG runs
    - description: Human-readable description
    - tags: Labels/categories for the DAG
    - owners: Who maintains the DAG
    - file_token: Location of the DAG file

    Returns:
        JSON with list of all DAGs and their complete metadata
    """
    return _list_dags_impl()


def _get_dag_source_impl(dag_id: str) -> str:
    """Internal implementation for getting DAG source code from Airflow.

    Args:
        dag_id: The ID of the DAG to get source code for

    Returns:
        JSON string containing the DAG source code and metadata
    """
    try:
        adapter = _get_adapter()
        source_data = adapter.get_dag_source(dag_id)
        return json.dumps(source_data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def get_dag_source(dag_id: str) -> str:
    """Get the source code for a specific Apache Airflow DAG.

    Use this tool when the user asks about:
    - "Show me the code for DAG X" or "What's the source of DAG Y?"
    - "How is DAG Z implemented?" or "What does the DAG file look like?"
    - "Can I see the Python code for this workflow?"
    - "What tasks are defined in the DAG code?"

    Returns the DAG source file contents including:
    - content: The actual Python source code of the DAG file
    - file_token: Unique identifier for the source file

    Args:
        dag_id: The ID of the DAG to get source code for

    Returns:
        JSON with DAG source code and metadata
    """
    return _get_dag_source_impl(dag_id=dag_id)


def _get_dag_stats_impl(dag_ids: list[str] | None = None) -> str:
    """Internal implementation for getting DAG statistics from Airflow.

    Args:
        dag_ids: Optional list of DAG IDs to get stats for. If None, gets stats for all DAGs.

    Returns:
        JSON string containing DAG run statistics by state
    """
    try:
        adapter = _get_adapter()
        stats_data = adapter.get_dag_stats(dag_ids=dag_ids)
        return json.dumps(stats_data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def get_dag_stats(dag_ids: list[str] | None = None) -> str:
    """Get statistics about DAG runs (success/failure counts by state).

    Use this tool when the user asks about:
    - "What's the overall health of my DAGs?" or "Show me DAG statistics"
    - "How many DAG runs succeeded/failed?" or "What's the success rate?"
    - "Give me a summary of DAG run states"
    - "How many runs are currently running/queued?"
    - "Show me stats for specific DAGs"

    Returns statistics showing counts of DAG runs grouped by state:
    - success: Number of successful runs
    - failed: Number of failed runs
    - running: Number of currently running runs
    - queued: Number of queued runs
    - And other possible states

    Args:
        dag_ids: Optional list of DAG IDs to filter by. If not provided, returns stats for all DAGs.

    Returns:
        JSON with DAG run statistics organized by DAG and state
    """
    return _get_dag_stats_impl(dag_ids=dag_ids)


def _pause_dag_impl(dag_id: str) -> str:
    """Internal implementation for pausing a DAG.

    Args:
        dag_id: The ID of the DAG to pause

    Returns:
        JSON string containing the updated DAG details
    """
    try:
        adapter = _get_adapter()
        data = adapter.pause_dag(dag_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def pause_dag(dag_id: str) -> str:
    """Pause a DAG to prevent new scheduled runs from starting.

    Use this tool when the user asks to:
    - "Pause DAG X" or "Stop DAG Y from running"
    - "Disable DAG Z" or "Prevent new runs of DAG X"
    - "Turn off DAG scheduling" or "Suspend DAG execution"

    When a DAG is paused:
    - No new scheduled runs will be created
    - Currently running tasks will complete
    - Manual triggers are still possible
    - The DAG remains visible in the UI with a paused indicator

    IMPORTANT: This is a write operation that modifies Airflow state.
    The DAG will remain paused until explicitly unpaused.

    Args:
        dag_id: The ID of the DAG to pause (e.g., "example_dag")

    Returns:
        JSON with updated DAG details showing is_paused=True
    """
    return _pause_dag_impl(dag_id=dag_id)


def _unpause_dag_impl(dag_id: str) -> str:
    """Internal implementation for unpausing a DAG.

    Args:
        dag_id: The ID of the DAG to unpause

    Returns:
        JSON string containing the updated DAG details
    """
    try:
        adapter = _get_adapter()
        data = adapter.unpause_dag(dag_id)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def unpause_dag(dag_id: str) -> str:
    """Unpause a DAG to allow scheduled runs to resume.

    Use this tool when the user asks to:
    - "Unpause DAG X" or "Resume DAG Y"
    - "Enable DAG Z" or "Start DAG scheduling again"
    - "Turn on DAG X" or "Activate DAG Y"

    When a DAG is unpaused:
    - The scheduler will create new runs based on the schedule
    - Any missed runs (depending on catchup setting) may be created
    - The DAG will appear active in the UI

    IMPORTANT: This is a write operation that modifies Airflow state.
    New DAG runs will be scheduled according to the DAG's schedule_interval.

    Args:
        dag_id: The ID of the DAG to unpause (e.g., "example_dag")

    Returns:
        JSON with updated DAG details showing is_paused=False
    """
    return _unpause_dag_impl(dag_id=dag_id)
