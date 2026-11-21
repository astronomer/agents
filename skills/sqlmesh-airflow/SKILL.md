---
name: sqlmesh-airflow
description: Use when orchestrating a SQLMesh project with Apache Airflow - running SQLMesh models/environments from a DAG, wiring `sqlmesh run` or `sqlmesh plan` into tasks, picking a gateway/connection for a SQLMesh project inside Airflow, or choosing between a single coarse-grained task vs one task per model. Triggers include "run sqlmesh from airflow", "orchestrate sqlmesh with airflow", "sqlmesh plan vs run in a dag", "schedule sqlmesh models", "sqlmesh gateway airflow connection". Not for dbt Core/Fusion (use cosmos-dbt-core or cosmos-dbt-fusion) and not for Tobiko Cloud's paid Airflow facade (`tobiko-cloud-scheduler-facade`), which has its own vendor docs and isn't Astronomer-specific.
---

# Orchestrating SQLMesh with Airflow

## Goal
A DAG that runs a SQLMesh project's models on schedule, with the plan/run split handled correctly, state and warehouse credentials sourced from Airflow connections, and (if fine-grained visibility is wanted) one task per model built from the SQLMesh project graph.

> Validated live against `sqlmesh==0.236.1` (config-override env var scheme, `Context`/`context.run` signatures, `plan --auto-apply` vs `run` behavior). SQLMesh's config internals move fast — re-check the env var names and API signatures against the installed version before trusting them on a newer release.

## Before you start

**There is no official Airflow provider for SQLMesh.** Do not `pip install apache-airflow-providers-sqlmesh` or import `airflow.providers.sqlmesh` — that package does not exist on PyPI; if you see it referenced in a blog post or in a hallucinated answer, ignore it. Open-source SQLMesh also no longer ships a first-party Airflow scheduler integration (`sqlmesh.schedulers.airflow` was removed from the SQLMesh repo; only Tobiko Cloud, the paid product, has a current Airflow integration, and it's a "facade" that mirrors a Tobiko Cloud-managed run rather than something Airflow executes). For plain open-source SQLMesh, the correct approach is to call the **SQLMesh CLI or Python API from inside Airflow tasks** — this skill covers that path.

Check `requirements.txt` for `sqlmesh` (plus its engine extra, e.g. `sqlmesh[snowflake]`) before writing any code. If it's missing, this is a net-new dependency — flag that to the user rather than assuming it's already installed.

## Steps

### 1. Understand `plan` vs `run` — do not conflate them
SQLMesh has two distinct verbs and a DAG should almost never call both the same way:

- **`sqlmesh plan <environment>`** compares your local project to the target environment, computes what changed, and (outside of `--auto-apply`) asks for interactive confirmation before applying schema/backfill changes. This is a deploy-time / CI-time operation — run it when code changes land (e.g. in your deploy pipeline or a manually-triggered DAG), not on every scheduled tick.
- **`sqlmesh run <environment>`** executes the *already-planned* environment for whatever intervals are due. This is the recurring, unattended operation — this is what your scheduled Airflow DAG should call.

Mixing these up is the most common mistake: an unattended `sqlmesh plan --auto-apply` running on every DAG tick can silently apply model/schema changes nobody reviewed. Keep `plan` in your deploy/CI workflow and `run` in the scheduled DAG.

**Success criteria:** you can state, for this project, where `plan` runs (CI/deploy) versus where `run` runs (the Airflow DAG), and they are not the same trigger.

### 2. Give SQLMesh a real, persistent state connection
SQLMesh tracks applied plans, snapshots, and intervals in a state backend (configured under `gateways.<name>.connection` or a dedicated `state_connection` in `config.yaml`). If a project defaults to local file/DuckDB state, that state must live on durable, shared storage reachable from wherever the Airflow task runs — not inside an ephemeral worker's local filesystem. On Astro (Celery/Kubernetes executors, autoscaling workers), a task can execute on a different worker each run; file-local state disappears with the pod. Point the state connection at a real database (e.g. Postgres) that survives across runs, exactly like you would for Airflow's own metadata DB.

**Success criteria:** `config.yaml`'s state connection is a durable external database, not a local file path, before this runs unattended in Airflow.

### 3. Resolve the gateway from an Airflow connection, not hardcoded secrets
SQLMesh selects environments via **gateways** (`gateway: prod` in `config.yaml` or `--gateway prod` on the CLI) — there is no `environment=` kwarg on the runtime API for this purpose; that's a common mix-up with the unrelated `sqlmesh plan <environment>` argument (which names the SQLMesh *virtual environment*, e.g. `dev`/`prod`, not the gateway). Keep warehouse credentials out of `config.yaml` and DAG source: pull them from an Airflow `Connection` at task runtime and inject them via SQLMesh's config-override environment variables, `SQLMESH__GATEWAYS__<GATEWAY_NAME>__CONNECTION__<FIELD>`, set right before constructing `Context`:

```python
import os
from airflow.hooks.base import BaseHook

conn = BaseHook.get_connection("snowflake_prod")
os.environ["SQLMESH__GATEWAYS__PROD__CONNECTION__USER"] = conn.login
os.environ["SQLMESH__GATEWAYS__PROD__CONNECTION__PASSWORD"] = conn.password
os.environ["SQLMESH__GATEWAYS__PROD__CONNECTION__ACCOUNT"] = conn.extra_dejson["account"]

context = Context(paths="/usr/local/airflow/include/sqlmesh_project", gateway="prod")
```

Never print the resolved credentials to task logs.

**Success criteria:** `af config connections` (or the project's connections) has a connection for the warehouse SQLMesh targets, and no password/token/account identifier appears in DAG source or `config.yaml`.

### 4. Pick coarse-grained or per-model granularity
Two valid patterns — pick based on how much retry/observability isolation you need, not by default:

**Coarse-grained (recommended default).** One task runs `sqlmesh run <environment>` for the whole project. This is usually the *right* default for SQLMesh specifically (unlike dbt): SQLMesh already computes per-model incremental intervals and skips work that isn't due, so a single task isn't wasteful the way a monolithic `dbt run` can be. Use `@task.bash` or `BashOperator`, or the Python API:

```python
from airflow.decorators import task

@task
def sqlmesh_run(environment: str, data_interval_start=None, data_interval_end=None):
    from sqlmesh import Context  # import inside the task, not at module scope

    context = Context(paths="/usr/local/airflow/include/sqlmesh_project", gateway="prod")
    context.run(
        environment=environment,
        start=data_interval_start,
        end=data_interval_end,
    )
```

Pass Airflow's `data_interval_start` / `data_interval_end` into `context.run(start=, end=)` so SQLMesh's incremental window matches the Airflow run being executed, rather than letting SQLMesh infer "now" from wall-clock time — the same idempotency principle as any other date-partitioned task.

**Per-model (only when you need it).** Build one Airflow task per SQLMesh model from the project graph (`context.models`, `context.dag`) so failures, retries, and durations are visible per model — mirroring what Cosmos does for dbt. There is no Astronomer-maintained equivalent to Cosmos for SQLMesh; the only accelerators are third-party community packages (e.g. `sqlmesh-dag-generator` on PyPI). Treat any such package as unvetted, pin its version, and read its source before pointing it at production — it is not an Astronomer-supported dependency. If per-model granularity matters, it's usually safer to hand-roll the model loop from `context.models` than to adopt an unmaintained generator wholesale.

**Success criteria:** the DAG's task granularity is a deliberate choice you can justify, not whatever the first example you copied happened to use.

### 5. Isolate the SQLMesh dependency footprint
`sqlmesh` plus its engine extras pin their own versions of heavy libraries (pandas, sqlglot, the warehouse client). Installing it straight into the Airflow scheduler/worker image risks version conflicts with other providers. Prefer running the SQLMesh call in an isolated environment — `ExternalPythonOperator`/`@task.external_python` against a prebuilt venv, `@task.virtualenv`, or `KubernetesPodOperator` with a dedicated image — the same isolation pattern Cosmos uses (`ExecutionMode.VIRTUALENV`) for dbt. Only inline it directly into the main worker image for small projects where you've confirmed there's no dependency conflict.

**Success criteria:** `requirements.txt` conflicts (if any) are identified before deploy, and the execution mode chosen reflects that check.

### 6. Keep parse-time light
Do not instantiate a SQLMesh `Context` or call any SQLMesh API at DAG module scope — `Context(paths=...)` reads the project and touches the state connection, which is exactly the kind of I/O that must stay inside a task (or inside `@task`-decorated code), not at import time. If you need the model list to build a per-model DAG (Step 4's second option), do that inside a callable invoked at task/DAG-parsing-safe boundaries, and cache/generate it out-of-band rather than hitting the state DB on every scheduler parse loop.

**Success criteria:** `af dags errors` shows no import errors, and a `grep` for `Context(` in the DAG file shows it only appears inside function/task bodies.

## Rules
- Never call `sqlmesh plan --auto-apply` from a recurring, unattended Airflow schedule — `plan` belongs in deploy/CI, `run` belongs in the DAG.
- Never hardcode warehouse credentials in `config.yaml` or DAG source — source them from an Airflow connection at task runtime.
- Never assume an official `apache-airflow-providers-sqlmesh` package or a still-current `sqlmesh.schedulers.airflow` module exists — verify against the installed `sqlmesh` version and PyPI before citing either.
- Never point SQLMesh's state connection at ephemeral local storage in a DAG meant to run unattended on autoscaling workers.
