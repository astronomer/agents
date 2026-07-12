# Airflow 2.11.0 Compatibility Notes

This document describes changes made to the `astro-airflow-mcp` adapter layer
to ensure full compatibility with the **Airflow 2.11.0** REST API
(`/api/v1`, OpenAPI spec at `airflow/api_connexion/openapi/v1.yaml`).

## Branch

`feat/airflow-2.11-compat`

## Summary of Changes to `airflow_v2.py`

### New methods added

| Method | Endpoint | Airflow version |
|---|---|---|
| `get_dag_details` | `GET /dags/{dag_id}/details` | 2.x |
| `reparse_dag_file` | `PUT /parseDagFile/{file_token}` | 2.x |
| `delete_dag` | `DELETE /dags/{dag_id}` | 2.2+ |
| `update_dag_run_state` | `PATCH /dags/{dag_id}/dagRuns/{dag_run_id}` | 2.2+ |
| `set_dag_run_note` | `PATCH …/dagRuns/{id}/setNote` | 2.5+ |
| `patch_task_instance` | `PATCH …/taskInstances/{task_id}` | 2.5+ |
| `set_task_instance_note` | `PATCH …/taskInstances/{id}/setNote` (mapped+unmapped) | 2.5+ |
| `get_task_instance_tries` | `GET …/taskInstances/{task_id}/tries` | 2.10+ |
| `get_task_instance_try_details` | `GET …/taskInstances/{task_id}/tries/{n}` | 2.10+ |
| `get_task_instance_dependencies` | `GET …/taskInstances/{task_id}/dependencies` (mapped+unmapped) | 2.10+ |
| `get_xcom_entries` | `GET …/xcomEntries` | 2.x |
| `get_xcom_entry` | `GET …/xcomEntries/{key}` | 2.x |
| `get_asset` | `GET /datasets/{uri}` | 2.4+ |
| `create_dataset_event` | `POST /datasets/events` | 2.4+ |
| `set_variable` | `POST /variables` | 2.x |
| `patch_variable` | `PATCH /variables/{key}` | 2.x |
| `delete_variable` | `DELETE /variables/{key}` | 2.x |
| `get_connection` | `GET /connections/{connection_id}` | 2.x |
| `create_pool` | `POST /pools` | 2.x |
| `patch_pool` | `PATCH /pools/{pool_name}` | 2.x |
| `delete_pool` | `DELETE /pools/{pool_name}` | 2.x |
| `get_health` | `GET /health` | 2.x |
| `get_event_logs` | `GET /eventLogs` | 2.x |
| `get_event_log` | `GET /eventLogs/{id}` | 2.x |

### Existing method improvements

- **`trigger_dag_run`**: Now sends both `logical_date` (2.2+) and `execution_date`
  (backward compat for 2.0/2.1). Added `dag_run_id`, `data_interval_start`,
  `data_interval_end`, and `note` parameters.
- **`list_dags`**: Added `dag_id_pattern`, `only_active`, `paused`, and `tags` filters.
- **`list_dag_runs`**: Exposed all filter params from the OpenAPI spec
  (`state`, date range filters, `order_by`).
- **`get_task_instances`**: Added `state` filter; documents `~` wildcard usage.
- **`list_assets`**: Added `uri_pattern` and `dag_ids` filters (2.9+).
- **`get_config`**: Added optional `section` parameter.
- **`get_task_logs`**: Documented `map_index = -1` semantics.

### API path reference (Airflow 2.x)

All endpoints are under `/api/v1`. The version detection probe in
`adapters/__init__.py` already targets `/api/v1/version`, which is correct.

### Key differences from Airflow 3 (`airflow_v3.py`)

| Feature | Airflow 2.x (`/api/v1`) | Airflow 3 (`/api/v2`) |
|---|---|---|
| Datasets | `datasets` | `assets` |
| Consuming DAGs field | `consuming_dags` | `scheduled_dags` |
| Auth (roles/users) | `/roles`, `/users` (deprecated, FAB forwarded) | `/auth/fab/v1` |
| Backfill REST endpoint | Not in stable API | Available |
| Task instance try history | `/tries` (2.10+) | `/tries` |
| `logical_date` | Supported since 2.2; `execution_date` alias kept | `logical_date` only |
