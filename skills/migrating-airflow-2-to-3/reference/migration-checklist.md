# Migration Checklist

After running Ruff's AIR rules, use this manual search checklist to find remaining issues.

## 1. Direct metadata DB access

**Search for:**
- `provide_session`
- `create_session`
- `Session(`
- `engine`

**Fix:** Refactor to use Airflow Python client or REST API

---

## 2. Legacy imports

**Search for:**
- `from airflow.contrib`
- `from airflow.operators.`
- `from airflow.hooks.`

**Fix:** Map to provider imports (see [migration-patterns.md](migration-patterns.md))

---

## 3. Removed DAG arguments

**Search for:**
- `schedule_interval=`
- `timetable=`
- `days_ago(`
- `fail_stop=`

**Fix:** Use `schedule=` and `pendulum`

---

## 4. Deprecated context keys

**Search for:**
- `execution_date`
- `prev_ds`
- `next_ds`
- `yesterday_ds`
- `tomorrow_ds`

**Fix:** Use `data_interval_start/end` and `dag_run.logical_date`

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

**Fix:** Switch to `airflow.sdk.Asset`

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

**Fix:** Use SMTP provider

---

## 9. REST API v1

**Search for:**
- `/api/v1`

**Fix:** Update to `/api/v2` with Bearer tokens

---

## 10. File paths

**Search for:**
- `open("include/...)`
- relative paths

**Fix:** Use `__file__` or `AIRFLOW_HOME` anchoring
