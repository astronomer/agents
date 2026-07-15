# Dagster → Airflow 3 concept map (master)

> **STATUS: reviewed; hardened through seven complete test migrations (incl. a real-warehouse execution), a live cutover rehearsal, and three adversarial review rounds.** Remaining `[VERIFY]` markers are individually flagged items.

Target assumptions for every mapping in this file:

- **Airflow 3.x on Astro Runtime**, authored TaskFlow-style with `airflow.sdk` assets as the flagship translation form.
- **Asset-first**: a Dagster asset graph translates to multiple small asset-producing DAGs wired by asset-aware schedules, not one flattened DAG. Imperative job→DAG translation is the fallback for legacy ops/graphs/jobs.
- **Cosmos** for dbt, provider packages for managed integrations.

Classification legend (every row carries one):

| Tag | Meaning |
|---|---|
| `MECH` | Mechanical translation; low risk; scriptable or near-scriptable |
| `JUDG` | Needs per-instance judgment (granularity, boundaries, idioms) |
| `REDESIGN` | Semantics differ enough that the pattern must be redesigned, not translated |
| `NONE` | No Airflow equivalent; documented mitigation required |

Deep-dive files are siblings in `reference/` (routing table in SKILL.md).

---

## 1. Project & definitions layer

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `Definitions` / code location | Astro project (`dags/` + `include/`) | JUDG | The `Definitions` object is the root the inventory scanner traverses |
| `workspace.yaml` (multiple code locations) | Separate Astro Deployments, or one project with DAG bundles | JUDG | Team/isolation boundaries drive the call |
| Asset loaders (`load_assets_from_modules`, `load_assets_from_package_module`, ...) | Nothing to migrate: loaders are assembly, not definitions; migrate what they LOAD | MECH | The inventory enumerates the loaded definitions themselves |
| `get_asset_key_for_model` / `dbt_asset_key` helpers used outside dbt modules | Resolve the referenced model's Airflow asset URI at migration time | JUDG | Load-time dbt-manifest coupling; the scanner surfaces these (`dbt_manifest_coupling`), see `components.md` |
| Components: library component instances (`defs.yaml` of shipped components) | Unwrap to the underlying integration's mapping row | JUDG | The YAML is config for a known component; map what it generates |
| Components: custom `Component` subclasses (`build_defs` logic) | Port what `build_defs` PRODUCES, not the class | REDESIGN | Real subclasses are programs: dynamic discovery via live APIs, per-item automation conditions, config-file fan-out. Snapshot their output to a static manifest at migration time and translate that |
| `setup.py` / `pyproject.toml` deps | `requirements.txt` + `Dockerfile` in Astro project | MECH | |
| Definitions branched on env vars at import time (e.g. dbt CLI vs dbt Cloud selected by env) | Migrate the branch the deployment actually runs; disposition the alternate branch explicitly | JUDG | The scanner records BOTH branches with their conditions; neither may be silently absent from the report |
| Third-party Dagster extension libraries (anything emitting definitions that isn't first-party `dagster-*`) | Classify the DEFINITIONS the library emits individually; the library's Dagster glue does not migrate, its core value usually survives as plain Python | JUDG | Read the extension's docs before assuming; flag heavy usage in the go/no-go conditions |
| `dagster.yaml` (instance config) | `airflow.cfg` / Astro Deployment settings | JUDG | Concurrency, retention, retries live in different layers |

## 2. Assets

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `@asset` | `airflow.sdk` `@asset` (auto DAG + single task + outlet), or `@task` with `Asset` outlet inside a domain DAG | JUDG | Granularity is the key decision: standalone asset-DAG vs task-in-DAG. See `assets.md` |
| `@multi_asset` (`can_subset=False`) | `@asset.multi(outlets=[...])` | MECH | `@asset.multi` emits ALL outlets on success; fine when the Dagster asset also always emits all |
| `@multi_asset` (`can_subset=True`) or with `internal_asset_deps` | Split into separate assets/tasks, or redesign | REDESIGN | Runtime subsetting via `context.selected_asset_keys` and internal dep graphs have no `@asset.multi` analog |
| Asset deps (`deps=`) crossing DAG boundaries | Asset-aware schedule on downstream DAG (`schedule=[upstream]`) | MECH | The flagship Airflow 3 win; edges become schedule conditions |
| Asset deps within one domain DAG | Task ordering (`>>` / TaskFlow returns) | MECH | Boundary choice (which deps become schedules vs edges) is JUDG |
| `AssetIn` / managed input loading | None; explicit read in task body | NONE | IO-manager decision tree, see `io-and-data-passing.md` |
| `MaterializeResult` / metadata | `yield Metadata(self, {...})` or `outlet_events[self].extra = {...}` | MECH | Consumer reads `inlet_events[upstream][-1].extra` |
| External assets (`AssetSpec`) | `Asset` updated via `POST /api/v2/assets/events` (keys on integer `asset_id`) or `AssetWatcher` | JUDG | `partition_key` in the event body is verified in source (main branch); confirm it's in your deployed version before relying on it |
| Observable source assets | `AssetWatcher` (event source) or polling sensor DAG | JUDG | |
| `@graph_asset` / graph-backed assets | TaskGroup whose final task outlets the asset | JUDG | Inherits the intra-graph data-passing problem |
| Asset groups / `key_prefix` | DAG naming + tags + asset name/URI conventions | MECH | Define one canonical URI convention; see `assets.md` |
| `code_version` / `data_version` | None (DAG versioning tracks code, not data) | NONE | Document the loss |
| `define_asset_job(selection=...)` | DAG materializing the selected asset set as tasks | JUDG | "Run this selection as one unit" is a first-class Dagster pattern; becomes a domain DAG whose boundary is the selection |
| `AssetSelection` DSL (`.groups()`, `.upstream()`, `.downstream()`, `.key()`) | Explicit task/DAG enumeration at codegen time | JUDG | Queries resolve against the asset graph during migration, not at runtime |

## 3. Data passing & IO managers

The central hard problem of the whole migration. Dagster persists op/asset outputs implicitly via IO managers; Airflow tasks share nothing by default.

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| IO manager (any) | None; per-edge explicit decision | NONE | Decision tree: (1) fuse producer+consumer into one task; (2) explicit storage write/read in task bodies; (3) XCom for small values, with `XComObjectStorageBackend` (`common-io`, size-threshold spillover to object storage) for medium |
| Built-in fs/s3/gcs pickle IO managers | Explicit read/write against same storage | JUDG | Mechanical-ish once storage layout is chosen |
| Opaque Python objects (ML models, matrices) via pickle IO managers | Explicit pickle to object storage | JUDG | XCom impossible (size/serialization); fusing collapses independently-materializable chains. Name the storage path convention explicitly |
| Partitioned file IO managers (partition-window → path encoding) | Shared key-derivation helper used by producer AND consumers | JUDG | The storage key is a function of the partition window; both sides of every cross-DAG edge must derive the identical path from `partition_key`. Recipe in `partitions.md` |
| Warehouse IO managers, non-partitioned | SQL executed via hooks/operators; table is the interface | JUDG | Often genuinely simplifies |
| Warehouse IO managers, partitioned | Hooks/operators + reimplemented idempotency contract | JUDG | The IO manager silently provided delete-then-insert partition overwrite on write and time-window WHERE clauses on read. Every producer and consumer must reimplement both or backfills stop being idempotent |
| Env-swapped IO managers (e.g. DuckDB locally, Snowflake in prod) | Env-switched connection/hook helper | REDESIGN | The IO-manager indirection is what made `dagster dev` run prod code locally; inlining SQL destroys it. Preserve with a deployment-aware helper or accept the local-dev loss explicitly |
| One asset reading N inputs from different IO managers (+ `AssetIn(metadata=...)` directives like column projection) | Per-input explicit reads | JUDG | Each input names its own storage backend and read options; there is no single "input loading" translation |
| Non-partitioned downstream consuming ALL partitions of an upstream | Explicit full-scan read | NONE | Unbounded rollup ("every partition to date") has no native mapper; windows/`RollupMapper` cover bounded ranges only |
| `In`/`Out` between ops (small data) | XCom (TaskFlow return values) | MECH | Size guardrails apply |

## 4. Partitions & backfills

**CONFIRMED 2026-07-09**: Airflow shipped native asset partitions (AIP-76) in **3.2.0**, expanded in **3.3.0**. All under `airflow.sdk`. Version floors matter:

- **3.2+**: `CronPartitionTimetable` (producer side), `PartitionedAssetTimetable` (consumer side), core mappers (`IdentityMapper`, `StartOfHourMapper` and other `StartOf*` mappers, `FixedKeyMapper`, `AllowedKeyMapper`, `ProductMapper`); tasks read `dag_run.partition_key`.
- **3.3+ only**: runtime/dynamic partition emission via `outlet_events[self].add_partitions(...)`, `RollupMapper`, `FanOutMapper`, windows (`DayWindow`, `SegmentWindow`, ...), wait policies (`WaitForAll`, `MinimumCount`).

Target Astro Runtime 3.3+ to get the full surface. Pre-3.2 fallback is logical-date mapping, documented in `partitions.md`.

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| Time-window partitions (daily/hourly/...) | `CronPartitionTimetable` on the producing asset | MECH | Native mapping on Airflow >= 3.2 |
| Downstream of partitioned asset | `PartitionedAssetTimetable` + wait policy | JUDG | Wait-policy choice (`WaitForAll` vs `MinimumCount`) encodes Dagster's implicit semantics |
| Partition mappings (`TimeWindowPartitionMapping`, identity, fan-out...) | Partition mappers (`StartOfHourMapper`, `RollupMapper`, `FanOutMapper`, `IdentityMapper`, ...) | JUDG | Map each Dagster mapping to nearest mapper; document deltas |
| Static partitions | `FixedKeyMapper` / `AllowedKeyMapper` key sets | JUDG | |
| Dynamic partitions (`DynamicPartitionsDefinition`) | `outlet_events[self].add_partitions(...)` (3.3+); `PartitionedAtRuntime` timetable | JUDG | `add_partitions` is the doc-confirmed path; `PartitionedAtRuntime` spelling appears in core docs but not Astronomer's guide, re-verify against the 3.3 API ref before emitting. Retroactive-key semantics need verification |
| Multi-partitions | `ProductMapper` composition, or key-encoding | REDESIGN | `ProductMapper` may cover two-dimensional cases; verify semantics before downgrading to JUDG |
| Dagster backfill (asset partitions) | `airflow backfill create --from-date --to-date --reprocess-behavior ...` (also UI/REST) | JUDG | Partition-aware backfill is native since 3.2 |
| `BackfillPolicy.single_run` | None: no single-run backfill exists (verified in testing) | NONE | Per-partition runs, or a manual run with explicit range params; see partitions.md |

## 5. Automation: schedules, sensors, declarative automation

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `ScheduleDefinition` (cron) | DAG `schedule` cron string + timezone, `catchup` set explicitly | MECH | Catchup is the trap: Dagster non-partitioned schedules never catch up (Airflow 3 default `catchup=False` matches); Dagster partitioned schedules DO fill gaps (`catchup=True`, BUT an old start_date means a run storm at unpause: use `catchup=False` + bounded backfill, see automation.md). MECH only once catchup is set per source type |
| `@schedule` with dynamic `RunConfig` | DAG params + templating, or leading config task | JUDG | Airflow schedules can't compute run config |
| `@sensor` (polling, cursor) | Deferrable sensor / `@task.sensor` in a polling DAG; cursor state → Variable/XCom | REDESIGN | Dagster sensors are arbitrary Python with cursors; see `automation.md`. Scanner heuristic: a plain `@sensor` polling materialization events of multiple assets is a hand-rolled multi-asset sensor; MECH boolean asset schedule ONLY when its cursor is pure last-seen dedup (fire once per new materialization) with no counting/threshold/per-partition logic, which is the REDESIGN case below. And see automation.md's partitioned-upstream trap first |
| Schedules/sensors targeting asset selections (`define_asset_job(selection=...)`, YAML `target:` queries) | One DAG per selection; overlapping selections need dedup rules | REDESIGN | In Airflow an asset has ONE producing DAG with ONE schedule. Two cadences over overlapping asset sets (e.g. @weekly everything + @daily subset) cannot both drive the same assets without restructuring |
| `@asset_sensor` (bare: fire on materialization) | Asset-aware schedule (`schedule=[asset]`) | MECH | Airflow 3 makes this native. PARTITIONED upstream → must be `PartitionedAssetTimetable` instead (see automation.md's trap: a bare asset schedule silently never fires) |
| `@asset_sensor` with evaluation logic | Asset schedule + guard task, or deferrable sensor | REDESIGN | `schedule=[asset]` fires unconditionally, passes no config. Metadata filtering, computed `run_config`, and cross-job triggering all need redesign |
| `@multi_asset_sensor` | Boolean asset conditions (`(a & b)`, `(a \| b)`, nestable) for plain fan-in; otherwise redesign | REDESIGN | Cursor-based custom Python over materialization events (counting, per-partition logic) cannot be expressed as a boolean schedule. Partitioned upstreams → `PartitionedAssetTimetable`, per automation.md's trap |
| `@run_status_sensor` / `@run_failure_sensor` | DAG/task callbacks, or listeners | JUDG | |
| `AutomationCondition.eager()` | Asset-aware schedule on upstreams | JUDG | Approximation drops four guarantees: eager skips when (a) any upstream partition is missing, (b) any upstream is in progress, (c) the asset itself is in progress, and (d) restricts to the latest time window. A bare asset schedule fires anyway; migration report must say so |
| `AutomationCondition.on_cron()` | No faithful native analog; `AssetOrTimeSchedule` is the nearest but has INVERTED semantics | REDESIGN | `on_cron` = cron tick THEN wait for ALL deps updated since that tick (AND). `AssetOrTimeSchedule` fires on time tick OR any asset update. Faithful version needs a gating pattern; see `automation.md` |
| `cron_tick_passed(x) & ~in_progress()` (the DOMINANT idiom in real projects) | Plain DAG cron schedule + `max_active_runs=1` | MECH | Unlike `on_cron`, fires on the tick regardless of parent updates. Do not conflate with the on_cron row below |
| `cron_tick_passed(x)` alone | DAG cron schedule | MECH | |
| `~in_progress()` | `max_active_runs=1` | MECH | |
| `any_deps_updated()` | Asset-aware schedule on deps | JUDG | Same success-only caveat as asset schedules |
| `in_latest_time_window()` | Latest-window guard in task logic | JUDG | |
| `code_version_changed()` | Cron + state-aware dbt builds (Fusion / dbt State skip unchanged models per run) | JUDG | Converges on rebuild-on-changed-models with cadence-bounded latency; the push-at-deploy semantics and non-dbt uses of code_version remain deltas. Maturity: Fusion public beta, Cosmos Fusion support since 1.11 (LOCAL mode); see `dbt.md` |
| `any_deps_match(...)` / `.allow()` / `.ignore()` scoping | Partial decomposition at best | REDESIGN | Per-dep scoped conditions have no schedule analog |
| Other complex `AutomationCondition` compositions | Partial via boolean asset schedules | REDESIGN | Decompose into the operator rows above; whatever remains goes to manual review |
| `AutoMaterializePolicy.eager()` / eager-style `auto_materialize_policy=` [deprecated spelling] | Same targets as `AutomationCondition.eager()` | JUDG | Legacy spelling, still common; normalize then map |
| `AutoMaterializePolicy.lazy()` [deprecated spelling] | Freshness/observability layer (see FreshnessPolicy row), NOT an asset schedule | JUDG | lazy was freshness/SLA-driven; routing it to an eager-style schedule is wrong (adversarial-review finding; matches automation.md) |
| `FreshnessPolicy` / freshness checks | Deadline Alerts (`DeadlineAlert`, 3.1+, experimental) and/or Astro **DAG Timeliness** alerts | JUDG | Deadline references are DAG-run-oriented; Dagster freshness is asset-oriented. Document the reframing |

## 6. Asset checks & data quality

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `@asset_check` | Downstream check task (`SQLColumnCheckOperator` / `SQLTableCheckOperator` from common-sql, or Python task) | JUDG | Blocking semantics are SCOPED in Dagster: a blocking check halts downstream assets in the SAME RUN only, and automation-driven (declarative) downstreams ignore blocking entirely |
| Blocking check: WHO carries the asset outlet | Producer task by DEFAULT; check task only as a deliberate, documented upgrade | JUDG | For same-run imperative job downstreams, a check-task gate matches Dagster. For asset-schedule downstreams (the flagship translation form) Dagster did NOT block on checks, so putting the outlet on the check task INTRODUCES gating Dagster lacked: a behavior change, never the silent default (adversarial-review finding) |
| Inline `check_specs=` / `AssetCheckSpec` on assets (incl. cross-system reconciliation checks) | Same translation as `@asset_check`: check task after the producing task | JUDG | Scanner must catch the inline spelling; cross-warehouse reconciliation checks need both connections. Blocking on inline specs is version-dependent (historically only `@asset_check` supported it); verify `AssetCheckSpec(blocking=True)` was actually set before assuming any gate |
| Check severity / blocking | Task failure vs warning-only (callback + continue) | JUDG | |
| dbt tests as checks | Cosmos-native dbt test execution | MECH | |
| Freshness-check builders (`build_last_update_freshness_checks`, `build_time_partition_freshness_checks`, `build_sensor_for_freshness_checks`) | Astro DAG Timeliness alert / `DeadlineAlert`; **NEVER a downstream check task** | JUDG | Freshness checks run even when the asset fails or is stale, which is their whole purpose; a success-gated downstream task inverts that. Route to the observability layer, not the DAG |

## 7. Legacy ops / graphs / jobs (imperative fallback)

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `@job` | DAG | MECH | |
| `@op` | `@task` | MECH | |
| `@graph` | TaskGroup | MECH | |
| Op `In`/`Out` wiring | TaskFlow returns (XCom) or explicit storage | JUDG | Same IO decision tree; consider fusing ops |
| `DynamicOut` / `DynamicOutput` | Dynamic task mapping (`expand`) | MECH | Runtime-verified (verified in testing). One trap: a collector task returning its mapped input re-pushes a `LazyXComSequence` and fails serialization; materialize with `list(...)` first (playbook entry) |
| `Nothing` dependencies | Pure ordering edges (`>>`) | MECH | |
| `@success_hook` / `@failure_hook` | `on_success_callback` / `on_failure_callback` | MECH | |
| `RetryPolicy(max_retries, delay, backoff, jitter)` | `retries`, `retry_delay`, `retry_exponential_backoff` | JUDG | Only `max_retries` + constant delay are mechanical. `Backoff.LINEAR` and `Jitter` have no Airflow equivalent; the exponential curves differ (Dagster `(2^n - 1) * delay` vs Airflow `~2^try_number` sec capped by `max_retry_delay`) |
| Executors (per-job) | Deployment-level executor choice | JUDG | Airflow executor is not per-DAG |

## 8. Resources & configuration

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `ConfigurableResource` (connection-like) | Airflow Connection + provider Hook | JUDG | Inversion of control: injected → pulled. Run-scoped `setup_for_execution`/`teardown_after_execution` lifecycle is lost; resources relying on teardown (sessions, locks, leases) need context managers in task bodies or callbacks |
| `ConfigurableResource` (client/service wrapper) | Plain Python construction in task body or `include/` helper | JUDG | Not everything should become a Connection |
| `EnvVar` | Env vars / Astro Environment secrets | MECH | |
| `Config` / `RunConfig` (Pydantic) | DAG `Params` (typed) + templating | JUDG | |
| Resources on sensors/schedules | Hooks inside the corresponding DAG code | JUDG | |

## 9. External execution (Pipes)

| Dagster Pipes client | Airflow operator | Class | Notes |
|---|---|---|---|
| `PipesSubprocessClient` | `@task.bash` / `BashOperator` or `ExternalPythonOperator` | MECH | |
| `PipesK8sClient` | `KubernetesPodOperator` | MECH | |
| `PipesDatabricksClient` | Databricks provider operators | MECH | |
| `PipesECSClient` / `PipesEMRClient` / `PipesGlueClient` / `PipesLambdaClient` | Matching AWS provider operators | MECH | |
| Pipes report-back protocol (materializations, metadata, logs from external process) | None; OpenLineage or explicit post-hoc metadata | NONE | Document the loss; the launch mapping is easy, the feedback channel isn't |

## 10. Integrations

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `dagster-dbt` (`@dbt_assets`, `DbtProject`, `DbtCliResource`) | Cosmos (`DbtDag` / `DbtTaskGroup`) | JUDG | Structure maps well, but: custom translators (grouping, automation) carry logic; automation via `code_version_changed()` has NO Cosmos equivalent (silently degrades to cron); branch-deploy DB swaps live in translator code |
| dbt profiles/targets per environment | Cosmos `ProfileConfig` per Deployment | JUDG | Dagster projects switch dbt targets on env vars; map each to the right Astro Deployment's profile |
| `dagster-fivetran` / `dagster-airbyte` | Fivetran/Airbyte provider operators | JUDG | Real projects discover connectors dynamically from the live API at definition time (`build_*_assets_definitions`); Airflow DAG parsing can't. Generate a static connector manifest at migration time. Custom workspace subclasses (e.g. skip-sync-on-reschedule) carry business logic provider operators lack |
| `dagster-sling` / `dagster-dlt` (embedded ELT) | Plain tasks invoking sling/dlt, or provider operators `[VERIFY availability]` | JUDG | |
| Plain-code dlt wrapped in a `ConfigurableResource` (the common real-world dlt shape, NOT `@dlt_assets`) | Vendor the dlt pipeline code unchanged; call it from `@task` bodies | MECH-ish | Execution-proven cold (verified in testing). The dlt DSL (`@dlt.resource`, `@dlt.source`) is dlt's, not Dagster's: it migrates as-is, and is NOT a Dagster resource needing a Connection |
| Warehouse resources (snowflake/duckdb/bigquery) | Provider hooks + SQL operators | JUDG | |
| `dagster-k8s` executor / ops | KubernetesPodOperator / K8s executor at deployment level | JUDG | |

## 11. Runtime semantics

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| Run tags | DAG tags + run conf/params | MECH | |
| `dagster-k8s/config` tags (per-job pod resources) | Per-task `executor_config` / `pod_override` | JUDG | Container CPU/memory requests set via run tags must land on the translated tasks, not the deployment |
| Tag-based concurrency limits / pools | Airflow Pools + `max_active_runs` / `max_active_tis_per_dag` | MECH | |
| Run coordinator / queues | Pools + `priority_weight` | JUDG | |
| Instance-level run retries | Default `retries` via `default_args` / config | MECH | |
| `context.log` | Task logger (`logging`) | MECH | |
| Definition metadata / descriptions | DAG/task `doc_md`, asset descriptions | MECH | |

## 12. Platform: Dagster+ → Astro

| Dagster+ | Astro | Class | Notes |
|---|---|---|---|
| Deployment | Astro Deployment (in a Workspace) | JUDG | |
| `dagster_cloud.yaml` | Astro project + Deployment config + `astro deploy` CI/CD | JUDG | |
| Branch deployments | Astro preview Deployments (per-branch ephemeral, via `deploy-action` CI sub-actions) | JUDG | Not just platform config: `DAGSTER_CLOUD_IS_BRANCH_DEPLOYMENT` / `DAGSTER_CLOUD_PULL_REQUEST_ID` env vars appear IN CODE (DB naming, URLs) and must be found and rewritten |
| K8s `env_secrets` / agent env vars per code location | Astro Environment secrets + Connections | JUDG | Map each named secret; nothing does this automatically |
| `agent_queue` routing (e.g. regional isolation) | Separate Astro Deployments (per region) + registry mapping | JUDG | Data-residency boundaries become deployment boundaries |
| Run/materialization history | Not migrated | NONE | Keep Dagster readable for a grace period; Airflow starts with empty history |
| Alert policies | Astro alerts (UI-configured, no DAG code): DAG Failure/Success/Timeliness/Duration, Task Failure/Duration; Slack/PagerDuty/Email/Opsgenie/DAG-Trigger channels | MECH | Map each Dagster alert policy to the nearest Astro alert type |
| Insights | Astro Observe (GA): freshness/timeliness SLAs, data products, health dashboards, Snowflake cost at pipeline level. No per-asset credit accounting | JUDG | |
| Serverless vs hybrid agents | Astro hosted vs dedicated/hybrid options | JUDG | |
| Asset catalog & lineage UI | Airflow 3 asset views + Astro lineage (OpenLineage) | NONE | Partial coverage; column-level lineage loss must be documented honestly |

## 13. Dev & testing workflow

| Dagster | Airflow 3 / Astro target | Class | Notes |
|---|---|---|---|
| `dagster dev` | `astro dev start` | MECH | Different feel; set expectations |
| `dagster definitions validate` | `astro dev parse` (DagBag import check) | MECH | First rung of the validation ladder |
| `materialize()` in unit tests | `dag.test()` (in-file) / `astro dev pytest` | JUDG | See `validation.md` |
| `build_asset_context()` etc. | Plain function tests of task callables | JUDG | |
| `dagster asset materialize` CLI | `astro run <dag-id>` (single DAG, one worker container) | MECH | |
