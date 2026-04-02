# Migration Checklist

After running Ruff's AIR rules, use this manual search checklist to find remaining issues.

## 1. Direct metadata DB access

**Search for:**
- `provide_session`
- `create_session`
- `@provide_session`
- `Session(`
- `engine`
- `with Session()`
- `engine.connect(`
- `Session(bind=engine)`
- `from airflow.settings import Session`
- `from airflow.settings import engine`
- `from sqlalchemy.orm.session import Session`

**Fix:** Refactor to use Airflow Python client or REST API

---

## 2. Legacy imports

**Search for:**
- `from airflow.contrib`
- `from airflow.operators.`
- `from airflow.hooks.`

**Fix:** Map to provider imports (see [migration-patterns.md](migration-patterns.md))

---

## 3. Removed/renamed DAG arguments

**Search for:**
- `schedule_interval=`
- `timetable=`
- `days_ago(`
- `fail_stop=`
- `concurrency=` (on DAG constructor)
- `sla=`
- `sla_miss_callback`
- `task_concurrency=`

**Fix:**
- `schedule_interval` and `timetable` → use `schedule=`
- `days_ago` → use `pendulum.today("UTC").add(days=-N)`
- `fail_stop` → renamed to `fail_fast`
- `concurrency` (DAG) → renamed to `max_active_tasks`
- `sla` and `sla_miss_callback` → removed; use **Astro Alerts** or OSS **Deadline Alerts** (Airflow 3.1+ experimental)
- `task_concurrency` → renamed to `max_active_tis_per_dag`

### Additional parameter removals

**Search for:**
- `execution_date` on `TriggerDagRunOperator` → removed; use `logical_date` or `run_id`

---

## 4. Deprecated context keys

**Search for:**
- `execution_date`
- `prev_ds`
- `next_ds`
- `yesterday_ds`
- `tomorrow_ds`
- `templates_dict`

**Fix:**
- `execution_date` → use `context["dag_run"].logical_date`
- `tomorrow_ds` / `yesterday_ds` → use `ds` with date math: `macros.ds_add(ds, 1)` / `macros.ds_add(ds, -1)`
- `prev_ds` / `next_ds` → use `prev_start_date_success` or timetable API
- `templates_dict` → use `params` via `context["params"]`

---

## 5. XCom pickling

**Search for:**
- `ENABLE_XCOM_PICKLING`
- `.xcom_pull(` without `task_ids=`

**Fix:** Use JSON-serializable data or custom backend

---

## 6. Datasets to Assets

**Search for:**
- `airflow.datasets`
- `triggering_dataset_events`
- `DatasetOrTimeSchedule`
- `on_dataset_created`
- `on_dataset_changed`
- `outlet_events["`
- `inlet_events["`

**Fix:** Switch to `airflow.sdk.Asset`, `AssetOrTimeSchedule`, `on_asset_created`/`on_asset_changed`. Use `Asset(name=...)` objects as keys in `outlet_events`/`inlet_events` (not strings)

---

## 7. Removed operators

**Search for:**
- `SubDagOperator`
- `SimpleHttpOperator`
- `DagParam`
- `DummyOperator`

**Fix:** Use TaskGroups, HttpOperator, Param, EmptyOperator

---

## 8. Email changes

**Search for:**
- `airflow.operators.email.EmailOperator`
- `airflow.utils.email`
- `email=` (task parameter for email on failure/retry)

**Fix:** Use SMTP provider (`apache-airflow-providers-smtp`). Replace legacy email behavior with SMTP-provider callbacks such as `send_smtp_notification(...)` or `SmtpNotifier`.

---

## 9. REST API v1

**Search for:**
- `/api/v1`
- `auth=(`
- `execution_date` (in API params)
- `dataset_triggered` or `dataset_expression` (in API responses/requests)
- `schedule_interval` (in API responses)
- `/api/v1/roles`, `/api/v1/permissions`, `/api/v1/users`

**Fix:** Update to `/api/v2` with Bearer tokens. Replace `execution_date` params with `logical_date`. Dataset endpoints now under `asset` resources.

**Endpoint renames:**

| Old Endpoint | New Endpoint |
|-------------|-------------|
| `/api/v1/datasets` | `/api/v2/assets` |
| `/api/v1/datasets/{uri}` | `/api/v2/assets/{uri}` |
| `/api/v1/datasets/events` | `/api/v2/assets/events` |
| `/api/v1/roles` | `/auth/fab/v1/roles` |
| `/api/v1/permissions` | `/auth/fab/v1/permissions` |
| `/api/v1/users` | `/auth/fab/v1/users` |

**Field renames in API responses:**

| Old Field | New Field |
|-----------|-----------|
| `dataset_triggered` | `asset_triggered` |
| `dataset_expression` | `asset_expression` |
| `concurrency` (in DAGDetail) | `max_active_tasks` |
| `schedule_interval` | `timetable_summary` |

---

## 10. File paths and shared utility imports

**Search for:**
- `open("include/`
- `open("data/`
- `template_searchpath=`
- relative paths
- `import common` or `from common` (bare imports from `dags/common/` or similar)
- `import utils` or `from utils` (bare imports from `dags/utils/` or similar)
- `sys.path.append` or `sys.path.insert` (custom path manipulation)

**Fix:**
- Use `__file__` or `AIRFLOW_HOME` anchoring for file paths
- Note: triggers cannot be in DAG bundle; must be elsewhere on `sys.path`
- **Shared utility imports**: Bare imports like `import common` no longer work. Use fully qualified imports: `import dags.common` or `from dags.common.utils import helper_function`

---

## 11. FAB-based plugins

**Search for:**
- `appbuilder_views`
- `appbuilder_menu_items`
- `flask_blueprints`
- `AirflowPlugin`

**Fix:** Flask-AppBuilder removed from core. FAB plugins need manual migration to new system (React apps, FastAPI, listeners). Do not auto-migrate; recommend separate PR

---

## 12. Configuration file (`airflow.cfg`)

**Search for:**
- `AIRFLOW__CORE__SQL_ALCHEMY` (database settings moved to `[database]`)
- `AIRFLOW__CORE__REMOTE_LOGGING` or `AIRFLOW__CORE__BASE_LOG_FOLDER` (logging settings moved to `[logging]`)
- `AIRFLOW__CORE__DAG_CONCURRENCY` (renamed to `max_active_tasks_per_dag`)
- `AIRFLOW__SCHEDULER__DEACTIVATE_STALE_DAGS_INTERVAL` (renamed to `parsing_cleanup_interval`)
- `AIRFLOW__WEBSERVER__BASE_URL` (moved to `[api]base_url`)
- `AIRFLOW__KUBERNETES__` (section replaced by `[kubernetes_executor]`)

**Fix:** Update environment variables and config references to new section/key names. See [config-changes.md](config-changes.md) for full mapping.

---

## 13. `airflow_local_settings.py`: rename `policy` → `task_policy`

---

## 14. Callback and behavior changes

**Search for:**
- `on_success_callback`
- `@teardown`
- `templates_dict`
- `expanded_ti_count`
- `external_trigger`
- `test_mode`
- `trigger_rule="dummy"` or `TriggerRule.DUMMY`
- `trigger_rule="none_failed_or_skipped"` or `NONE_FAILED_OR_SKIPPED`

**Fix:**
- `on_success_callback` no longer runs on skip; use `on_skipped_callback` if needed
- `@teardown` with trigger rule `always` not allowed; teardowns now execute even if DAG run terminated early
- `templates_dict` removed → use `params` via `context["params"]`
- `expanded_ti_count` removed → use REST API "Get Mapped Task Instances"
- `dag_run.external_trigger` removed → infer from `dag_run.run_type`
- `test_mode` removed; avoid relying on this flag
- `dummy` trigger rule removed → use `always` (or `TriggerRule.ALWAYS`)
- `none_failed_or_skipped` trigger rule removed → use `none_failed_min_one_success` (or `TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS`)
