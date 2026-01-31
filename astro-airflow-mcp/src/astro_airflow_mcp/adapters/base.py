"""Base adapter interface for Airflow API clients."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import httpx


class NotFoundError(Exception):
    """Raised when an API endpoint returns 404."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        super().__init__(f"Endpoint not found: {endpoint}")


class AirflowAdapter(ABC):
    """Abstract base class for Airflow API adapters.

    Adapters wrap version-specific API calls and provide a consistent
    interface for the MCP server tools.
    """

    def __init__(
        self,
        airflow_url: str,
        version: str,
        token_getter: Callable[[], str | None] | None = None,
        basic_auth_getter: Callable[[], tuple[str, str] | None] | None = None,
    ):
        """Initialize adapter with connection details.

        Args:
            airflow_url: Base URL of Airflow webserver
            version: Full version string (e.g., "3.1.3")
            token_getter: Callable that returns current auth token (or None)
            basic_auth_getter: Callable that returns (username, password) tuple or None
                             Used as fallback for Airflow 2.x which doesn't support token auth
        """
        self.airflow_url = airflow_url
        self.version = version
        self._token_getter = token_getter
        self._basic_auth_getter = basic_auth_getter

    @property
    @abstractmethod
    def api_base_path(self) -> str:
        """API base path for this version (e.g., '/api/v1' or '/api/v2')."""

    def _setup_auth(self) -> tuple[dict[str, str], tuple[str, str] | None]:
        """Set up authentication using token or basic auth.

        Tries token-based auth first (Airflow 3.x), falls back to basic auth
        (Airflow 2.x) if token is not available.

        Returns:
            Tuple of (headers dict, auth tuple or None)
        """
        headers: dict[str, str] = {}
        auth: tuple[str, str] | None = None

        # Try token-based auth first
        if self._token_getter:
            token = self._token_getter()
            if token:
                headers["Authorization"] = f"Bearer {token}"
                return headers, None

        # Fall back to basic auth if no token available
        if self._basic_auth_getter:
            auth = self._basic_auth_getter()

        return headers, auth

    def _call(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        **extra_params: Any,
    ) -> dict[str, Any]:
        """Make HTTP call to Airflow API.

        Args:
            endpoint: API endpoint path (without base path)
            params: Query parameters
            **extra_params: Additional query parameters (pass-through)

        Returns:
            Parsed JSON response

        Raises:
            NotFoundError: If endpoint returns 404
            Exception: For other HTTP errors
        """
        headers, auth = self._setup_auth()
        headers["Accept"] = "application/json"
        url = f"{self.airflow_url}{self.api_base_path}/{endpoint}"

        # Merge params with extra_params for forward compatibility
        all_params = {**(params or {}), **extra_params}
        # Remove None values
        all_params = {k: v for k, v in all_params.items() if v is not None}

        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=all_params, headers=headers, auth=auth)

            if response.status_code == 404:
                raise NotFoundError(endpoint)

            response.raise_for_status()
            return response.json()

    def _post(
        self,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP POST call to Airflow API.

        Args:
            endpoint: API endpoint path (without base path)
            json_data: JSON body to send

        Returns:
            Parsed JSON response

        Raises:
            NotFoundError: If endpoint returns 404
            Exception: For other HTTP errors
        """
        headers, auth = self._setup_auth()
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        url = f"{self.airflow_url}{self.api_base_path}/{endpoint}"

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=json_data, headers=headers, auth=auth)

            if response.status_code == 404:
                raise NotFoundError(endpoint)

            response.raise_for_status()
            return response.json()

    def _patch(
        self,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP PATCH call to Airflow API.

        Args:
            endpoint: API endpoint path (without base path)
            json_data: JSON body to send

        Returns:
            Parsed JSON response

        Raises:
            NotFoundError: If endpoint returns 404
            Exception: For other HTTP errors
        """
        headers, auth = self._setup_auth()
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        url = f"{self.airflow_url}{self.api_base_path}/{endpoint}"

        with httpx.Client(timeout=30.0) as client:
            response = client.patch(url, json=json_data, headers=headers, auth=auth)

            if response.status_code == 404:
                raise NotFoundError(endpoint)

            response.raise_for_status()
            return response.json()

    def _delete(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        """Make HTTP DELETE call to Airflow API.

        Args:
            endpoint: API endpoint path (without base path)

        Returns:
            Parsed JSON response (or empty dict if no content)

        Raises:
            NotFoundError: If endpoint returns 404
            Exception: For other HTTP errors
        """
        headers, auth = self._setup_auth()
        headers["Accept"] = "application/json"
        url = f"{self.airflow_url}{self.api_base_path}/{endpoint}"

        with httpx.Client(timeout=30.0) as client:
            response = client.delete(url, headers=headers, auth=auth)

            if response.status_code == 404:
                raise NotFoundError(endpoint)

            response.raise_for_status()
            # DELETE often returns 204 No Content
            if response.status_code == 204 or not response.text:
                return {}
            return response.json()

    def raw_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        raw_endpoint: bool = False,
    ) -> dict[str, Any]:
        """Make raw HTTP request to Airflow API.

        This method provides direct access to any Airflow REST API endpoint,
        similar to `gh api` for GitHub. It automatically handles authentication
        and API version prefixes based on the Airflow version.

        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE)
            endpoint: API endpoint path (e.g., "dags" or "/dags")
            params: Query parameters
            json_data: JSON body for POST/PATCH/PUT requests
            headers: Additional headers to include
            raw_endpoint: If True, use endpoint path as-is without API version prefix.
                         Useful for endpoints like /health that don't have version prefix.

        Returns:
            Dict with 'status_code', 'headers', 'body' keys containing the raw response.

        Example:
            # GET /api/v1/dags (AF2) or /api/v2/dags (AF3)
            adapter.raw_request("GET", "dags")

            # GET /health (no version prefix)
            adapter.raw_request("GET", "health", raw_endpoint=True)

            # POST with JSON body
            adapter.raw_request("POST", "variables", json_data={"key": "x", "value": "y"})
        """
        auth_headers, auth = self._setup_auth()
        all_headers = {**auth_headers, **(headers or {})}

        # Build URL: with or without version prefix
        endpoint = endpoint.lstrip("/")
        if raw_endpoint:
            url = f"{self.airflow_url}/{endpoint}"
        else:
            url = f"{self.airflow_url}{self.api_base_path}/{endpoint}"

        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                headers=all_headers,
                auth=auth,
            )

        # Parse body - handle empty responses and non-JSON
        body: Any = None
        if response.text:
            try:
                body = response.json()
            except ValueError:
                # Not JSON, return as text
                body = response.text

        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }

    def _handle_not_found(self, endpoint: str, alternative: str | None = None) -> dict[str, Any]:
        """Create a structured response for unavailable endpoints.

        Args:
            endpoint: The endpoint that was not found
            alternative: Suggested alternative approach

        Returns:
            Dict with availability info and alternative
        """
        result: dict[str, Any] = {
            "available": False,
            "note": f"Endpoint '{endpoint}' not available in Airflow {self.version}",
        }
        if alternative:
            result["alternative"] = alternative
        return result

    def _filter_passwords(self, data: dict[str, Any]) -> dict[str, Any]:
        """Filter password fields from connection data for security.

        Args:
            data: Dict containing connection data

        Returns:
            Dict with passwords filtered out
        """
        if "connections" in data:
            for conn in data["connections"]:
                if "password" in conn:
                    conn["password"] = "***FILTERED***"  # nosec B105
        return data

    # DAG Operations
    @abstractmethod
    def list_dags(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List all DAGs."""

    @abstractmethod
    def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get details of a specific DAG."""

    @abstractmethod
    def get_dag_source(self, dag_id: str) -> dict[str, Any]:
        """Get source code of a DAG."""

    @abstractmethod
    def pause_dag(self, dag_id: str) -> dict[str, Any]:
        """Pause a DAG to prevent new runs from being scheduled.

        Args:
            dag_id: The ID of the DAG to pause

        Returns:
            Updated DAG details with is_paused=True
        """

    @abstractmethod
    def unpause_dag(self, dag_id: str) -> dict[str, Any]:
        """Unpause a DAG to allow new runs to be scheduled.

        Args:
            dag_id: The ID of the DAG to unpause

        Returns:
            Updated DAG details with is_paused=False
        """

    # DAG Run Operations
    @abstractmethod
    def list_dag_runs(
        self, dag_id: str | None = None, limit: int = 100, offset: int = 0, **kwargs: Any
    ) -> dict[str, Any]:
        """List DAG runs."""

    @abstractmethod
    def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get details of a specific DAG run."""

    @abstractmethod
    def trigger_dag_run(
        self, dag_id: str, logical_date: str | None = None, conf: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger a new DAG run.

        Args:
            dag_id: The ID of the DAG to trigger
            logical_date: Optional logical/execution date for the run
            conf: Optional configuration dictionary to pass to the DAG run

        Returns:
            Details of the triggered DAG run
        """

    # Task Operations
    @abstractmethod
    def list_tasks(self, dag_id: str) -> dict[str, Any]:
        """List all tasks in a DAG."""

    @abstractmethod
    def get_task(self, dag_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a specific task."""

    @abstractmethod
    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a task instance."""

    @abstractmethod
    def get_task_instances(
        self, dag_id: str, dag_run_id: str, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """List all task instances for a DAG run.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            limit: Maximum number of task instances to return
            offset: Offset for pagination
        """

    @abstractmethod
    def get_task_logs(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        try_number: int = 1,
        map_index: int = -1,
        full_content: bool = True,
    ) -> dict[str, Any]:
        """Get logs for a specific task instance.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            task_id: Task ID
            try_number: Task try number (1-indexed, default 1)
            map_index: Map index for mapped tasks (-1 for unmapped, default -1)
            full_content: Whether to return full log content (default True)
        """

    # Asset/Dataset Operations
    @abstractmethod
    def list_assets(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List assets/datasets."""

    @abstractmethod
    def list_asset_events(
        self,
        limit: int = 100,
        offset: int = 0,
        source_dag_id: str | None = None,
        source_run_id: str | None = None,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        """List asset/dataset events with optional filters.

        Args:
            limit: Maximum number of events to return
            offset: Offset for pagination
            source_dag_id: Filter by DAG that produced the event
            source_run_id: Filter by DAG run that produced the event
            source_task_id: Filter by task that produced the event

        Returns:
            Dict with 'asset_events' list (normalized key for both Airflow 2/3)
        """

    @abstractmethod
    def get_dag_run_upstream_asset_events(
        self,
        dag_id: str,
        dag_run_id: str,
    ) -> dict[str, Any]:
        """Get asset events that triggered a specific DAG run.

        This is used to verify causation - which asset events caused this
        DAG run to be scheduled (data-aware scheduling).

        Args:
            dag_id: The DAG ID
            dag_run_id: The DAG run ID

        Returns:
            Dict with 'asset_events' list showing which events triggered this run
        """

    # Variable Operations
    @abstractmethod
    def list_variables(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow variables."""

    @abstractmethod
    def get_variable(self, variable_key: str) -> dict[str, Any]:
        """Get a specific variable."""

    # Connection Operations
    @abstractmethod
    def list_connections(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow connections (passwords filtered)."""

    # Pool Operations
    @abstractmethod
    def list_pools(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow pools."""

    @abstractmethod
    def get_pool(self, pool_name: str) -> dict[str, Any]:
        """Get details of a specific pool."""

    # DAG Statistics and Warnings
    @abstractmethod
    def get_dag_stats(self, dag_ids: list[str] | None = None) -> dict[str, Any]:
        """Get DAG run statistics by state.

        Args:
            dag_ids: Optional list of DAG IDs to get stats for.
        """

    @abstractmethod
    def list_dag_warnings(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List DAG warnings."""

    @abstractmethod
    def list_import_errors(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List import errors from DAG files."""

    # Plugin and Provider Operations
    @abstractmethod
    def list_plugins(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List installed Airflow plugins."""

    @abstractmethod
    def list_providers(self) -> dict[str, Any]:
        """List installed Airflow provider packages."""

    # System Operations
    @abstractmethod
    def get_version(self) -> dict[str, Any]:
        """Get Airflow version info."""

    @abstractmethod
    def get_config(self) -> dict[str, Any]:
        """Get Airflow configuration."""

    # Task Instance Operations
    @abstractmethod
    def clear_task_instances(
        self,
        dag_id: str,
        dag_run_id: str,
        task_ids: list[str],
        dry_run: bool = True,
        only_failed: bool = False,
        include_downstream: bool = False,
        include_upstream: bool = False,
        reset_dag_runs: bool = True,
    ) -> dict[str, Any]:
        """Clear task instances to allow re-execution.

        Args:
            dag_id: The ID of the DAG
            dag_run_id: The ID of the DAG run
            task_ids: List of task IDs to clear
            dry_run: If True, return what would be cleared without clearing
            only_failed: Only clear failed task instances
            include_downstream: Also clear downstream tasks
            include_upstream: Also clear upstream tasks
            reset_dag_runs: Reset the DAG run state to 'queued'

        Returns:
            Dict with list of cleared task instances
        """
