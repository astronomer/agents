"""FastMCP server for Airflow integration."""

from typing import Any

import requests
from fastmcp import FastMCP

# Default configuration values
DEFAULT_AIRFLOW_URL = "http://localhost:8080"
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0

# Create MCP server
mcp = FastMCP(
    "Airflow MCP Server",
    instructions="""
    This server provides access to Apache Airflow's REST API through MCP tools.

    Use these tools to:
    - List and inspect DAGs (Directed Acyclic Graphs / workflows)
    - View DAG runs and their execution status
    - Check task instances and their states
    - Inspect Airflow connections, variables, and pools
    - Monitor DAG statistics and warnings
    - View system configuration and version information

    When the user asks about Airflow workflows, pipelines, or data orchestration,
    use these tools to provide detailed, accurate information directly from the
    Airflow instance.
    """,
)


# Global configuration for Airflow API access
class AirflowConfig:
    """Global configuration for Airflow API access."""

    def __init__(self):
        self.url: str = DEFAULT_AIRFLOW_URL
        self.auth_token: str | None = None


_config = AirflowConfig()


def configure(
    url: str | None = None,
    auth_token: str | None = None,
) -> None:
    """Configure global Airflow connection settings.

    Args:
        url: Base URL of Airflow webserver
        auth_token: Bearer token for authentication
    """
    if url:
        _config.url = url
    if auth_token:
        _config.auth_token = auth_token


# Helper functions for API calls and response formatting
def _call_airflow_api(
    endpoint: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    params: dict[str, Any] | None = None,
    auth_token: str | None = None,
) -> dict[str, Any]:
    """Call Airflow REST API with error handling and optional authentication.

    Args:
        endpoint: API endpoint path (e.g., 'dags', 'dagRuns')
        airflow_url: Base URL of the Airflow webserver
        params: Optional query parameters
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        Parsed JSON response from the API

    Raises:
        Exception: If the API call fails with error details

    Note:
        If auth_token is provided, Bearer token authentication is used.
        If not provided, no authentication is used.
    """
    try:
        api_url = f"{airflow_url}/api/v2/{endpoint}"
        headers: dict[str, str] = {}

        # Handle authentication
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error connecting to Airflow API: {str(e)}") from e
    except Exception as e:
        raise Exception(f"Error calling API endpoint '{endpoint}': {str(e)}") from e


def _wrap_list_response(items: list[dict[str, Any]], key_name: str, data: dict[str, Any]) -> str:
    """Wrap API list response with pagination metadata.

    Args:
        items: List of items from the API
        key_name: Name for the items key in response (e.g., 'dags', 'dag_runs')
        data: Original API response data (for total_entries)

    Returns:
        JSON string with pagination metadata
    """
    import json

    total_entries = data.get("total_entries", len(items))
    result: dict[str, Any] = {
        f"total_{key_name}": total_entries,
        "returned_count": len(items),
        key_name: items,
    }
    return json.dumps(result, indent=2)


def _get_dag_details_impl(
    dag_id: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting details about a specific DAG.

    Args:
        dag_id: The ID of the DAG to get details for
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the DAG details
    """
    try:
        data = _call_airflow_api(
            f"dags/{dag_id}",
            airflow_url,
            auth_token=auth_token,
        )

        import json

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
    return _get_dag_details_impl(
        dag_id=dag_id,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _list_dags_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing DAGs from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of DAGs to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of DAGs with their metadata
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "dags",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "dags" in data:
            return _wrap_list_response(data["dags"], "dags", data)
        else:
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
    return _list_dags_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _get_dag_source_impl(
    dag_id: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting DAG source code from Airflow.

    Args:
        dag_id: The ID of the DAG to get source code for
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the DAG source code and metadata
    """
    try:
        # Using dagSources/{dag_id} endpoint
        source_data = _call_airflow_api(
            f"dagSources/{dag_id}",
            airflow_url,
            auth_token=auth_token,
        )

        import json

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
    return _get_dag_source_impl(
        dag_id=dag_id,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _get_dag_stats_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting DAG statistics from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing DAG run statistics by state
    """
    try:
        # Using dagStats endpoint
        stats_data = _call_airflow_api(
            "dagStats",
            airflow_url,
            auth_token=auth_token,
        )

        import json

        return json.dumps(stats_data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def get_dag_stats() -> str:
    """Get statistics about DAG runs across all DAGs (success/failure counts by state).

    Use this tool when the user asks about:
    - "What's the overall health of my DAGs?" or "Show me DAG statistics"
    - "How many DAG runs succeeded/failed?" or "What's the success rate?"
    - "Give me a summary of DAG run states"
    - "How many runs are currently running/queued?"

    Returns statistics showing counts of DAG runs grouped by state:
    - success: Number of successful runs
    - failed: Number of failed runs
    - running: Number of currently running runs
    - queued: Number of queued runs
    - And other possible states

    Returns:
        JSON with DAG run statistics organized by DAG and state
    """
    return _get_dag_stats_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _list_dag_warnings_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing DAG warnings from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of warnings to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of DAG warnings
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "dagWarnings",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "dag_warnings" in data:
            return _wrap_list_response(data["dag_warnings"], "dag_warnings", data)
        else:
            return f"No DAG warnings found. Response: {data}"
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
    return _list_dag_warnings_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _get_task_impl(
    dag_id: str,
    task_id: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting task details from Airflow.

    Args:
        dag_id: The ID of the DAG
        task_id: The ID of the task
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the task details
    """
    try:
        endpoint = f"dags/{dag_id}/tasks/{task_id}"
        data = _call_airflow_api(
            endpoint,
            airflow_url,
            auth_token=auth_token,
        )

        import json

        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_tasks_impl(
    dag_id: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing tasks in a DAG from Airflow.

    Args:
        dag_id: The ID of the DAG to list tasks for
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of tasks with their metadata
    """
    try:
        endpoint = f"dags/{dag_id}/tasks"
        data = _call_airflow_api(
            endpoint,
            airflow_url,
            auth_token=auth_token,
        )

        if "tasks" in data:
            return _wrap_list_response(data["tasks"], "tasks", data)
        else:
            return f"No tasks found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_task_instance_impl(
    dag_id: str,
    dag_run_id: str,
    task_id: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting task instance details from Airflow.

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run
        task_id: The ID of the task
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the task instance details
    """
    try:
        # Using dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id} endpoint
        endpoint = f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}"
        data = _call_airflow_api(
            endpoint,
            airflow_url,
            auth_token=auth_token,
        )

        import json

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
    return _get_task_impl(
        dag_id=dag_id,
        task_id=task_id,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


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
    return _list_tasks_impl(
        dag_id=dag_id,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


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
    return _get_task_instance_impl(
        dag_id=dag_id,
        dag_run_id=dag_run_id,
        task_id=task_id,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _list_dag_runs_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing DAG runs from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of DAG runs to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of DAG runs with their metadata
    """
    try:
        # Using ~/dagRuns to get runs across all DAGs
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "dags/~/dagRuns",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "dag_runs" in data:
            return _wrap_list_response(data["dag_runs"], "dag_runs", data)
        else:
            return f"No DAG runs found. Response: {data}"
    except Exception as e:
        return str(e)


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
    return _list_dag_runs_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _list_assets_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing assets from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of assets to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of assets with their metadata
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "assets",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "assets" in data:
            return _wrap_list_response(data["assets"], "assets", data)
        else:
            return f"No assets found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def list_assets() -> str:
    """Get data assets and datasets tracked by Airflow (data lineage).

    Use this tool when the user asks about:
    - "What datasets exist?" or "List all assets"
    - "What data does this DAG produce/consume?"
    - "Show me data dependencies" or "What's the data lineage?"
    - "Which DAGs use dataset X?"
    - Data freshness or update events

    Assets represent datasets or files that DAGs produce or consume.
    This enables data-driven scheduling where DAGs wait for data availability.

    Returns asset information including:
    - uri: Unique identifier for the asset (e.g., s3://bucket/path)
    - id: Internal asset ID
    - created_at: When this asset was first registered
    - updated_at: When this asset was last updated
    - consuming_dags: Which DAGs depend on this asset
    - producing_tasks: Which tasks create/update this asset

    Returns:
        JSON with list of all assets and their producing/consuming relationships
    """
    return _list_assets_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _list_connections_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing connections from Airflow.

    NOTE: This endpoint uses explicit field filtering (unlike other endpoints)
    to exclude sensitive information like passwords for security reasons.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of connections to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of connections with their metadata
    """
    import json

    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "connections",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "connections" in data:
            connections = data["connections"]
            total_entries = data.get("total_entries", len(connections))

            # SECURITY: Explicitly filter sensitive fields (password)
            # We cannot use pass-through here as we must prevent password exposure
            filtered_connections = [
                {
                    "connection_id": conn.get("connection_id"),
                    "conn_type": conn.get("conn_type"),
                    "description": conn.get("description"),
                    "host": conn.get("host"),
                    "port": conn.get("port"),
                    "schema": conn.get("schema"),
                    "login": conn.get("login"),
                    "extra": conn.get("extra"),
                    # password is intentionally excluded
                }
                for conn in connections
            ]

            result = {
                "total_connections": total_entries,
                "returned_count": len(filtered_connections),
                "connections": filtered_connections,
            }

            return json.dumps(result, indent=2)
        else:
            return f"No connections found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def list_connections() -> str:
    """Get connection configurations for external systems (databases, APIs, services).

    Use this tool when the user asks about:
    - "What connections are configured?" or "List all connections"
    - "How do I connect to database X?"
    - "What's the connection string for Y?"
    - "Which databases/services are available?"
    - Finding connection details by name or type

    Connections store credentials and connection info for external systems
    that DAGs interact with (databases, S3, APIs, etc.).

    Returns connection metadata including:
    - connection_id: Unique name for this connection
    - conn_type: Type (postgres, mysql, s3, http, etc.)
    - description: Human-readable description
    - host: Server hostname or IP
    - port: Port number
    - schema: Database schema or path
    - login: Username (passwords excluded for security)
    - extra: Additional connection parameters as JSON

    IMPORTANT: Passwords are NEVER returned for security reasons.

    Returns:
        JSON with list of all connections (credentials excluded)
    """
    return _list_connections_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


def _get_variable_impl(
    variable_key: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting a specific variable from Airflow.

    Args:
        variable_key: The key of the variable to get
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the variable details
    """
    try:
        data = _call_airflow_api(
            f"variables/{variable_key}",
            airflow_url,
            auth_token=auth_token,
        )

        import json

        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_variables_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing variables from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of variables to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of variables with their metadata
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "variables",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "variables" in data:
            return _wrap_list_response(data["variables"], "variables", data)
        else:
            return f"No variables found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_version_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting Airflow version information.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the Airflow version information
    """
    try:
        data = _call_airflow_api(
            "version",
            airflow_url,
            auth_token=auth_token,
        )

        import json

        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _get_config_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting Airflow configuration.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the Airflow configuration organized by sections
    """
    import json

    try:
        data = _call_airflow_api(
            "config",
            airflow_url,
            auth_token=auth_token,
        )

        if "sections" in data:
            # Add summary metadata and pass through sections
            result = {"total_sections": len(data["sections"]), "sections": data["sections"]}
            return json.dumps(result, indent=2)
        else:
            return f"No configuration found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_pool_impl(
    pool_name: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for getting details about a specific pool.

    Args:
        pool_name: The name of the pool to get details for
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the pool details
    """
    try:
        data = _call_airflow_api(
            f"pools/{pool_name}",
            airflow_url,
            auth_token=auth_token,
        )

        import json

        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_pools_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing pools from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of pools to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of pools with their metadata
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "pools",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "pools" in data:
            return _wrap_list_response(data["pools"], "pools", data)
        else:
            return f"No pools found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_plugins_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing installed plugins from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        limit: Maximum number of plugins to return (default: 100)
        offset: Offset for pagination (default: 0)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of installed plugins
    """
    try:
        params = {"limit": limit, "offset": offset}
        data = _call_airflow_api(
            "plugins",
            airflow_url,
            params,
            auth_token=auth_token,
        )

        if "plugins" in data:
            return _wrap_list_response(data["plugins"], "plugins", data)
        else:
            return f"No plugins found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_providers_impl(
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    auth_token: str | None = None,
) -> str:
    """Internal implementation for listing installed providers from Airflow.

    Args:
        airflow_url: The base URL of the Airflow webserver (default: http://localhost:8080)
        auth_token: Optional Bearer token for token-based authentication

    Returns:
        JSON string containing the list of installed providers
    """
    try:
        data = _call_airflow_api(
            "providers",
            airflow_url,
            auth_token=auth_token,
        )

        if "providers" in data:
            return _wrap_list_response(data["providers"], "providers", data)
        else:
            return f"No providers found. Response: {data}"
    except Exception as e:
        return str(e)


@mcp.tool()
def get_pool(pool_name: str) -> str:
    """Get detailed information about a specific resource pool.

    Use this tool when the user asks about:
    - "Show me details for pool X" or "What's the status of pool Y?"
    - "How many slots are available in pool Z?" or "Is pool X full?"
    - "What's using pool Y?" or "How many tasks are running in pool X?"
    - "Get information about the default_pool" or "Show me pool details"

    Pools are used to limit parallelism for specific sets of tasks. This returns
    detailed real-time information about a specific pool's capacity and utilization.

    Returns detailed pool information including:
    - name: Name of the pool
    - slots: Total number of available slots in the pool
    - occupied_slots: Number of currently occupied slots (running + queued)
    - running_slots: Number of slots with currently running tasks
    - queued_slots: Number of slots with queued tasks waiting to run
    - open_slots: Number of available slots (slots - occupied_slots)
    - description: Human-readable description of the pool's purpose

    Args:
        pool_name: The name of the pool to get details for (e.g., "default_pool")

    Returns:
        JSON with complete details about the specified pool
    """
    return _get_pool_impl(
        pool_name=pool_name,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def list_pools() -> str:
    """Get resource pools for managing task concurrency and resource allocation.

    Use this tool when the user asks about:
    - "What pools are configured?" or "List all pools"
    - "Show me the resource pools" or "What pools exist?"
    - "How many slots does pool X have?" or "What's the pool capacity?"
    - "Which pools are available?" or "What's the pool configuration?"

    Pools are used to limit parallelism for specific sets of tasks. Each pool
    has a certain number of slots, and tasks assigned to a pool will only run
    if there are available slots. This is useful for limiting concurrent access
    to resources like databases or external APIs.

    Returns pool information including:
    - name: Name of the pool
    - slots: Total number of available slots in the pool
    - occupied_slots: Number of currently occupied slots
    - running_slots: Number of slots with running tasks
    - queued_slots: Number of slots with queued tasks
    - open_slots: Number of available slots (slots - occupied_slots)
    - description: Human-readable description of the pool's purpose

    Returns:
        JSON with list of all pools and their current utilization
    """
    return _list_pools_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def list_plugins() -> str:
    """Get information about installed Airflow plugins.

    Use this tool when the user asks about:
    - "What plugins are installed?" or "List all plugins"
    - "Show me the plugins" or "Which plugins are enabled?"
    - "Is plugin X installed?" or "Do we have any custom plugins?"
    - "What's in the plugins directory?"

    Plugins extend Airflow functionality by adding custom operators, hooks,
    views, menu items, or other components. This returns information about
    all plugins discovered by Airflow's plugin system.

    Returns information about installed plugins including:
    - name: Name of the plugin
    - hooks: Custom hooks provided by the plugin
    - executors: Custom executors provided by the plugin
    - macros: Custom macros provided by the plugin
    - flask_blueprints: Flask blueprints for custom UI pages
    - appbuilder_views: Flask-AppBuilder views for admin interface
    - appbuilder_menu_items: Custom menu items in the UI

    Returns:
        JSON with list of all installed plugins and their components
    """
    return _list_plugins_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def list_providers() -> str:
    """Get information about installed Airflow provider packages.

    Use this tool when the user asks about:
    - "What providers are installed?" or "List all providers"
    - "What integrations are available?" or "Show me installed packages"
    - "Do we have the AWS provider?" or "Is the Snowflake provider installed?"
    - "What version of provider X is installed?"

    Returns information about installed provider packages including:
    - package_name: Name of the provider package (e.g., "apache-airflow-providers-amazon")
    - version: Version of the provider package
    - description: What the provider does
    - provider_info: Details about operators, hooks, and sensors included

    Returns:
        JSON with list of all installed provider packages and their details
    """
    return _list_providers_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def get_variable(variable_key: str) -> str:
    """Get a specific Airflow variable by key.

    Use this tool when the user asks about:
    - "What's the value of variable X?" or "Show me variable Y"
    - "Get variable Z" or "What does variable A contain?"
    - "What's stored in variable B?" or "Look up variable C"

    Variables are key-value pairs stored in Airflow's metadata database that
    can be accessed by DAGs at runtime. They're commonly used for configuration
    values, API keys, or other settings that need to be shared across DAGs.

    Returns variable information including:
    - key: The variable's key/name
    - value: The variable's value (may be masked if marked as sensitive)
    - description: Optional description of the variable's purpose

    Args:
        variable_key: The key/name of the variable to retrieve

    Returns:
        JSON with the variable's key, value, and metadata
    """
    return _get_variable_impl(
        variable_key=variable_key,
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def list_variables() -> str:
    """Get all Airflow variables (key-value configuration pairs).

    Use this tool when the user asks about:
    - "What variables are configured?" or "List all variables"
    - "Show me the variables" or "What variables exist?"
    - "What configuration variables are available?"
    - "Show me all variable keys"

    Variables are key-value pairs stored in Airflow's metadata database that
    can be accessed by DAGs at runtime. They're commonly used for configuration
    values, environment-specific settings, or other data that needs to be
    shared across DAGs without hardcoding in the DAG files.

    Returns variable information including:
    - key: The variable's key/name
    - value: The variable's value (may be masked if marked as sensitive)
    - description: Optional description of the variable's purpose

    IMPORTANT: Sensitive variables (like passwords, API keys) may have their
    values masked in the response for security reasons.

    Returns:
        JSON with list of all variables and their values
    """
    return _list_variables_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def get_airflow_version() -> str:
    """Get version information for the Airflow instance.

    Use this tool when the user asks about:
    - "What version of Airflow is running?" or "Show me the Airflow version"
    - "What's the Airflow version?" or "Which Airflow release is this?"
    - "What version is installed?" or "Check Airflow version"
    - "Is this Airflow 2 or 3?" or "What's the version number?"

    Returns version information including:
    - version: The Airflow version string (e.g., "2.8.0", "3.0.0")
    - git_version: Git commit hash if available

    This is useful for:
    - Determining API compatibility
    - Checking if features are available in this version
    - Troubleshooting version-specific issues
    - Verifying upgrade success

    Returns:
        JSON with Airflow version information
    """
    return _get_version_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )


@mcp.tool()
def get_airflow_config() -> str:
    """Get Airflow instance configuration and settings.

    Use this tool when the user asks about:
    - "What's the Airflow configuration?" or "Show me Airflow settings"
    - "What's the executor type?" or "How is Airflow configured?"
    - "What's the parallelism setting?"
    - Database connection, logging, or scheduler settings
    - Finding specific configuration values

    Returns all Airflow configuration organized by sections:
    - [core]: Basic Airflow settings (executor, dags_folder, parallelism)
    - [database]: Database connection and settings
    - [webserver]: Web UI configuration (port, workers, auth)
    - [scheduler]: Scheduler behavior and intervals
    - [logging]: Log locations and formatting
    - [api]: REST API configuration
    - [operators]: Default operator settings
    - And many more sections...

    Each setting includes:
    - key: Configuration parameter name
    - value: Current value
    - source: Where the value came from (default, env var, config file)

    Returns:
        JSON with complete Airflow configuration organized by sections
    """
    return _get_config_impl(
        airflow_url=_config.url,
        auth_token=_config.auth_token,
    )
