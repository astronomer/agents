"""Adapter for Airflow 2.x API."""

from typing import Any

from astro_airflow_mcp.adapters.base import AirflowAdapter, NotFoundError


class AirflowV2Adapter(AirflowAdapter):
    """Adapter for Airflow 2.x API (/api/v1)."""

    @property
    def api_base_path(self) -> str:
        """API base path for Airflow 2.x."""
        return "/api/v1"

    def list_dags(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List all DAGs."""
        return self._call("dags", params={"limit": limit, "offset": offset}, **kwargs)

    def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get details of a specific DAG."""
        return self._call(f"dags/{dag_id}")

    def get_dag_source(self, dag_id: str) -> dict[str, Any]:
        """Get source code of a DAG.

        Note: Airflow 2 requires a file_token, so we get DAG details first.
        """
        # First, get the DAG to get its file_token
        dag_data = self.get_dag(dag_id)
        file_token = dag_data.get("file_token")
        if not file_token:
            return {"error": "DAG has no file_token", "dag_id": dag_id}

        # Get source using file_token
        return self._call(f"dagSources/{file_token}")

    def pause_dag(self, dag_id: str) -> dict[str, Any]:
        """Pause a DAG to prevent new runs from being scheduled.

        Args:
            dag_id: The ID of the DAG to pause

        Returns:
            Updated DAG details with is_paused=True
        """
        return self._patch(f"dags/{dag_id}", json_data={"is_paused": True})

    def unpause_dag(self, dag_id: str) -> dict[str, Any]:
        """Unpause a DAG to allow new runs to be scheduled.

        Args:
            dag_id: The ID of the DAG to unpause

        Returns:
            Updated DAG details with is_paused=False
        """
        return self._patch(f"dags/{dag_id}", json_data={"is_paused": False})

    def list_dag_runs(
        self, dag_id: str | None = None, limit: int = 100, offset: int = 0, **kwargs: Any
    ) -> dict[str, Any]:
        """List DAG runs.

        Note: Airflow 2 requires dag_id. Use '~' to list runs for all DAGs.
        """
        dag_id_param = dag_id if dag_id else "~"
        return self._call(
            f"dags/{dag_id_param}/dagRuns",
            params={"limit": limit, "offset": offset},
            **kwargs,
        )

    def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get details of a specific DAG run."""
        return self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}")

    def trigger_dag_run(
        self, dag_id: str, logical_date: str | None = None, conf: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Trigger a new DAG run.

        Args:
            dag_id: The ID of the DAG to trigger
            logical_date: Optional execution date for the run (Airflow 2 uses execution_date)
            conf: Optional configuration dictionary to pass to the DAG run

        Returns:
            Details of the triggered DAG run
        """
        json_body: dict[str, Any] = {}
        if logical_date:
            # Airflow 2.x uses execution_date instead of logical_date
            json_body["execution_date"] = logical_date
        if conf:
            json_body["conf"] = conf

        return self._post(f"dags/{dag_id}/dagRuns", json_data=json_body)

    def list_tasks(self, dag_id: str) -> dict[str, Any]:
        """List all tasks in a DAG."""
        return self._call(f"dags/{dag_id}/tasks")

    def get_task(self, dag_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a specific task."""
        return self._call(f"dags/{dag_id}/tasks/{task_id}")

    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a task instance."""
        return self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")

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
        return self._call(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
            params={"limit": limit, "offset": offset},
        )

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
        endpoint = f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
        params: dict[str, Any] = {"full_content": full_content}
        if map_index != -1:
            params["map_index"] = map_index

        try:
            return self._call(endpoint, params=params)
        except NotFoundError:
            return self._handle_not_found(
                "task logs", alternative="Check if the task instance exists and has been executed"
            )

    def list_assets(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List assets (called 'datasets' in Airflow 2).

        Normalizes field names for consistency with Airflow 3:
        - 'datasets' -> 'assets'
        - 'consuming_dags' -> 'scheduled_dags'
        """
        try:
            data = self._call("datasets", params={"limit": limit, "offset": offset}, **kwargs)

            # Normalize field names
            if "datasets" in data:
                data["assets"] = data.pop("datasets")
                for asset in data.get("assets", []):
                    if "consuming_dags" in asset:
                        asset["scheduled_dags"] = asset.pop("consuming_dags")

            return data
        except NotFoundError:
            return self._handle_not_found(
                "datasets", alternative="Datasets/Assets were added in Airflow 2.4"
            )

    def list_asset_events(
        self,
        limit: int = 100,
        offset: int = 0,
        source_dag_id: str | None = None,
        source_run_id: str | None = None,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        """List dataset events (Airflow 2.x naming).

        Normalizes field names for consistency with Airflow 3:
        - 'dataset_events' -> 'asset_events'
        - 'dataset_uri' -> 'uri'
        - 'dataset_id' -> 'asset_id'
        """
        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if source_dag_id:
                params["source_dag_id"] = source_dag_id
            if source_run_id:
                params["source_run_id"] = source_run_id
            if source_task_id:
                params["source_task_id"] = source_task_id

            data = self._call("datasets/events", params=params)

            # Normalize field names
            if "dataset_events" in data:
                data["asset_events"] = data.pop("dataset_events")
                for event in data.get("asset_events", []):
                    if "dataset_uri" in event:
                        event["uri"] = event.pop("dataset_uri")
                    if "dataset_id" in event:
                        event["asset_id"] = event.pop("dataset_id")

            return data
        except NotFoundError:
            return self._handle_not_found(
                "datasets/events",
                alternative="Dataset events require Airflow 2.4+",
            )

    def get_dag_run_upstream_asset_events(
        self,
        dag_id: str,
        dag_run_id: str,
    ) -> dict[str, Any]:
        """Get upstream dataset events that triggered a DAG run (Airflow 2.x).

        Normalizes field names for consistency with Airflow 3:
        - 'dataset_events' -> 'asset_events'
        - 'dataset_uri' -> 'uri'
        - 'dataset_id' -> 'asset_id'
        """
        try:
            data = self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}/upstreamDatasetEvents")

            # Normalize field names
            if "dataset_events" in data:
                data["asset_events"] = data.pop("dataset_events")
                for event in data.get("asset_events", []):
                    if "dataset_uri" in event:
                        event["uri"] = event.pop("dataset_uri")
                    if "dataset_id" in event:
                        event["asset_id"] = event.pop("dataset_id")

            return data
        except NotFoundError:
            return self._handle_not_found(
                "upstreamDatasetEvents",
                alternative="This endpoint requires Airflow 2.4+ and a dataset-triggered run",
            )

    def list_variables(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow variables."""
        return self._call("variables", params={"limit": limit, "offset": offset})

    def get_variable(self, variable_key: str) -> dict[str, Any]:
        """Get a specific variable."""
        return self._call(f"variables/{variable_key}")

    def list_connections(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow connections (passwords filtered)."""
        data = self._call("connections", params={"limit": limit, "offset": offset})
        return self._filter_passwords(data)

    def list_pools(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow pools."""
        return self._call("pools", params={"limit": limit, "offset": offset})

    def get_pool(self, pool_name: str) -> dict[str, Any]:
        """Get details of a specific pool."""
        return self._call(f"pools/{pool_name}")

    def get_dag_stats(self, dag_ids: list[str] | None = None) -> dict[str, Any]:
        """Get DAG run statistics by state.

        Note: Airflow 2.x requires dag_ids parameter. If not provided, we fetch all DAGs first.
        """
        if dag_ids is None:
            # Airflow 2.x requires dag_ids, so fetch all DAGs first
            dags_response = self.list_dags(limit=1000)
            dag_ids = [dag["dag_id"] for dag in dags_response.get("dags", [])]

            if not dag_ids:
                return {"dags": [], "total_entries": 0}

        params = {"dag_ids": ",".join(dag_ids)}
        return self._call("dagStats", params=params)

    def list_dag_warnings(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List DAG warnings."""
        return self._call("dagWarnings", params={"limit": limit, "offset": offset})

    def list_import_errors(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List import errors from DAG files."""
        return self._call("importErrors", params={"limit": limit, "offset": offset})

    def list_plugins(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List installed Airflow plugins."""
        return self._call("plugins", params={"limit": limit, "offset": offset})

    def list_providers(self) -> dict[str, Any]:
        """List installed Airflow provider packages."""
        return self._call("providers")

    def get_version(self) -> dict[str, Any]:
        """Get Airflow version info."""
        return self._call("version")

    def get_config(self) -> dict[str, Any]:
        """Get Airflow configuration.

        Note: Airflow 2.x config endpoint may require specific permissions.
        """
        try:
            return self._call("config")
        except Exception as e:
            return {
                "error": str(e),
                "note": "Config endpoint may require expose_config=True in airflow.cfg",
            }

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
        json_body: dict[str, Any] = {
            "dag_run_id": dag_run_id,
            "task_ids": task_ids,
            "dry_run": dry_run,
            "only_failed": only_failed,
            "include_downstream": include_downstream,
            "include_upstream": include_upstream,
            "reset_dag_runs": reset_dag_runs,
        }

        try:
            return self._post(f"dags/{dag_id}/clearTaskInstances", json_data=json_body)
        except NotFoundError:
            return self._handle_not_found(
                "clearTaskInstances",
                alternative="clearTaskInstances requires Airflow 2.1+. Use the Airflow UI to clear task instances.",
            )
