"""Adapter for Airflow 3.x API."""

from typing import Any

from astro_airflow_mcp.adapters.base import AirflowAdapter, NotFoundError


class AirflowV3Adapter(AirflowAdapter):
    """Adapter for Airflow 3.x API (/api/v2).

    Authentication is handled by the token_getter callback provided at init time,
    which should return a valid JWT token from the central TokenManager.

    See: https://github.com/apache/airflow-client-python
    """

    @property
    def api_base_path(self) -> str:
        """API base path for Airflow 3.x."""
        return "/api/v2"

    def list_dags(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List all DAGs with optional filters.

        Args:
            limit: Maximum number of DAGs to return
            offset: Offset for pagination
            **kwargs: Additional filters (e.g., tags, paused, only_active)
                      Passed through to Airflow API for forward compatibility.
        """
        return self._call("dags", params={"limit": limit, "offset": offset}, **kwargs)

    def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get details of a specific DAG."""
        return self._call(f"dags/{dag_id}")

    def get_dag_source(self, dag_id: str) -> dict[str, Any]:
        """Get source code of a DAG.

        Note: Airflow 3 directly uses dag_id for source lookup.
        """
        return self._call(f"dagSources/{dag_id}")

    def list_dag_runs(
        self, dag_id: str | None = None, limit: int = 100, offset: int = 0, **kwargs: Any
    ) -> dict[str, Any]:
        """List DAG runs.

        Args:
            dag_id: Optional DAG ID. Use '~' or None for all DAGs.
            limit: Maximum number of runs to return
            offset: Offset for pagination
            **kwargs: Additional filters (e.g., state, start_date_gte)
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

    def list_tasks(self, dag_id: str) -> dict[str, Any]:
        """List all tasks in a DAG."""
        return self._call(f"dags/{dag_id}/tasks")

    def get_task(self, dag_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a specific task."""
        return self._call(f"dags/{dag_id}/tasks/{task_id}")

    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a task instance."""
        return self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")

    def list_assets(self, limit: int = 100, offset: int = 0, **kwargs: Any) -> dict[str, Any]:
        """List assets (renamed from 'datasets' in Airflow 3)."""
        try:
            return self._call("assets", params={"limit": limit, "offset": offset}, **kwargs)
        except NotFoundError:
            return self._handle_not_found(
                "assets", alternative="Try 'datasets' endpoint if using older Airflow 3.x"
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

        Args:
            dag_ids: Optional list of DAG IDs to get stats for.
                     If None, returns stats for all DAGs.

        Note:
            Airflow 3.2.0 has bugs where:
            1. Calling without dag_ids causes a 500 error
            2. Multiple dag_ids in one call causes a 500 error
            3. DAGs with dag_display_name=None cause a 500 error

            We work around these by calling once per DAG and handling errors.

        Available in Airflow 3.0+. Returns counts by DAG and state.
        """
        try:
            # Workaround for Airflow 3.2.0 bugs
            if dag_ids:
                # Call once per DAG to avoid multiple dag_ids bug
                all_results: dict[str, Any] = {"dags": [], "total_entries": 0, "errors": []}
                for dag_id in dag_ids:
                    try:
                        result = self._call("dagStats", params={"dag_ids": dag_id})
                        all_results["dags"].extend(result.get("dags", []))
                        all_results["total_entries"] += result.get("total_entries", 0)
                    except Exception as e:
                        # Some DAGs may fail due to dag_display_name=None bug
                        all_results["errors"].append(
                            {
                                "dag_id": dag_id,
                                "error": str(e),
                                "note": "Airflow 3.2.0 bug: dag_display_name may be None",
                            }
                        )
                if not all_results["errors"]:
                    del all_results["errors"]
                return all_results
            else:
                # Pass empty dag_ids to avoid 500 error
                return self._call("dagStats", params={"dag_ids": ""})
        except NotFoundError:
            return self._handle_not_found(
                "dagStats", alternative="Use list_dag_runs to compute statistics"
            )

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
        """Get Airflow configuration."""
        return self._call("config")

    # Airflow 3.x specific features

    def get_task_instances(
        self, dag_id: str, dag_run_id: str, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        """List all task instances for a DAG run.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            limit: Maximum number of task instances to return
            offset: Offset for pagination

        Available in Airflow 3.0+.
        """
        try:
            return self._call(
                f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
                params={"limit": limit, "offset": offset},
            )
        except NotFoundError:
            return self._handle_not_found(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")

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

        Available in Airflow 3.0+.
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
