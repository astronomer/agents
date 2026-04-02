# Removed & Inaccessible Model Methods

Airflow 3 enforces a strict boundary between the **public SDK** (`airflow.sdk`) used in DAG code and **internal ORM models** (`airflow.models.*`) used by the scheduler and API. Task code runs in isolated subprocesses with no database access (AIP-72).

If your DAG code calls any of the methods below, the fix is not just a rename — you need to replace direct model access with SDK patterns or the Airflow Client API.

---

## DAG

In Airflow 3, use `from airflow.sdk import DAG`. The SDK DAG is a definition object — it does not expose runtime state methods.

| Removed / Inaccessible | Migration Path |
|------------------------|----------------|
| `DAG.concurrency` | Use `max_active_tasks` parameter in DAG constructor |
| `DAG.date_range()` | Remove — use `pendulum` for date range logic |
| `DAG.following_schedule()` / `DAG.previous_schedule()` | Remove — use timetable API if needed at parse time |
| `DAG.get_num_active_runs()` | Use Airflow REST API `/api/v2/dags/{dag_id}` |
| `DAG.set_dag_runs_state()` | Use Airflow REST API to update DAG run state |
| `DAG.full_filepath` / `DAG.filepath` | Use `os.path.dirname(__file__)` for relative paths |
| `DAG.is_paused` / `DAG.get_is_paused()` | Use Airflow REST API `/api/v2/dags/{dag_id}` |
| `DAG.latest_execution_date` | Use Airflow REST API `/api/v2/dags/{dag_id}/dagRuns` |
| `DAG.bulk_sync_to_db()` / `DAG.normalize_schedule()` / `DAG.is_fixed_time_schedule()` / `DAG.next_dagrun_after_date()` / `DAG.get_run_dates()` / `DAG.concurrency_reached()` / `DAG.normalized_schedule_interval` | Internal scheduler methods — no user-facing replacement |

---

## TaskInstance

In task code, access task instance state through the `context` dict or SDK IPC methods. Direct ORM queries on TaskInstance are blocked at runtime.

| Removed / Inaccessible | Migration Path |
|------------------------|----------------|
| `TaskInstance._try_number` / `prev_attempted_tries` / `next_try_number` | Use `context["ti"].try_number` |
| `TaskInstance.previous_ti` / `previous_ti_success` | Use `context["ti"].get_previous_ti()` (SDK IPC method) |
| `TaskInstance.previous_start_date_success` | Use `context["ti"].get_previous_start_date()` (SDK IPC method) |
| `TaskInstance.operator` | Use `context["ti"].task.operator_name` |
| `session.query(TaskInstance).filter(...)` | Use Airflow REST API or `PostgresHook` with `airflow_db` connection |

---

## DagRun

Access DagRun properties through the task context. Direct ORM queries on DagRun are blocked at runtime.

| Removed / Inaccessible | Migration Path |
|------------------------|----------------|
| `DagRun.execution_date` | `context["dag_run"].logical_date` or `context["run_id"]` |
| `DagRun.get_run()` | Use Airflow REST API `/api/v2/dags/{dag_id}/dagRuns` |
| `DagRun.is_backfill` | No direct replacement |
| `DagRun.get_task_instances(state=...)` | Use `context["ti"].get_task_states(dag_id, task_ids, run_ids)` (SDK IPC) |
| `session.query(DagRun).filter(...)` | Use Airflow REST API or `PostgresHook` with `airflow_db` connection |

---

## Connection

Connection resolution happens through hooks. Do not query Connection objects directly.

| Removed / Inaccessible | Migration Path |
|------------------------|----------------|
| `Connection.parse_netloc_to_hostname()` | Remove — pass connection IDs to hooks instead |
| `Connection.parse_from_uri()` | Remove — use `Connection(conn_id=..., uri=...)` constructor |
| `Connection.log_info()` / `Connection.debug_info()` | Remove — use standard logging |
| `session.query(Connection).filter(...)` | Use `BaseHook.get_connection(conn_id)` or Airflow REST API |

---

## Dataset → Asset Renames

| Removed | Replacement |
|---------|-------------|
| `airflow.datasets.DatasetEvent` | `airflow.sdk.AssetEvent` |
| `airflow.datasets.manager.DatasetAliasEvent` | `airflow.sdk.AssetAliasEvent` |
