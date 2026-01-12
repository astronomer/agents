"""FastMCP server for Airflow integration."""

import json
import time
from typing import Any

import requests
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from astro_airflow_mcp.adapters import AirflowAdapter, create_adapter
from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Default configuration values
DEFAULT_AIRFLOW_URL = "http://localhost:8080"
DEFAULT_LIMIT = 100
DEFAULT_OFFSET = 0
# Buffer time before token expiry to trigger refresh (5 minutes)
TOKEN_REFRESH_BUFFER_SECONDS = 300
# Terminal states for DAG runs (polling stops when reached)
TERMINAL_DAG_RUN_STATES = {"success", "failed", "upstream_failed"}


class AirflowTokenManager:
    """Manages JWT token lifecycle for Airflow API authentication.

    Handles fetching tokens from /auth/token endpoint (Airflow 3.x),
    automatic refresh when tokens expire, and supports both credential-based
    and credential-less (all_admins mode) authentication.

    For Airflow 2.x (which doesn't have /auth/token), this manager will detect
    the 404 and stop attempting token fetches, falling back to basic auth.
    """

    def __init__(
        self,
        airflow_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        """Initialize the token manager.

        Args:
            airflow_url: Base URL of the Airflow webserver
            username: Optional username for token authentication
            password: Optional password for token authentication
        """
        self.airflow_url = airflow_url
        self.username = username
        self.password = password
        self._token: str | None = None
        self._token_fetched_at: float | None = None
        # Default token lifetime of 30 minutes if not provided by server
        self._token_lifetime_seconds: float = 1800
        # Track if token endpoint is available (False for Airflow 2.x)
        self._token_endpoint_available: bool | None = None

    def get_token(self) -> str | None:
        """Get current token, fetching/refreshing if needed.

        Returns:
            JWT token string, or None if token fetch fails or endpoint unavailable
        """
        # If we've determined the endpoint doesn't exist, don't try again
        if self._token_endpoint_available is False:
            return None
        if self._should_refresh():
            self._fetch_token()
        return self._token

    def get_basic_auth(self) -> tuple[str, str] | None:
        """Get basic auth credentials for Airflow 2.x fallback.

        Returns:
            Tuple of (username, password) if available, None otherwise
        """
        if self.username and self.password:
            return (self.username, self.password)
        return None

    def is_token_endpoint_available(self) -> bool | None:
        """Check if the token endpoint is available.

        Returns:
            True if available (Airflow 3.x), False if not (Airflow 2.x),
            None if not yet determined.
        """
        return self._token_endpoint_available

    def _should_refresh(self) -> bool:
        """Check if token needs refresh (expired or not yet fetched).

        Returns:
            True if token should be refreshed
        """
        if self._token is None:
            return True
        if self._token_fetched_at is None:
            return True
        # Refresh if we're within the buffer time of expiry
        elapsed = time.time() - self._token_fetched_at
        return elapsed >= (self._token_lifetime_seconds - TOKEN_REFRESH_BUFFER_SECONDS)

    def _fetch_token(self) -> None:
        """Fetch new token from /auth/token endpoint.

        Tries credential-less GET first if no username/password provided,
        otherwise uses POST with credentials.

        For Airflow 2.x (404 response), marks the endpoint as unavailable
        and stops future attempts.
        """
        token_url = f"{self.airflow_url}/auth/token"

        try:
            if self.username and self.password:
                # Use credentials to fetch token
                logger.debug("Fetching token with username/password credentials")
                response = requests.post(
                    token_url,
                    json={"username": self.username, "password": self.password},
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
            else:
                # Try credential-less fetch (for all_admins mode)
                logger.debug("Attempting credential-less token fetch")
                response = requests.get(token_url, timeout=30)

            # Check for 404 - indicates Airflow 2.x without token endpoint
            if response.status_code == 404:
                self._token_endpoint_available = False
                self._token = None
                # Default to admin:admin for Airflow 2.x if no credentials provided
                if not self.username and not self.password:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Defaulting to admin:admin for basic auth."
                    )
                    self.username = "admin"  # nosec B105 - default for local dev
                    self.password = "admin"  # nosec B105 - default for local dev
                else:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Using provided credentials for basic auth."
                    )
                return

            response.raise_for_status()
            data = response.json()

            # Extract token from response
            # Airflow returns {"access_token": "...", "token_type": "bearer"}
            if "access_token" in data:
                self._token = data["access_token"]
                self._token_fetched_at = time.time()
                self._token_endpoint_available = True
                # Use expires_in if provided, otherwise keep default
                if "expires_in" in data:
                    self._token_lifetime_seconds = float(data["expires_in"])
                logger.info("Successfully fetched Airflow API token")
            else:
                logger.warning(f"Unexpected token response format: {data}")
                self._token = None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch token from {token_url}: {e}")
            self._token = None

    def invalidate(self) -> None:
        """Force token refresh on next request."""
        self._token = None
        self._token_fetched_at = None


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

# Add logging middleware to log all MCP tool calls
mcp.add_middleware(LoggingMiddleware(include_payloads=True))


# Global configuration for Airflow API access
class AirflowConfig:
    """Global configuration for Airflow API access."""

    def __init__(self):
        self.url: str = DEFAULT_AIRFLOW_URL
        self.auth_token: str | None = None
        self.token_manager: AirflowTokenManager | None = None


_config = AirflowConfig()

# Global adapter instance (lazy-initialized)
_adapter: AirflowAdapter | None = None


def _get_adapter() -> AirflowAdapter:
    """Get or create the global adapter instance.

    The adapter is lazy-initialized on first use and will automatically
    detect the Airflow version and create the appropriate adapter type.

    Returns:
        Version-specific AirflowAdapter instance
    """
    global _adapter
    if _adapter is None:
        logger.info(f"Initializing adapter for {_config.url}")
        _adapter = create_adapter(
            airflow_url=_config.url,
            token_getter=_get_auth_token,
            basic_auth_getter=_get_basic_auth,
        )
        logger.info(f"Created adapter for Airflow {_adapter.version}")
    return _adapter


def _reset_adapter() -> None:
    """Reset the global adapter (e.g., when config changes)."""
    global _adapter
    _adapter = None


def configure(
    url: str | None = None,
    auth_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Configure global Airflow connection settings.

    Args:
        url: Base URL of Airflow webserver
        auth_token: Direct bearer token for authentication (takes precedence)
        username: Username for token-based authentication
        password: Password for token-based authentication

    Note:
        If auth_token is provided, it will be used directly.
        If username/password are provided (without auth_token), a token manager
        will be created to fetch and refresh tokens automatically.
        If neither is provided, credential-less token fetch will be attempted.
    """
    if url:
        _config.url = url
    if auth_token:
        # Direct token takes precedence - no token manager needed
        _config.auth_token = auth_token
        _config.token_manager = None
    elif username or password:
        # Use token manager with credentials
        _config.auth_token = None
        _config.token_manager = AirflowTokenManager(
            airflow_url=_config.url,
            username=username,
            password=password,
        )
    else:
        # No auth provided - try credential-less token manager
        _config.auth_token = None
        _config.token_manager = AirflowTokenManager(
            airflow_url=_config.url,
            username=None,
            password=None,
        )

    # Reset adapter so it will be re-created with new config
    _reset_adapter()


def _get_auth_token() -> str | None:
    """Get the current authentication token.

    Returns:
        Bearer token string, or None if no authentication configured
    """
    # Direct token takes precedence
    if _config.auth_token:
        return _config.auth_token
    # Otherwise use token manager
    if _config.token_manager:
        return _config.token_manager.get_token()
    return None


def _get_basic_auth() -> tuple[str, str] | None:
    """Get basic auth credentials for Airflow 2.x fallback.

    Returns:
        Tuple of (username, password) if available, None otherwise
    """
    if _config.token_manager:
        return _config.token_manager.get_basic_auth()
    return None


def _invalidate_token() -> None:
    """Invalidate the current token to force refresh on next request."""
    if _config.token_manager:
        _config.token_manager.invalidate()


# Helper functions for API calls and response formatting
def _call_airflow_api(
    endpoint: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    params: dict[str, Any] | None = None,
    auth_token: str | None = None,
    _retry: bool = True,
) -> dict[str, Any]:
    """Call Airflow REST API with error handling and optional authentication.

    Args:
        endpoint: API endpoint path (e.g., 'dags', 'dagRuns')
        airflow_url: Base URL of the Airflow webserver
        params: Optional query parameters
        auth_token: Optional Bearer token for token-based authentication
        _retry: Internal flag to control retry on auth failure (default True)

    Returns:
        Parsed JSON response from the API

    Raises:
        Exception: If the API call fails with error details

    Note:
        If auth_token is provided, Bearer token authentication is used.
        If not provided, the global token (from token manager or config) is used.
        On 401/403 errors, the token is invalidated and the request is retried once.
    """
    try:
        api_url = f"{airflow_url}/api/v2/{endpoint}"
        headers: dict[str, str] = {}

        # Handle authentication - use provided token or get from global config
        token = auth_token if auth_token else _get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(api_url, params=params, headers=headers, timeout=30)

        # Handle auth errors with retry
        if response.status_code in (401, 403) and _retry and not auth_token:
            logger.debug(f"Auth error ({response.status_code}), invalidating token and retrying")
            _invalidate_token()
            return _call_airflow_api(endpoint, airflow_url, params, auth_token=None, _retry=False)

        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error connecting to Airflow API: {str(e)}") from e
    except Exception as e:
        raise Exception(f"Error calling API endpoint '{endpoint}': {str(e)}") from e


def _post_airflow_api(
    endpoint: str,
    airflow_url: str = DEFAULT_AIRFLOW_URL,
    json_data: dict[str, Any] | None = None,
    auth_token: str | None = None,
    _retry: bool = True,
) -> dict[str, Any]:
    """Call Airflow REST API with POST method.

    Args:
        endpoint: API endpoint path (e.g., 'dags/{dag_id}/dagRuns')
        airflow_url: Base URL of the Airflow webserver
        json_data: Optional JSON body to send with the request
        auth_token: Optional Bearer token for token-based authentication
        _retry: Internal flag to control retry on auth failure (default True)

    Returns:
        Parsed JSON response from the API

    Raises:
        Exception: If the API call fails with error details

    Note:
        If auth_token is provided, Bearer token authentication is used.
        If not provided, the global token (from token manager or config) is used.
        On 401/403 errors, the token is invalidated and the request is retried once.
    """
    try:
        api_url = f"{airflow_url}/api/v2/{endpoint}"
        headers: dict[str, str] = {"Content-Type": "application/json"}

        # Handle authentication - use provided token or get from global config
        token = auth_token if auth_token else _get_auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.post(api_url, json=json_data, headers=headers, timeout=30)

        # Handle auth errors with retry
        if response.status_code in (401, 403) and _retry and not auth_token:
            logger.debug(f"Auth error ({response.status_code}), invalidating token and retrying")
            _invalidate_token()
            return _post_airflow_api(
                endpoint, airflow_url, json_data, auth_token=None, _retry=False
            )

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

    total_entries = data.get("total_entries", len(items))
    result: dict[str, Any] = {
        f"total_{key_name}": total_entries,
        "returned_count": len(items),
        key_name: items,
    }
    return json.dumps(result, indent=2)


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
        else:
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
        else:
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
        else:
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
    return _list_dag_runs_impl()


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

        failed_states = {"failed", "upstream_failed"}
        failed_tasks = []

        if "task_instances" in data:
            for task in data["task_instances"]:
                if task.get("state") in failed_states:
                    failed_tasks.append(
                        {
                            "task_id": task.get("task_id"),
                            "state": task.get("state"),
                            "try_number": task.get("try_number"),
                            "start_date": task.get("start_date"),
                            "end_date": task.get("end_date"),
                        }
                    )

        return failed_tasks
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
        timeout: Maximum time to wait in seconds (default: 1800.0 / 30 minutes)

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

    Default timeout is 30 minutes. Adjust the `timeout` parameter for longer DAGs.

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
        timeout: Maximum time to wait in seconds (default: 1800.0 / 30 minutes)

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


def _list_assets_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing assets from Airflow.

    Args:
        limit: Maximum number of assets to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of assets with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_assets(limit=limit, offset=offset)

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
    return _list_assets_impl()


def _list_connections_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing connections from Airflow.

    NOTE: This endpoint uses explicit field filtering (unlike other endpoints)
    to exclude sensitive information like passwords for security reasons.

    Args:
        limit: Maximum number of connections to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of connections with their metadata
    """

    try:
        adapter = _get_adapter()
        data = adapter.list_connections(limit=limit, offset=offset)

        if "connections" in data:
            connections = data["connections"]
            total_entries = data.get("total_entries", len(connections))

            # Note: Adapter's _filter_passwords already filters password field
            # but we apply additional explicit filtering for defense in depth
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
    return _list_connections_impl()


def _get_variable_impl(
    variable_key: str,
) -> str:
    """Internal implementation for getting a specific variable from Airflow.

    Args:
        variable_key: The key of the variable to get

    Returns:
        JSON string containing the variable details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_variable(variable_key)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_variables_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing variables from Airflow.

    Args:
        limit: Maximum number of variables to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of variables with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_variables(limit=limit, offset=offset)

        if "variables" in data:
            return _wrap_list_response(data["variables"], "variables", data)
        else:
            return f"No variables found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_version_impl() -> str:
    """Internal implementation for getting Airflow version information.

    Returns:
        JSON string containing the Airflow version information
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_version()
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _get_config_impl() -> str:
    """Internal implementation for getting Airflow configuration.

    Returns:
        JSON string containing the Airflow configuration organized by sections
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_config()

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
) -> str:
    """Internal implementation for getting details about a specific pool.

    Args:
        pool_name: The name of the pool to get details for

    Returns:
        JSON string containing the pool details
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_pool(pool_name)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


def _list_pools_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing pools from Airflow.

    Args:
        limit: Maximum number of pools to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of pools with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_pools(limit=limit, offset=offset)

        if "pools" in data:
            return _wrap_list_response(data["pools"], "pools", data)
        else:
            return f"No pools found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_plugins_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing installed plugins from Airflow.

    Args:
        limit: Maximum number of plugins to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of installed plugins
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_plugins(limit=limit, offset=offset)

        if "plugins" in data:
            return _wrap_list_response(data["plugins"], "plugins", data)
        else:
            return f"No plugins found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_providers_impl() -> str:
    """Internal implementation for listing installed providers from Airflow.

    Returns:
        JSON string containing the list of installed providers
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_providers()

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
    return _get_pool_impl(pool_name=pool_name)


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
    return _list_pools_impl()


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
    return _list_plugins_impl()


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
    return _list_providers_impl()


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
    return _get_variable_impl(variable_key=variable_key)


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
    return _list_variables_impl()


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
    return _get_version_impl()


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
    return _get_config_impl()


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


# =============================================================================
# MCP RESOURCES (Static, read-only information)
# =============================================================================


@mcp.resource("airflow://version")
def resource_version() -> str:
    """Get Airflow version information as a resource."""
    return _get_version_impl()


@mcp.resource("airflow://providers")
def resource_providers() -> str:
    """Get installed Airflow providers as a resource."""
    return _list_providers_impl()


@mcp.resource("airflow://plugins")
def resource_plugins() -> str:
    """Get installed Airflow plugins as a resource."""
    return _list_plugins_impl()


@mcp.resource("airflow://config")
def resource_config() -> str:
    """Get Airflow configuration as a resource."""
    return _get_config_impl()


# =============================================================================
# MCP PROMPTS (Guided workflows)
# =============================================================================


@mcp.prompt()
def troubleshoot_failed_dag(dag_id: str) -> str:
    """Step-by-step guide to troubleshoot a failed DAG.

    Args:
        dag_id: The DAG ID to troubleshoot
    """
    return f"""You are helping troubleshoot failures for DAG '{dag_id}'. Follow these steps:

1. First, use `explore_dag` to understand the DAG structure and check for any import errors.

2. Use `list_dag_runs` (filter by dag_id if possible) to find recent failed runs.

3. For each failed run, use `diagnose_dag_run` to get detailed information about:
   - Which tasks failed
   - The state of upstream tasks
   - Start/end times to understand duration

4. Based on the failed tasks, investigate:
   - Check task logs if available
   - Look at task dependencies (upstream_task_ids)
   - Check if any pools are at capacity using `list_pools`

5. Check system-wide issues using `get_system_health` to see if there are
   import errors or warnings that might be related.

6. Summarize your findings and provide recommendations for fixing the issues.

Start by running `explore_dag("{dag_id}")` to understand the DAG.
"""


@mcp.prompt()
def daily_health_check() -> str:
    """Morning health check workflow for Airflow."""
    return """You are performing a daily health check on the Airflow system. Follow these steps:

1. Start with `get_system_health` to get an overview of:
   - Import errors (broken DAG files)
   - DAG warnings
   - Overall system status

2. If there are import errors, prioritize investigating those first as they prevent DAGs from running.

3. Use `list_dag_runs` to see recent DAG run activity and identify any failures.

4. Check resource utilization with `list_pools` to see if any pools are at capacity.

5. Review `list_connections` to ensure all expected connections are configured.

6. Summarize the health status with:
   - Number of healthy vs problematic DAGs
   - Any blocking issues
   - Recommended actions

Start by running `get_system_health()` to assess the overall system state.
"""


@mcp.prompt()
def onboard_new_dag(dag_id: str) -> str:
    """Guide to understanding a new DAG.

    Args:
        dag_id: The DAG ID to learn about
    """
    return f"""You are helping someone understand the DAG '{dag_id}'. Provide a thorough overview:

1. Use `explore_dag` to get comprehensive DAG information including:
   - Schedule and timing
   - Owner and tags
   - All tasks and their relationships
   - Source code

2. Explain the DAG's purpose based on its description and task structure.

3. Walk through the task dependencies - what runs first, what runs in parallel,
   what are the critical path tasks.

4. Identify any external dependencies:
   - Check what connections the DAG might use with `list_connections`
   - Check for any assets/datasets it produces or consumes with `list_assets`

5. Show recent execution history with `list_dag_runs` filtered to this DAG.

6. Highlight any potential issues:
   - Is the DAG paused?
   - Are there any warnings?
   - What's the recent success/failure rate?

Start by running `explore_dag("{dag_id}")` to get the full picture.
"""
