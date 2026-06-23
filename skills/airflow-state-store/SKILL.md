---
name: airflow-state-store
description: Use when the user asks about task state store, checkpointing in tasks, persisting state across retries, job IDs surviving worker crashes, watermarks, asset metadata, resumable tasks, crash-safe operators, or "what's new in Airflow 3.3". Also use proactively when reading a DAG that uses Variables or XCom for intra-task coordination state — flag the anti-pattern and recommend task_state_store or asset_state_store instead. Requires Airflow 3.3+.
---

# Airflow Task State Store (AIP-103)

Airflow 3.3 ships two key/value stores and a crash-safety mixin for operators that submit external jobs.

> **Requires Airflow 3.3+.** Check first:
> ```bash
> af config version
> ```
> If the version is below 3.3, tell the user these features are not yet available and link them to the AIP-103 tracking issue instead.

---

## Step 1 — Pick the right primitive

| I need to… | Use |
|---|---|
| Persist a cursor, offset, or job ID so a retry can resume instead of restart | `task_state_store` |
| Pass small coordination state within one task across retries (not between tasks) | `task_state_store` |
| Store a watermark or last-processed timestamp per asset, surviving across Dag runs | `asset_state_store` |
| Cache asset-level metadata (manifest hash, row count, schema version) | `asset_state_store` |
| Make an existing non deferrable operator crash-safe when it submits to an external system | `task_state_store` or `ResumableJobMixin` |

**When NOT to use these:**
- Passing data *between* tasks -> use XCom
- Large payloads (model weights, dataframes) -> use XCom with an object storage backend
- Config or secrets shared across Dags -> use Variables or Connections

---

## Step 2 — Detect anti-patterns in existing DAGs (on demand)

When the user asks to review a DAG or asks "is there a better way", scan for these patterns and flag them:

| Pattern seen in DAG | Problem | Recommend |
|---|---|---|
| `Variable.get(...)` / `Variable.set(...)` inside a `@task` body for per-run state | Variables are global and shared; no scoping to task instance or retry | `task_state_store` |
| `context["ti"].xcom_push(key="job_id", ...)` to survive retries | XCom is scoped to a Dag run, not a retry; a new ti_id is issued per retry | `task_state_store` or `ResumableJobMixin` |
| Manual `if Variable.get("job_id"): reconnect else: submit` retry-resume logic | Reimplements what `ResumableJobMixin` already provides, without the crash-safety guarantee | `ResumableJobMixin` |
| `Variable.set("last_processed_at", ...)` for watermarks | Global; any Dag or task can overwrite it; no scoping to asset | `asset_state_store` |

Show a before/after snippet when flagging. Use the canonical examples in Steps 3–5 as the "after".

---

## Step 3 — `task_state_store`: per-task coordination state

`task_state_store` is a key/value store scoped to a single task instance identity (dag_id + run_id + task_id + map_index). It survives retries — a new retry on the same task reads the same store.

```python
from airflow.sdk import dag, task
from pendulum import datetime

@dag(start_date=datetime(2025, 1, 1), schedule="@daily")
def etl_with_checkpoint():

    @task(retries=3)
    def process_records(**context):
        task_state_store = context["task_state_store"]  # injected by Airflow, no setup needed
        cursor = task_state_store.get("last_cursor", default=0)
        records = fetch_records_after(cursor)
        for record in records:
            process(record)
            cursor = record["id"]
            task_state_store.set("last_cursor", cursor)   # checkpoint after each record

    process_records()

etl_with_checkpoint()
```

**API:**
```python
from airflow.sdk import NEVER_EXPIRE

task_state_store.get(key, default=None)                        # returns a JsonValue or default
task_state_store.set(key, value)                               # uses default_retention_days
task_state_store.set(key, value, retention=timedelta(days=7))  # per-key TTL override
task_state_store.set(key, value, retention=NEVER_EXPIRE)       # never expires regardless of config
task_state_store.delete(key)                                   # no-op if key does not exist
task_state_store.clear()                                       # delete all keys for this task instance
```

**Key rules:**
- Values must be JSON-serializable (`str`, `int`, `float`, `bool`, `list`, `dict` — `None` values are rejected).
- Default expiry is controlled by `[state_store] default_retention_days` (0 = never expire).
- Use `NEVER_EXPIRE` for keys that must outlive the default retention window (e.g. a job ID for a multi-day Spark job).
- Max value size defaults to 64 KB; configurable via `[state_store] max_value_storage_bytes` (0 = no limit). For larger payloads, configure a custom `[state_store] backend` or a worker side backend configured via: `[workers] state_store_backend`.

**Mapped tasks — each index has its own namespace:**

When a task is dynamically mapped (`task.expand(...)`), each map index gets an isolated `task_state_store` scoped to its own `map_index`. Indices do not share state.

```python
@task(retries=2)
def process_partition(partition_id, **context):
    task_state_store = context["task_state_store"]
    # Scoped to THIS index only — other indices have their own copy
    cursor = task_state_store.get("cursor", default=0)
    task_state_store.set("cursor", new_cursor)

process_partition.expand(partition_id=[0, 1, 2, 3])
```

`clear()` clears only the current index. To wipe state across all map indices of a task group, use the CLI or core API.

**Before (anti-pattern):**
```python
@task
def process(**context):
    cursor = Variable.get("etl_cursor", default_var=0)
    # ... process ...
    Variable.set("etl_cursor", new_cursor)  # global, any task can overwrite
```

**After:**
```python
@task(retries=3)
def process(**context):
    task_state_store = context["task_state_store"]
    cursor = task_state_store.get("cursor", default=0)
    # ... process ...
    task_state_store.set("cursor", new_cursor)    # scoped to this task instance
```

---

## Step 4 — `asset_state_store`: per-asset metadata across Dag runs

`asset_state_store` is scoped to an asset, not a task instance. It persists across Dag runs — the same key on the same asset is readable and writable by any task that produces or consumes it.

```python
from airflow.sdk import DAG, Asset, task
from datetime import datetime, timezone

ORDERS = Asset(name="orders/daily", uri="s3://warehouse/orders/daily")

with DAG(dag_id="producer", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):

    @task(inlets=[ORDERS], outlets=[ORDERS])
    def load(asset_state_store=None):        # asset_state_store injected by Airflow — declare as a kwarg
        asset_state_store = asset_state_store[ORDERS]

        watermark = asset_state_store.get("watermark", default="2026-01-01T00:00:00+00:00")
        records = fetch_records_since(watermark)

        now = datetime.now(tz=timezone.utc).isoformat()
        asset_state_store.set("watermark", now)
        asset_state_store.set("last_run_summary", {"rows_loaded": len(records), "completed_at": now})

    load()
```

**Reading the store from a consumer Dag:**
```python
with DAG(dag_id="consumer", schedule=[ORDERS], start_date=datetime(2026, 1, 1), catchup=False):

    @task(inlets=[ORDERS])
    def consume(asset_state_store=None):
        asset_state_store = asset_state_store[ORDERS]
        summary = asset_state_store.get("last_run_summary") or {}
        print(f"Processing {summary.get('rows_loaded')} rows up to {asset_state_store.get('watermark')}")

    consume()
```

**Key rules:**
- `asset_state_store` is injected by Airflow as a named kwarg — declare it as `def my_task(asset_state_store=None)`. Do NOT combine with `**context`; Airflow injects it separately.
- Use `datetime.now(tz=timezone.utc).isoformat()` for timestamps — never `datetime.utcnow()` (not timezone-aware).
- Same JSON-serializable value constraint as `task_state_store`.
- No per-key expiry — asset state store entries have no TTL (the asset outlives any single run).
- Readable by any Dag that declares the asset as an inlet or outlet.

**Mapped tasks — last writer wins:**

`asset_state_store` is scoped to the asset, not the map index. If multiple mapped indices write the same key concurrently, the last write wins. Use distinct keys per index or ensure only one index writes to a given key.

```python
@task(outlets=[my_asset])
def load_partition(partition_id, asset_state_store=None):
    asset_state_store = asset_state_store[my_asset]
    # Distinct key per index — no race condition
    asset_state_store.set(f"offset_{partition_id}", new_offset)
```

**Before (anti-pattern):**
```python
Variable.set(f"watermark_{asset_name}", new_offset)   # global, not scoped to asset
```

**After:**
```python
@task(inlets=[my_asset], outlets=[my_asset])
def load(asset_state_store=None):
    asset_state_store = asset_state_store[my_asset]
    asset_state_store.set("watermark", new_offset)
```

---

## Step 5 — `ResumableJobMixin`: crash-safe external job submission

Use when an operator submits a job to an external system (Spark, Databricks, dbt Cloud, AWS Batch, etc.) and then polls for completion. Without this mixin, a worker crash during polling means the next retry submits a duplicate job.

**When NOT to use `ResumableJobMixin`:**

| Situation | Use instead | Why |
|---|---|---|
| A Triggerer is deployed and a deferrable operator exists (or can be written) | Deferrable operator | Frees the worker slot during polling; more resource-efficient |
| The task fans out many concurrent I/O operations within a single execution | `async def` task / `BaseAsyncOperator` | Async is for high-throughput I/O, not crash recovery |
| `retries=0` | — | Crash recovery has nothing to reconnect to |
| The external system has no trackable job ID (`submit_job` returns `None`) | Plain operator | The mixin's crash-safety guarantee is silently disabled; adds no value |

`ResumableJobMixin` holds the worker slot for the full polling duration — the same as a standard synchronous operator. The benefit is crash safety and job continuity, not resource efficiency.

**Opting out of crash recovery:**

The mixin ships with `durable=True` by default. Set `durable=False` to skip all `task_state_store` interaction and run a plain submit/poll/result cycle — useful in test environments or when the external system has its own dedup:

```python
MyBatchOperator(task_id="job", durable=False)

# Or via default_args to disable for all tasks in a DAG:
with DAG("my_dag", default_args={"durable": False}):
    ...
```

### Implementing the mixin

```python
from airflow.sdk import BaseOperator, ResumableJobMixin
from pydantic import JsonValue


class MyBatchOperator(BaseOperator, ResumableJobMixin):

    external_id_key = "batch_job_id"   # key used in task_state_store; set once, never rename

    def execute(self, context):
        return self.execute_resumable(context)  # never call self.execute() — call this

    def submit_job(self, context) -> JsonValue:
        # Submit and return the job identifier. This value is persisted to task_state_store
        # before polling starts. Return None only if the system has no trackable ID
        # (in that case crash-safety is disabled and the job resubmits on every retry).
        return self.hook.submit_batch(...)

    def get_job_status(self, external_id: JsonValue, context) -> str:
        # Query the external system. Return a raw status string.
        return self.hook.get_status(external_id)

    def is_job_active(self, status: str) -> bool:
        # Return True if the job is still running and should be reconnected to.
        return status in ("RUNNING", "PENDING", "QUEUED")

    def is_job_succeeded(self, status: str) -> bool:
        return status == "SUCCEEDED"

    def poll_until_complete(self, external_id: JsonValue, context) -> None:
        # Block until the job reaches a terminal state. Raise on failure.
        self.hook.wait(external_id)

    def get_job_result(self, external_id: JsonValue, context):
        # Return the job result after success. Return None if not applicable.
        return None
```

### What happens on retry

| Job state on retry | Mixin behaviour |
|---|---|
| Still running | Reconnects — calls `poll_until_complete` without resubmitting |
| Already succeeded | Returns `get_job_result` immediately |
| Failed / unknown | Submits a fresh job |

### `external_id_key` warning

> **Never rename `external_id_key` on an operator that is already deployed with in-flight task instances.** The old key is stored in `task_state_store` under the previous name. A rename makes the mixin treat every active retry as a fresh submission, defeating the crash-safety guarantee.

### Before (anti-pattern):
```python
def execute(self, context):
    job_id = Variable.get("spark_job_id", default_var=None)
    if job_id and self._is_running(job_id):
        self._wait(job_id)
    else:
        job_id = self.hook.submit(...)
        Variable.set("spark_job_id", job_id)   # global, race-prone
        self._wait(job_id)
```

**After:**
```python
class MySparkOperator(BaseOperator, ResumableJobMixin):
    external_id_key = "spark_job_id"
    def execute(self, context): return self.execute_resumable(context)
    def submit_job(self, context): return self.hook.submit(...)
    # ... implement the 5 other methods ...
```

---

## Step 6 — Configuration reference

```ini
[state_store]
# Full dotted path to the storage backend. Default writes to the Airflow metadata DB.
backend = airflow.state.metastore.MetastoreStateStoreBackend

# Days to retain task state store entries after their last update. 0 = disable time-based cleanup.
# Does NOT affect asset_state_store rows — asset state store has no TTL.
default_retention_days = 30

# Rows deleted per batch during cleanup. 0 = no batching (single unbounded delete).
# Tune on large deployments to reduce lock contention.
state_cleanup_batch_size = 0

# Auto-delete all task state store keys when a task succeeds. Default: False.
# Does NOT affect asset_state_store — asset state store persists across runs and must be cleared explicitly.
clear_on_success = False
```

**Worker-side backend** (optional, `[workers]` section) — routes task state store writes through a local backend before they reach the API server. Useful when large payloads or credentialed storage should stay on the worker:

```ini
[workers]
state_store_backend = mypackage.store.WorkerSideBackend
```

---

## Step 7 — Safety checklist

- [ ] Airflow version ≥ 3.3 (`af config version`)
- [ ] Values are JSON-serializable (`str`, `int`, `float`, `bool`, `list`, `dict` — no `datetime`, no custom objects)
- [ ] `task_state_store` keys are short, descriptive strings (avoid dots and slashes)
- [ ] Mapped tasks writing to `asset_state_store`: use distinct keys per index or accept last-writer-wins semantics
- [ ] Mapped tasks: fleet-wide state clear uses CLI/core API from a downstream task, not `clear()` inside the task body
- [ ] `ResumableJobMixin`: `external_id_key` is set and will not be renamed after deployment
- [ ] `ResumableJobMixin`: `execute()` calls `self.execute_resumable(context)`, not custom logic
- [ ] `ResumableJobMixin`: `durable=False` is intentional if crash recovery is disabled
- [ ] Large payloads (> configured `max_value_storage_bytes`) use a custom `[state_store] backend` or a worker side backend configured via: `[workers] state_store_backend`

---

## Related skills

- **authoring-dags** — general DAG writing patterns and conventions.
- **airflow-hitl** — pausing a DAG for human approval (Airflow 3.1+).
- **airflow** — `af config`, `af registry`, and general Airflow CLI reference.
