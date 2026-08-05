---
name: airflow-state-store
description: Persists task and asset state across retries and DAG runs using Airflow 3.3's AIP-103 key/value stores (`task_state_store`, `asset_state_store`) and the crash-safe `ResumableJobMixin`. Use when the user asks about task state store, checkpointing in tasks, persisting state across retries, job IDs surviving worker crashes, watermarks, asset metadata, resumable tasks, crash-safe operators, or "what's new in Airflow 3.3". Also use proactively when reading a DAG that uses Variables or XCom for intra-task coordination state — flag the anti-pattern and recommend task_state_store or asset_state_store instead. Also use proactively when reviewing ANY DAG that submits a job to an external system and waits for it to finish — Databricks, Snowflake, BigQuery, Redshift, Spark, dbt Cloud, EMR, AWS Batch, etc. — whether that is one submit-and-wait operator or split across a separate submit task plus a sensor/polling task; this covers `wait_for_termination`, `deferrable`, `durable`, hand-rolled sensors polling a run/job id, and whether to collapse a submit+sensor split into one task. The `task_state_store`/`asset_state_store`/`ResumableJobMixin` state-persistence pieces require Airflow 3.3+; the submit+poll architecture guidance itself applies on any Airflow version — do not skip this skill for a pre-3.3 DAG.
---

# Airflow Task State Store (AIP-103)

Airflow 3.3 ships two key/value stores and a crash-safety mixin for operators that submit external jobs.

> **`task_state_store`, `asset_state_store`, and `ResumableJobMixin`'s crash-safety guarantee require Airflow 3.3+.** Check first:
> ```bash
> af config version
> ```
> Below 3.3: `task_state_store`/`asset_state_store` are unavailable, and `durable=True` is a no-op — provider operators ship a pre-3.3 `ResumableJobMixin` shim that always submits fresh (see Section 5). Tell the user those specific features aren't available yet and link the AIP-103 tracking issue. This does **not** gate Section 6's Triggerer-vs-`mode="reschedule"` decision, or the general "green submit ≠ success" anti-pattern — those apply on any Airflow version. On a pre-3.3 DAG, give that guidance in full; only drop the "`durable=True` adds crash-safety" half of it.

---

## Section 1 — Pick the right primitive

| I need to… | Use |
|---|---|
| Persist a cursor, offset, or job ID so a retry can resume instead of restart | `task_state_store` |
| Pass small coordination state within one task across retries (not between tasks) | `task_state_store` |
| Store a watermark or last-processed timestamp per asset, surviving across DAG runs | `asset_state_store` |
| Cache asset-level metadata (manifest hash, row count, schema version) | `asset_state_store` |
| Make an existing non deferrable operator crash-safe when it submits to an external system | `task_state_store` or `ResumableJobMixin` |

**When NOT to use these:**
- Passing data *between* tasks -> use XCom
- Large payloads (model weights, dataframes) -> use XCom with an object storage backend
- Config or secrets shared across DAGs -> use Variables or Connections

---

## Section 2 — Detect anti-patterns in existing DAGs (on demand)

When the user asks to review a DAG or asks "is there a better way", scan for these patterns and flag them:

| Pattern seen in DAG | Problem | Recommend |
|---|---|---|
| `Variable.get(...)` / `Variable.set(...)` inside a `@task` body for per-run state | Variables are global and shared; no scoping to task instance or retry | `task_state_store` |
| `context["ti"].xcom_push(key="job_id", ...)` to survive retries | XCom is scoped to a DAG run, not a retry; a new ti_id is issued per retry | `task_state_store` or `ResumableJobMixin` |
| Manual `if Variable.get("job_id"): reconnect else: submit` retry-resume logic | Reimplements what `ResumableJobMixin` already provides, without the crash-safety guarantee | `ResumableJobMixin` |
| `Variable.set("last_processed_at", ...)` for watermarks | Global; any DAG or task can overwrite it; no scoping to asset | `asset_state_store` |
| Separate `submit` task (`wait_for_termination=False` / fire-and-forget) + a second sensor/polling task waiting on the same external job (Databricks, Snowflake, BigQuery, Redshift, Spark, etc.) | A green submit task only means the job was *accepted*, not that it *succeeded* — only the sensor task's outcome reflects reality. | See **Section 6, "Submit-and-poll DAGs: one task or two?"** — the right call depends on Triggerer availability and job duration, not a single fixed answer. |

Show a before/after snippet when flagging. Use the canonical examples in Steps 3–5 as the "after".

**The submit+sensor split is worth a comment even when the sensor code is bug-free** — reviewing the sensor's code quality (correct `mode=`, correct terminal-state handling, cached hook) is a separate question from whether the two-task split is the right architecture. Follow **Section 6, "Submit-and-poll DAGs: one task or two?"** for that decision; don't re-derive it here.

---

## Section 3 — `task_state_store`: per-task coordination state

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

## Section 4 — `asset_state_store`: per-asset metadata across DAG runs

`asset_state_store` is scoped to an asset, not a task instance. It persists across DAG runs — the same key on the same asset is readable and writable by any task that produces or consumes it.

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

**Reading the store from a consumer DAG:**
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
- Readable by any DAG that declares the asset as an inlet or outlet.

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

## Section 5 — `ResumableJobMixin`: crash-safe external job submission

Use whenever a task submits a job to an external system (Spark, Databricks, dbt Cloud, AWS Batch, etc.) and could resubmit a duplicate on retry — whether that same task also polls for completion inside one `execute()` call, or hands the job id to a separate downstream poll/sensor task. Without this mixin (or a provider operator that already builds it in, like `DatabricksSubmitRunOperator`'s `durable=True` default), a worker crash after submission means the next retry of the **submit** task resubmits a duplicate job — that risk exists regardless of whether polling happens in that same task or a separate one.

**Scope check before recommending it:** if submit and poll are already two *separate* tasks (e.g. a `submit` task handing a job id to a downstream sensor/poll task via XCom), the **poll/sensor task** doesn't need this mixin — it never submits anything, so retrying it is already safe. The **submit task** still does; splitting off the poll step doesn't make the submit task's own duplicate-submission risk go away. See the table row below.

**When NOT to use `ResumableJobMixin`:**

| Situation | Use instead | Why |
|---|---|---|
| A Triggerer is deployed and a deferrable operator exists (or can be written) | Deferrable operator | Frees the worker slot during polling; more resource-efficient |
| The task fans out many concurrent I/O operations within a single execution | `async def` task / `BaseAsyncOperator` | Async is for high-throughput I/O, not crash recovery |
| `retries=0` | — | Crash recovery has nothing to reconnect to |
| The external system has no trackable job ID (`submit_job` returns `None`) | Plain operator | The mixin's crash-safety guarantee is silently disabled; adds no value |
| Submit and poll are already split into two separate tasks (submit task → XCom → sensor/poll task) | Nothing for the poll/sensor task — but the submit task itself still wants `durable=True` | The poll/sensor task never submits anything, so retrying it is already idempotent — no checkpoint needed there. The submit task can still resubmit on its own retry unless it's itself crash-safe: e.g. `DatabricksSubmitRunOperator.execute()` routes through `execute_resumable()` (and checkpoints the run id under `durable=True`, the default) even with `wait_for_termination=False` — keep that default on. A hand-rolled submit task (a plain `@task` calling the hook directly) gets none of this for free and should implement `ResumableJobMixin` itself. |

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

For the "submit + separate sensor task" DAG shape specifically — whether to collapse it to one task — see **Section 6, "Submit-and-poll DAGs: one task or two?"**. That's an architecture call driven by Triggerer availability and job duration. It's a different question from whether the submit task itself needs `durable=True` for crash-safety (usually yes, whether or not the split stays) — see the table row above.

---

## Section 6 — Submit-and-poll DAGs: one task or two?

A common DAG shape for Databricks/Snowflake/BigQuery/Redshift/Spark jobs: a `submit` task that fires the job with `wait_for_termination=False` (or equivalent) and returns immediately, followed by a hand-rolled sensor task that polls the same job to completion. The submit task going green the instant the external system *accepts* the job (not when it finishes) is always worth pointing out — a retry, alert, or SLA on the submit task alone tells you nothing about real job success, only the sensor task's outcome does. But whether the split itself should be removed depends on Triggerer availability:

**If a Triggerer is deployed** — collapse to one task with `deferrable=True` **and set `wait_for_termination=True` explicitly**. `deferrable=True` does not by itself imply `wait_for_termination=True` — on `DatabricksSubmitRunOperator`, the deferral helper only defers if `wait_for_termination` is also `True`; carry `wait_for_termination=False` over from an old submit task and it silently skips deferral and polling entirely, reproducing the exact fire-and-forget gap this section exists to remove.

This still frees the worker during polling and the task's own outcome reflects the real job result — but it isn't a strictly-better upgrade with zero tradeoff: the deferred path submits the job directly and never goes through the mixin's checkpointing step, so `durable=True` protects nothing here (unlike the synchronous path below). A worker crash between submission and the trigger taking over still resubmits on retry.

```python
run_job = DatabricksSubmitRunOperator(
    task_id="run_job",
    tasks=[{"task_key": "job", "notebook_task": {"notebook_path": NOTEBOOK_PATH}}],
    deferrable=True,
    wait_for_termination=True,   # required — deferrable=True alone does not imply this
)
```

**If no Triggerer is deployed** — this is a genuine tradeoff, not an automatic call either way. It splits into two cases depending on whether holding a worker for the job's duration is acceptable:

- **Job is OK to run synchronously (short/moderate runtime, or worker capacity isn't scarce) and the operator supports durable execution** (inherits `ResumableJobMixin` from Section 5, exposes `durable=True`) — recommend replacing the two-task pattern with **one task** in the operator's durable mode: `wait_for_termination=True`, `durable=True` (both already the default). This is not just fewer moving parts — the operator's built-in poll loop is covered by `ResumableJobMixin` end-to-end (submit *and* poll), so a worker crash mid-poll reconnects instead of resubmitting. A hand-rolled sensor task is a separate, non-mixin code path with its own retry semantics — often weaker (check whether it has its own `retries` set; many don't). Collapsing here removes an entire hand-maintained file, not just a task:

  ```python
  run_job = DatabricksSubmitRunOperator(
      task_id="run_job",
      tasks=[{"task_key": "job", "notebook_task": {"notebook_path": NOTEBOOK_PATH}}],
      wait_for_termination=True,   # synchronous — holds the worker for the run, acceptable here
      durable=True,                # default; ResumableJobMixin checkpoints the run id end-to-end
  )
  ```

- **Job is genuinely long-running and worker slots are scarce enough that holding one for the full duration is the real cost to avoid** — keep the `submit` + `mode="reschedule"` sensor split. That is the legitimate, worker-efficient design in this case, not an anti-pattern to remove on sight.

Either way:
- Verify downstream tasks (and any alerting/SLA) depend on the **sensor** task, not `submit`, if the split stays. If something downstream keys off `submit` succeeding, that's the real bug — fix the dependency, not the architecture.
- Name the tradeoff explicitly in the review (worker-slot cost and split outcome vs. single-task correctness and built-in crash-safety) rather than asserting one side is simply "the right pattern."

**Crash-safety and the collapse decision are related, but they're not the same call.** Whether to remove the split is decided by worker-slot cost (above) — that's independent of `durable=True`, which the submit task should generally keep on regardless of whether you collapse (see the "When NOT to use `ResumableJobMixin`" table in Section 5: the poll/sensor task needs nothing, but the submit task's own duplicate-submission risk doesn't disappear just because it's split from the poll task). When you do collapse, prefer the operator's own `durable=True` mode over keeping the hand-rolled sensor bolted on — the built-in path already carries `ResumableJobMixin`'s crash-safety for both submit and poll in one place, which a hand-rolled sensor doesn't replicate.

---

## Section 7 — Configuration reference

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

## Section 8 — Safety checklist

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
