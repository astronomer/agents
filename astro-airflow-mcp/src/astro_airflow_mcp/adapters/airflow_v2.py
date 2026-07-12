"""Adapter for Airflow 2.x API (tested against Airflow 2.11.0, /api/v1)."""

from typing import Any

import yaml

from astro_airflow_mcp.adapters.base import AirflowAdapter, NotFoundError


class AirflowV2Adapter(AirflowAdapter):
    """Adapter for Airflow 2.x REST API (/api/v1).

    Verified against Airflow 2.11.0 OpenAPI spec:
      airflow/api_connexion/openapi/v1.yaml

    Key differences from Airflow 3 (v2 adapter):
      - API base path: /api/v1  (not /api/v2)
      - Assets are called "datasets"  (field: 'datasets', not 'assets')
      - DAG runs use execution_date / logical_date (both accepted since 2.2)
      - Users/Roles endpoints are at /users, /roles (deprecated in 2.x, forwarded to FAB)
      - No backfill endpoint in stable REST API
      - Config endpoint needs expose_config=True
    """

    @property
    def api_base_path(self) -> str:
        """API base path for Airflow 2.x."""
        return "/api/v1"

    # ------------------------------------------------------------------ #
    #  DAGs                                                                #
    # ------------------------------------------------------------------ #

    def list_dags(
        self,
        limit: int = 100,
        offset: int = 0,
        dag_id_pattern: str | None = None,
        only_active: bool | None = None,
        paused: bool | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List all DAGs.

        Args:
            limit: Max DAGs to return (default 100)
            offset: Pagination offset
            dag_id_pattern: Filter DAGs whose dag_id contains this pattern
            only_active: If True, only return active (seen by scheduler) DAGs
            paused: If True/False, filter by paused state
            tags: Filter by tag names
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if dag_id_pattern:
            params["dag_id_pattern"] = dag_id_pattern
        if only_active is not None:
            params["only_active"] = only_active
        if paused is not None:
            params["paused"] = paused
        if tags:
            params["tags"] = ",".join(tags)
        return self._call("dags", params=params, **kwargs)

    def get_dag(self, dag_id: str) -> dict[str, Any]:
        """Get basic information about a DAG (from DAGModel, database only)."""
        return self._call(f"dags/{dag_id}")

    def get_dag_details(self, dag_id: str) -> dict[str, Any]:
        """Get detailed representation of a DAG (parsed, includes params, timezone, etc.).

        Use this when you need full DAG metadata; it is more expensive than get_dag.
        """
        return self._call(f"dags/{dag_id}/details")

    def get_dag_source(self, dag_id: str) -> dict[str, Any]:
        """Get source code of a DAG.

        Airflow 2 exposes source via /dagSources/{file_token}.
        We obtain the file_token from get_dag first.
        """
        dag_data = self.get_dag(dag_id)
        file_token = dag_data.get("file_token")
        if not file_token:
            return {"error": "DAG has no file_token", "dag_id": dag_id}
        return self._call(f"dagSources/{file_token}")

    def reparse_dag_file(self, dag_id: str) -> dict[str, Any]:
        """Request re-parsing of the DAG file.

        Triggers the scheduler to re-read the file. Returns 201 on success.
        Requires Airflow 2.x with the dag parsing endpoint enabled.
        """
        dag_data = self.get_dag(dag_id)
        file_token = dag_data.get("file_token")
        if not file_token:
            return {"error": "DAG has no file_token", "dag_id": dag_id}
        result = self.raw_request("PUT", f"parseDagFile/{file_token}", raw_endpoint=False)
        if result["status_code"] == 201:
            return {"status": "reparse_requested", "dag_id": dag_id}
        return {"error": f"HTTP {result['status_code']}", "body": result.get("body", "")}

    def pause_dag(self, dag_id: str) -> dict[str, Any]:
        """Pause a DAG to prevent new runs from being scheduled."""
        return self._patch(f"dags/{dag_id}", json_data={"is_paused": True})

    def unpause_dag(self, dag_id: str) -> dict[str, Any]:
        """Unpause a DAG to allow new runs to be scheduled."""
        return self._patch(f"dags/{dag_id}", json_data={"is_paused": False})

    def delete_dag(self, dag_id: str) -> dict[str, Any]:
        """Delete a DAG and all its metadata (runs, task instances). Logs are kept.

        *Available since Airflow 2.2.0*
        """
        return self._delete(f"dags/{dag_id}")

    def get_dag_stats(self, dag_ids: list[str] | None = None) -> dict[str, Any]:
        """Get DAG run statistics grouped by state.

        Airflow 2.x requires the dag_ids query parameter (comma-separated).
        If dag_ids is None, all DAGs are fetched first.
        """
        if dag_ids is None:
            dags_response = self.list_dags(limit=1000)
            dag_ids = [dag["dag_id"] for dag in dags_response.get("dags", [])]
            if not dag_ids:
                return {"dags": [], "total_entries": 0}
        return self._call("dagStats", params={"dag_ids": ",".join(dag_ids)})

    def list_dag_warnings(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List DAG warnings (e.g. deprecation warnings found during parsing)."""
        return self._call("dagWarnings", params={"limit": limit, "offset": offset})

    def list_import_errors(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List import errors from DAG files."""
        return self._call("importErrors", params={"limit": limit, "offset": offset})

    def list_tasks(self, dag_id: str) -> dict[str, Any]:
        """List all tasks in a DAG."""
        return self._call(f"dags/{dag_id}/tasks")

    def get_task(self, dag_id: str, task_id: str) -> dict[str, Any]:
        """Get simplified representation of a specific task."""
        return self._call(f"dags/{dag_id}/tasks/{task_id}")

    # ------------------------------------------------------------------ #
    #  DAG Runs                                                            #
    # ------------------------------------------------------------------ #

    def list_dag_runs(
        self,
        dag_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
        state: str | None = None,
        execution_date_gte: str | None = None,
        execution_date_lte: str | None = None,
        start_date_gte: str | None = None,
        start_date_lte: str | None = None,
        end_date_gte: str | None = None,
        end_date_lte: str | None = None,
        updated_at_gte: str | None = None,
        updated_at_lte: str | None = None,
        order_by: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List DAG runs.

        Use dag_id='~' to list runs across all DAGs.

        Args:
            dag_id: DAG ID, or None/'~' to list all
            limit: Max runs to return
            offset: Pagination offset
            state: Filter by state (running, success, failed, queued, etc.)
            execution_date_gte/lte: Filter by logical/execution date range (ISO 8601)
            start_date_gte/lte: Filter by start date range
            end_date_gte/lte: Filter by end date range
            updated_at_gte/lte: Filter by last update range (*New in 2.6.0*)
            order_by: Sort field (prefix with '-' for descending)
        """
        dag_id_param = dag_id if dag_id else "~"
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if state:
            params["state"] = state
        if execution_date_gte:
            params["execution_date_gte"] = execution_date_gte
        if execution_date_lte:
            params["execution_date_lte"] = execution_date_lte
        if start_date_gte:
            params["start_date_gte"] = start_date_gte
        if start_date_lte:
            params["start_date_lte"] = start_date_lte
        if end_date_gte:
            params["end_date_gte"] = end_date_gte
        if end_date_lte:
            params["end_date_lte"] = end_date_lte
        if updated_at_gte:
            params["updated_at_gte"] = updated_at_gte
        if updated_at_lte:
            params["updated_at_lte"] = updated_at_lte
        if order_by:
            params["order_by"] = order_by
        return self._call(f"dags/{dag_id_param}/dagRuns", params=params, **kwargs)

    def get_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Get details of a specific DAG run."""
        return self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}")

    def trigger_dag_run(
        self,
        dag_id: str,
        logical_date: str | None = None,
        conf: dict[str, Any] | None = None,
        dag_run_id: str | None = None,
        data_interval_start: str | None = None,
        data_interval_end: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a new DAG run.

        In Airflow 2.2+, both ``logical_date`` and the legacy ``execution_date``
        field are accepted by the API.  We send ``logical_date`` (and its alias
        ``execution_date`` for maximum backward compatibility with 2.0/2.1).

        Args:
            dag_id: The ID of the DAG to trigger
            logical_date: Optional ISO-8601 datetime for the run's logical date.
                          Sent as both logical_date (2.2+) and execution_date (2.0+).
            conf: Optional configuration dict passed to the DAG run
            dag_run_id: Optional custom run ID; auto-generated if not provided
            data_interval_start: Optional data interval start (ISO-8601)
            data_interval_end: Optional data interval end (ISO-8601)
            note: Optional human note attached to the run (*New in 2.5.0*)

        Returns:
            Details of the triggered DAG run
        """
        json_body: dict[str, Any] = {}
        if logical_date:
            # Send both for broadest compatibility (2.0 through 2.11)
            json_body["logical_date"] = logical_date
            json_body["execution_date"] = logical_date
        if conf:
            json_body["conf"] = conf
        if dag_run_id:
            json_body["dag_run_id"] = dag_run_id
        if data_interval_start:
            json_body["data_interval_start"] = data_interval_start
        if data_interval_end:
            json_body["data_interval_end"] = data_interval_end
        if note:
            json_body["note"] = note
        return self._post(f"dags/{dag_id}/dagRuns", json_data=json_body)

    def update_dag_run_state(
        self, dag_id: str, dag_run_id: str, state: str
    ) -> dict[str, Any]:
        """Update the state of a DAG run.

        Args:
            dag_id: The DAG ID
            dag_run_id: The DAG run ID
            state: New state – one of 'success', 'failed', 'queued'

        *New in Airflow 2.2.0*
        """
        allowed = {"success", "failed", "queued"}
        if state not in allowed:
            return {"error": f"state must be one of {allowed}, got '{state}'"}
        return self._patch(f"dags/{dag_id}/dagRuns/{dag_run_id}", json_data={"state": state})

    def delete_dag_run(self, dag_id: str, dag_run_id: str) -> dict[str, Any]:
        """Delete a specific DAG run."""
        return self._delete(f"dags/{dag_id}/dagRuns/{dag_run_id}")

    def clear_dag_run(
        self,
        dag_id: str,
        dag_run_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Clear all task instances in a DAG run to allow re-execution.

        Args:
            dag_id: The DAG ID
            dag_run_id: The DAG run ID
            dry_run: If True, list what would be cleared without clearing

        *New in Airflow 2.4.0*
        """
        return self._post(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/clear",
            json_data={"dry_run": dry_run},
        )

    def set_dag_run_note(self, dag_id: str, dag_run_id: str, note: str) -> dict[str, Any]:
        """Set or update the human note on a DAG run.

        *New in Airflow 2.5.0*
        """
        return self._patch(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/setNote",
            json_data={"note": note},
        )

    def get_dag_run_upstream_asset_events(
        self,
        dag_id: str,
        dag_run_id: str,
    ) -> dict[str, Any]:
        """Get upstream dataset events that triggered a dataset-triggered DAG run.

        Normalises 'dataset_events' -> 'asset_events' for consistency with v3 adapter.

        *New in Airflow 2.4.0*
        """
        try:
            data = self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}/upstreamDatasetEvents")
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
                alternative="Requires Airflow 2.4+ and a dataset-triggered run",
            )

    # ------------------------------------------------------------------ #
    #  Task Instances                                                      #
    # ------------------------------------------------------------------ #

    def get_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
        """Get details of a task instance."""
        return self._call(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")

    def get_task_instances(
        self,
        dag_id: str,
        dag_run_id: str,
        limit: int = 100,
        offset: int = 0,
        state: str | None = None,
    ) -> dict[str, Any]:
        """List all task instances for a DAG run.

        Use dag_id='~' and dag_run_id='~' to query across all DAGs and runs.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if state:
            params["state"] = state
        return self._call(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
            params=params,
        )

    def patch_task_instance(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        new_state: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Update the state of a single task instance.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            task_id: Task ID
            new_state: New state (e.g. 'success', 'failed', 'skipped', 'up_for_retry')
            dry_run: If True, simulate without actually changing (default True)

        *New in Airflow 2.5.0*
        """
        return self._patch(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}",
            json_data={"dry_run": dry_run, "new_state": new_state},
        )

    def set_task_instance_note(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        note: str,
        map_index: int | None = None,
    ) -> dict[str, Any]:
        """Set a human note on a task instance.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            task_id: Task ID
            note: The note text
            map_index: For mapped tasks; omit for non-mapped tasks

        *New in Airflow 2.5.0*
        """
        if map_index is not None:
            endpoint = (
                f"dags/{dag_id}/dagRuns/{dag_run_id}"
                f"/taskInstances/{task_id}/{map_index}/setNote"
            )
        else:
            endpoint = (
                f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/setNote"
            )
        return self._patch(endpoint, json_data={"note": note})

    def get_task_instance_tries(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List all try-history records for a task instance.

        *New in Airflow 2.10.0*
        """
        try:
            return self._call(
                f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/tries",
                params={"limit": limit, "offset": offset},
            )
        except NotFoundError:
            return self._handle_not_found(
                "taskInstance tries",
                alternative="Task instance try history requires Airflow 2.10+",
            )

    def get_task_instance_try_details(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        task_try_number: int,
    ) -> dict[str, Any]:
        """Get details for a specific task instance try.

        *New in Airflow 2.10.0*
        """
        try:
            return self._call(
                f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/tries/{task_try_number}",
            )
        except NotFoundError:
            return self._handle_not_found(
                "taskInstance try details",
                alternative="Task instance try details require Airflow 2.10+",
            )

    def get_task_instance_dependencies(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        map_index: int | None = None,
    ) -> dict[str, Any]:
        """Get dependencies that are blocking a task instance from being scheduled.

        Args:
            dag_id: DAG ID
            dag_run_id: DAG run ID
            task_id: Task ID
            map_index: For mapped tasks; omit for non-mapped tasks

        *New in Airflow 2.10.0*
        """
        try:
            if map_index is not None:
                endpoint = (
                    f"dags/{dag_id}/dagRuns/{dag_run_id}"
                    f"/taskInstances/{task_id}/{map_index}/dependencies"
                )
            else:
                endpoint = (
                    f"dags/{dag_id}/dagRuns/{dag_run_id}"
                    f"/taskInstances/{task_id}/dependencies"
                )
            return self._call(endpoint)
        except NotFoundError:
            return self._handle_not_found(
                "taskInstance dependencies",
                alternative="Task instance dependency info requires Airflow 2.10+",
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
            map_index: Map index for mapped tasks (-1 means not set)
            full_content: Whether to return full log content
        """
        endpoint = (
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
        )
        params: dict[str, Any] = {"full_content": full_content}
        if map_index != -1:
            params["map_index"] = map_index
        try:
            return self._call(endpoint, params=params)
        except NotFoundError:
            return self._handle_not_found(
                "task logs",
                alternative="Check if the task instance exists and has been executed",
            )

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

        Calls POST /dags/{dag_id}/clearTaskInstances.
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
                alternative="clearTaskInstances requires Airflow 2.1+",
            )

    # ------------------------------------------------------------------ #
    #  XCom                                                                #
    # ------------------------------------------------------------------ #

    def get_xcom_entries(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        limit: int = 100,
        offset: int = 0,
        map_index: int | None = None,
        xcom_key: str | None = None,
    ) -> dict[str, Any]:
        """List XCom entries for a task instance.

        Use '~' for dag_id, dag_run_id, and task_id to list across all.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if map_index is not None:
            params["map_index"] = map_index
        if xcom_key:
            params["xcom_key"] = xcom_key
        return self._call(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries",
            params=params,
        )

    def get_xcom_entry(
        self,
        dag_id: str,
        dag_run_id: str,
        task_id: str,
        xcom_key: str,
        map_index: int | None = None,
        deserialize: bool = False,
        stringify: bool = True,
    ) -> dict[str, Any]:
        """Get a single XCom entry value.

        Args:
            deserialize: Call full deserialize_value (expensive) instead of orm_deserialize_value
            stringify: Return value as string (default True); set False for raw type (*New in 2.10.0*)
        """
        params: dict[str, Any] = {"deserialize": deserialize, "stringify": stringify}
        if map_index is not None:
            params["map_index"] = map_index
        return self._call(
            f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/xcomEntries/{xcom_key}",
            params=params,
        )

    # ------------------------------------------------------------------ #
    #  Assets / Datasets                                                   #
    # ------------------------------------------------------------------ #

    def list_assets(
        self,
        limit: int = 100,
        offset: int = 0,
        uri_pattern: str | None = None,
        dag_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List datasets (called 'assets' in Airflow 3).

        Normalises 'datasets' -> 'assets' and 'consuming_dags' -> 'scheduled_dags'
        for consistency with the v3 adapter.
        """
        try:
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if uri_pattern:
                params["uri_pattern"] = uri_pattern
            if dag_ids:
                params["dag_ids"] = ",".join(dag_ids)
            data = self._call("datasets", params=params, **kwargs)
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

    def get_asset(self, uri: str) -> dict[str, Any]:
        """Get a specific dataset/asset by URI."""
        try:
            return self._call(f"datasets/{uri}")
        except NotFoundError:
            return self._handle_not_found("dataset", alternative="Check the URI is correct")

    def list_asset_events(
        self,
        limit: int = 100,
        offset: int = 0,
        source_dag_id: str | None = None,
        source_run_id: str | None = None,
        source_task_id: str | None = None,
    ) -> dict[str, Any]:
        """List dataset events.

        Normalises 'dataset_events' -> 'asset_events' for v3 consistency.
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

    def create_dataset_event(self, dataset_uri: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Manually create a dataset event to trigger downstream DAGs.

        Args:
            dataset_uri: The URI of the dataset to signal
            extra: Optional extra JSON data attached to the event
        """
        json_body: dict[str, Any] = {"dataset_uri": dataset_uri}
        if extra:
            json_body["extra"] = extra
        return self._post("datasets/events", json_data=json_body)

    # ------------------------------------------------------------------ #
    #  Variables                                                           #
    # ------------------------------------------------------------------ #

    def list_variables(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow variables (values are NOT returned in list; fetch individually)."""
        return self._call("variables", params={"limit": limit, "offset": offset})

    def get_variable(self, variable_key: str) -> dict[str, Any]:
        """Get a specific variable by key (includes value)."""
        return self._call(f"variables/{variable_key}")

    def set_variable(self, key: str, value: str, description: str | None = None) -> dict[str, Any]:
        """Create or overwrite an Airflow variable.

        To update an existing variable use patch_variable.
        This method POSTs and will fail with 409 if the key already exists.
        """
        json_body: dict[str, Any] = {"key": key, "value": value}
        if description is not None:
            json_body["description"] = description
        return self._post("variables", json_data=json_body)

    def patch_variable(
        self, key: str, value: str, description: str | None = None
    ) -> dict[str, Any]:
        """Update an existing Airflow variable."""
        json_body: dict[str, Any] = {"key": key, "value": value}
        if description is not None:
            json_body["description"] = description
        return self._patch(f"variables/{key}", json_data=json_body)

    def delete_variable(self, variable_key: str) -> dict[str, Any]:
        """Delete an Airflow variable."""
        return self._delete(f"variables/{variable_key}")

    # ------------------------------------------------------------------ #
    #  Connections                                                         #
    # ------------------------------------------------------------------ #

    def list_connections(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow connections (passwords are filtered out)."""
        data = self._call("connections", params={"limit": limit, "offset": offset})
        return self._filter_passwords(data)

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        """Get a connection by ID (password field is write-only; not returned)."""
        data = self._call(f"connections/{connection_id}")
        return self._filter_passwords(data)

    # ------------------------------------------------------------------ #
    #  Pools                                                               #
    # ------------------------------------------------------------------ #

    def list_pools(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List Airflow pools."""
        return self._call("pools", params={"limit": limit, "offset": offset})

    def get_pool(self, pool_name: str) -> dict[str, Any]:
        """Get details of a specific pool."""
        return self._call(f"pools/{pool_name}")

    def create_pool(
        self,
        name: str,
        slots: int,
        description: str | None = None,
        include_deferred: bool = False,
    ) -> dict[str, Any]:
        """Create a new Airflow pool.

        Args:
            name: Pool name
            slots: Max number of running slots
            description: Optional description (*New in 2.3.0*)
            include_deferred: Count deferred tasks against open slots (*New in 2.7.0*)
        """
        json_body: dict[str, Any] = {"name": name, "slots": slots, "include_deferred": include_deferred}
        if description is not None:
            json_body["description"] = description
        return self._post("pools", json_data=json_body)

    def patch_pool(
        self,
        pool_name: str,
        slots: int | None = None,
        description: str | None = None,
        include_deferred: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing pool."""
        json_body: dict[str, Any] = {}
        if slots is not None:
            json_body["slots"] = slots
        if description is not None:
            json_body["description"] = description
        if include_deferred is not None:
            json_body["include_deferred"] = include_deferred
        return self._patch(f"pools/{pool_name}", json_data=json_body)

    def delete_pool(self, pool_name: str) -> dict[str, Any]:
        """Delete a pool."""
        return self._delete(f"pools/{pool_name}")

    # ------------------------------------------------------------------ #
    #  Monitoring / Meta                                                   #
    # ------------------------------------------------------------------ #

    def get_health(self) -> dict[str, Any]:
        """Get instance health status (metadatabase, scheduler, triggerer, dag_processor)."""
        return self._call("health")

    def get_version(self) -> dict[str, Any]:
        """Get Airflow version info."""
        return self._call("version")

    def get_config(self, section: str | None = None) -> dict[str, Any]:
        """Get Airflow configuration.

        Requires ``expose_config = True`` in [webserver] section of airflow.cfg.
        """
        try:
            params: dict[str, Any] = {}
            if section:
                params["section"] = section
            return self._call("config", params=params if params else None)
        except Exception as e:
            return {
                "error": str(e),
                "note": "Config endpoint requires expose_config=True in airflow.cfg",
            }

    def list_plugins(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """List installed Airflow plugins (*New in 2.1.0*)."""
        return self._call("plugins", params={"limit": limit, "offset": offset})

    def list_providers(self) -> dict[str, Any]:
        """List installed Airflow provider packages (*New in 2.1.0*)."""
        return self._call("providers")

    def get_openapi_spec(self) -> dict[str, Any]:
        """Get the OpenAPI specification for the Airflow 2.x API.

        Airflow 2.x serves the spec as YAML at /api/v1/openapi.yaml.
        """
        result = self.raw_request("GET", "openapi.yaml", raw_endpoint=False)
        if result["status_code"] >= 400:
            raise Exception(f"HTTP {result['status_code']}: {result.get('body', 'Unknown error')}")
        body = result["body"]
        if isinstance(body, str):
            return yaml.safe_load(body)
        return body

    # ------------------------------------------------------------------ #
    #  Event Logs                                                          #
    # ------------------------------------------------------------------ #

    def get_event_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        dag_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        event: str | None = None,
        owner: str | None = None,
        included_events: str | None = None,
        excluded_events: str | None = None,
    ) -> dict[str, Any]:
        """List event log entries from the audit log.

        Args:
            included_events: Comma-separated event names to include (*New in 2.9.0*)
            excluded_events: Comma-separated event names to exclude (*New in 2.9.0*)
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if dag_id:
            params["dag_id"] = dag_id
        if task_id:
            params["task_id"] = task_id
        if run_id:
            params["run_id"] = run_id
        if event:
            params["event"] = event
        if owner:
            params["owner"] = owner
        if included_events:
            params["included_events"] = included_events
        if excluded_events:
            params["excluded_events"] = excluded_events
        return self._call("eventLogs", params=params)

    def get_event_log(self, event_log_id: int) -> dict[str, Any]:
        """Get a single event log entry by ID."""
        return self._call(f"eventLogs/{event_log_id}")
