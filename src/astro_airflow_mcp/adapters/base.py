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
        pass

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
        pass

    @abstractmethod
    def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get details of a specific DAG."""
        pass

    @abstractmethod
    def get_dag_source(self, dag_id: str) -> dict[str, Any]:
        """Get source code of a DAG."""
        pass

    @abstractmethod
    def pause_dag(self, dag_id: str) -> dict[str, Any]:
        """Pause a DAG to prevent new runs from being scheduled.

        Args:
            dag_id: The ID of the DAG to pause

        Returns:
            Updated DAG details with is_paused=True
        """
        pass

    @abstractmethod
    def unpause_dag(self, dag_id: str) -> dict[str, Any]:
        """Unpause a DAG to allow new runs to be scheduled.

        Args:
            dag_id: The ID of the DAG to unpause

        Returns:
            Updated DAG details with is_paused=False
        """
        pass

    # DAG Run Operations
    @abstractmethod
    def list_dag_runs(
        self, dag_id: str | None = None, limit: int = 100, offset: int = 0, **kwargs: Any
    ) -> dict[str, Any]:
        """List DAG runs."""
        pass

    @abstractmethod
    def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get details of a specific DAG run."""
        pass

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
        pass

    # Task Operations
    @abstractmethod
    def list_tasks(self, dag_id: str) -> dict[str, Any]:
        """List all tasks in a DAG."""
        pass

    @abstractmethod
    def get_task(self, dag_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a specific task."""
        pass

    @abstractmethod
    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a task instance."""
        pass

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
        pass

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
        pass

    # Asset/Dataset Operations
    @abstractmethod
    def list_assets(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List assets/datasets."""
        pass

    # Variable Operations
    @abstractmethod
    def list_variables(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow variables."""
        pass

    @abstractmethod
    def get_variable(self, variable_key: str) -> dict[str, Any]:
        """Get a specific variable."""
        pass

    # Connection Operations
    @abstractmethod
    def list_connections(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow connections (passwords filtered)."""
        pass

    # Pool Operations
    @abstractmethod
    def list_pools(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow pools."""
        pass

    @abstractmethod
    def get_pool(self, pool_name: str) -> dict[str, Any]:
        """Get details of a specific pool."""
        pass

    # DAG Statistics and Warnings
    @abstractmethod
    def get_dag_stats(self, dag_ids: list[str] | None = None) -> dict[str, Any]:
        """Get DAG run statistics by state.

        Args:
            dag_ids: Optional list of DAG IDs to get stats for.
        """
        pass

    @abstractmethod
    def list_dag_warnings(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List DAG warnings."""
        pass

    @abstractmethod
    def list_import_errors(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List import errors from DAG files."""
        pass

    # Plugin and Provider Operations
    @abstractmethod
    def list_plugins(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List installed Airflow plugins."""
        pass

    @abstractmethod
    def list_providers(self) -> dict[str, Any]:
        """List installed Airflow provider packages."""
        pass

    # System Operations
    @abstractmethod
    def get_version(self) -> dict[str, Any]:
        """Get Airflow version info."""
        pass

    @abstractmethod
    def get_config(self) -> dict[str, Any]:
        """Get Airflow configuration."""
        pass
