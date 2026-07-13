> **STATUS: reviewed; runtime-verified in testing** (Cosmos 1.15 / Airflow 3.3).

# dagster-dbt → Cosmos migration reference

Bottom line for the go/no-go gate: **dbt is never, by itself, a reason to stay on Dagster.** Every dbt-workflow loss in this file has an accepted-practice mitigation; record the deltas and proceed. (Per-model cost/column-lineage observability is assessed separately in the gate; see SKILL.md Phase 1.5.)

Your Dagster dbt integration (`@dbt_assets`, `DbtProject`, `DbtCliResource`, a
`DagsterDbtTranslator` subclass) becomes an Astronomer **Cosmos** `DbtDag` or
`DbtTaskGroup`. Cosmos parses your dbt `manifest.json` and renders one Airflow
task per model (plus test tasks), so the *shape* of the graph carries over
cleanly. What does NOT carry over is everything your translator computed in
Python: group names, custom asset keys, per-model automation conditions, and
branch-deployment database swaps. Those are the hard parts.

Target: Airflow 3.x on Astro Runtime, `astronomer-cosmos` >= 1.15. Verify every
Cosmos symbol against [the Cosmos docs](https://astronomer.github.io/astronomer-cosmos)
before shipping generated code.

## Quick map

| Dagster | Cosmos / Airflow 3 | Class | Where covered |
|---|---|---|---|
| `@dbt_assets` + `DbtProject` + `DbtCliResource` | `DbtDag` or `DbtTaskGroup` + `ProjectConfig`/`ExecutionConfig` | JUDG | below |
| dbt target switched by env var | `ProfileConfig` per Astro Deployment | JUDG | below |
| `DagsterDbtTranslator.get_asset_key` / group / metadata | `RenderConfig(node_converters=...)` or accept Cosmos defaults | JUDG | below |
| per-model `automation_condition` on `code_version_changed()` | cron + state-aware dbt builds (Fusion / dbt State) | JUDG | below |
| branch-deploy DB name in translator code | `ProfileConfig` targets + rewrite the Python | JUDG | below |
| `enable_asset_checks=True` (dbt tests as checks) | `RenderConfig(test_behavior=...)` | MECH | below |
| `.with_insights()` / Insights resources | strip (import-error on Astro); Astro Insights is UI-only | NONE | below |
| `.fetch_column_metadata()` / `.fetch_row_counts()` | OpenLineage / Astro lineage | JUDG | below |
| `DbtConfig` + run-tag warehouse swap on backfill | DAG `Params` + backfill `ProfileConfig`/`profile_args` | JUDG | below |
| `build_dbt_asset_selection` / `select=`/`exclude=` | `RenderConfig(select=[...], exclude=[...])` (comma=AND, space=OR) | JUDG | below |
| Python `@asset` up/downstream of dbt | cross-DAG asset schedule, or task in the same DAG | JUDG | below |
| `partitions_def` on `@dbt_assets` | partitioned dbt DAG; see `partitions.md` | JUDG | below |
| `dagster_dbt.cloud_v2` (dbt Cloud) | `apache-airflow-providers-dbt-cloud` (job trigger + sensor), NOT Cosmos | JUDG | below |

## Core structure: `@dbt_assets` → `DbtDag` / `DbtTaskGroup` (JUDG)

The simplest Dagster case (from `assets_dbt_python`):

```python
# BEFORE (Dagster)
from dagster_dbt import DbtCliResource, dbt_assets
from ..project import dbt_project

@dbt_assets(manifest=dbt_project.manifest_path)
def dbt_project_assets(context, dbt: DbtCliResource):
    yield from dbt.cli(["build"], context=context).stream()
```

```python
# AFTER (Cosmos, one standalone dbt DAG)
from cosmos import DbtDag, ProjectConfig, ProfileConfig, ExecutionConfig, RenderConfig
from cosmos.constants import ExecutionMode, TestBehavior
from pendulum import datetime

dbt_project_assets = DbtDag(
    dag_id="dbt_project_assets",
    project_config=ProjectConfig("/usr/local/airflow/dags/dbt/my_project"),
    profile_config=profile_config,                      # see ProfileConfig below
    execution_config=ExecutionConfig(execution_mode=ExecutionMode.LOCAL),
    render_config=RenderConfig(test_behavior=TestBehavior.AFTER_EACH),
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
)
```

Use `DbtDag` when the dbt project is its own schedulable unit; use
`DbtTaskGroup` when dbt is one stage inside a larger DAG with non-dbt tasks (the
Python-assets case below). `dbt.cli(["build"])` maps to `test_behavior`, not a
separate command. `DbtProject(project_dir=..., target=...)` splits into
`ProjectConfig` (project dir / manifest) and `ProfileConfig` (the target);
`DbtCliResource` disappears because Cosmos invokes dbt itself.

Source-side gotcha for the baseline: a project using
`DbtProject(...).prepare_if_dev()` needs `DAGSTER_IS_DEV_CLI=1` set (or a
pre-generated dbt manifest via `dbt parse`) for ANY source-side command,
including `dagster definitions validate` in the Phase 0 baseline. Without it the
project fails with a manifest.json-not-found ImportError. `validation.md` owns the
full baseline fix; this is the dbt-specific reason it happens.

## Assembling requirements.txt (do this BEFORE the first image build)

Translating the source's deps naively (the MECH `pyproject.toml` ->
`requirements.txt` mapping) produces a **broken image** on current Runtime. Known
class, hit in testing: `dbt-core` pins `mashumaro<3.15`, which cannot run on
Runtime 3.3's Python 3.14, so dbt cannot even parse and both DAGs fail at DagBag
import. The fix is an explicit override, `mashumaro>=3.16` (3.17 worked), in
`requirements.txt`. dbt-on-Astro dependency sets need the playbook's version-check
before you build the image; see the dbt dependency entry in
`reference/troubleshooting.md` rather than guessing pins here. At minimum: do not
treat the dbt requirements translation as mechanical, and run the playbook check
before the first `astro dev start`.

## ProfileConfig per environment (JUDG)

Dagster projects switch dbt targets with an env var read at definition time.
In a real example, `get_dbt_target()` returns `prod` / `branch_deployment` / `dev` /
`personal` based on `DAGSTER_CLOUD_*` env vars, and `DbtProject(target=...)`
picks the matching block in one shared `profiles.yml`.

```python
# BEFORE (Dagster): one profiles.yml, target chosen at runtime
DbtProject(project_dir=..., target=get_dbt_target())   # "prod" | "branch_deployment" | ...
```

Airflow does NOT switch targets at parse time per run. The clean mapping is one
Astro **Deployment per environment**, each pinning its own `ProfileConfig`. Two
options:

```python
# Option A: reuse the existing profiles.yml, pick target by env var per Deployment
profile_config = ProfileConfig(
    profile_name="my_project",
    target_name=os.environ["DBT_TARGET"],   # set per Astro Deployment
    profiles_yml_filepath="/usr/local/airflow/dags/dbt/my_project/profiles.yml",
)

# Option B: map the warehouse onto an Airflow Connection (no profiles.yml)
from cosmos.profiles import SnowflakeUserPasswordProfileMapping
profile_config = ProfileConfig(
    profile_name="my_project", target_name="prod",
    profile_mapping=SnowflakeUserPasswordProfileMapping(
        conn_id="snowflake_default", profile_args={"database": "PURINA", "schema": "analytics"},
    ),
)
```

Prefer Option A when the dbt repo already has a working `profiles.yml` (least
churn). Prefer Option B to consolidate secrets into Airflow Connections. The
per-`target` database/schema differences become per-Deployment Connection or
`profile_args` differences.

Not every dbt target is a Deployment. One real project's `get_dbt_target()` returns a
fourth target, `personal`, a developer-laptop schema with no cloud counterpart.
"One Deployment per environment" silently drops it. Map local/developer targets
to `astro dev start` running against a local `profiles.yml` target, NOT a
Deployment. Enumerate every value the target function can return and confirm each
maps to either a Deployment or the local dev flow; a target that maps to neither
is a gap to call out in the migration report.

## Custom translator porting (JUDG)

A `DagsterDbtTranslator` subclass is Python that runs while Dagster builds the
asset graph. One real project's `CustomDagsterDbtTranslator` computes, per model:

- **group name** from the dbt `fqn` path (snapshots → `"snapshots"`, else the directory path)
- **asset key** as `[database, schema, name]`, or a custom key from `meta.dagster.asset_key`
- **metadata**: a Snowflake Data Explorer URL
- **automation condition** (covered separately below)

Cosmos does not run your translator. Port each piece to its Cosmos equivalent, or
accept a Cosmos default and record the loss:

| Translator logic | Cosmos equivalent |
|---|---|
| group name from fqn | Airflow task grouping is by dbt folder already; custom grouping needs `RenderConfig(node_converters=...)` or dbt `+group` config. Often drop it |
| asset key `[db, schema, name]` | Cosmos emits Airflow `Asset` URIs from model names; a custom key scheme means custom `node_converters`. Pick ONE URI convention and apply it everywhere (see `assets.md`) |
| metadata URL | task `doc_md`, or drop |
| `meta.dagster.asset_key` overrides | move the override into dbt `meta` and read it in a `node_converter`, or normalize keys in dbt |

Do not try to reproduce a translator subclass one-to-one. Decide per project
whether custom keys/groups are load-bearing (something downstream schedules on
them) or cosmetic (UI only). Cosmetic ones get dropped in the migration report;
load-bearing ones need `node_converters` and must be verified against the Cosmos
docs, whose `node_converters` API is more limited than a Dagster translator.

## Per-model automation conditions → cron + state-aware builds (JUDG)

This is the sharpest edge. A real project's translator sets, per model:

```python
# BEFORE (Dagster): automation hangs on code_version_changed()
asset_is_new_or_updated = ~AutomationCondition.in_progress() & (
    AutomationCondition.code_version_changed() | AutomationCondition.missing()
)
# dwh_reporting models also add: | AutomationCondition.any_deps_updated()
```

`code_version_changed()` fires a rebuild when a model's compiled SQL changes.
Airflow has no per-model code-change TRIGGER, but the dbt ecosystem now covers
the effect from the other direction: **state-aware dbt builds** (the dbt Fusion
engine's state-aware orchestration, and dbt State, which also works with dbt
Core) rebuild only models whose code fingerprint or upstream data changed and
skip the rest as "Reused". Cosmos supports the Fusion engine since 1.11
(`ExecutionMode.LOCAL`). So the translation is a cron cadence whose runs are cheap
because unchanged models skip:

```python
# AFTER: cron cadence + state-aware skipping; the run after a deploy rebuilds
# exactly the changed models. Latency = the cadence, so size it accordingly.
DbtDag(..., schedule="0 * * * *", catchup=False)
```

Document TWO deltas in the equivalence row: (1) latency semantics: Dagster
rebuilds at deploy time (push); this rebuilds on the next tick (cadence-bounded;
tighten the cron since skips are near-free). (2) Maturity: Fusion is public-beta
era with Snowflake/Databricks adapters first, Cosmos Fusion support is newer
(LOCAL mode), and dbt State is in preview: verify the versions available to the
target before promising this, and fall back to CI-triggered `dbt build` on merge
(PR-gated, the standard non-Dagster pattern) plus a coarser cron when the
state-aware stack is not available.

The `~in_progress()` part maps to `max_active_runs=1` (MECH). The
`any_deps_updated()` part on `dwh_reporting` maps to an asset-aware schedule
(`schedule=[upstream_asset]`, JUDG, success-only). Flag every model whose only
automation was `code_version_changed()` so the cadence choice is deliberate.
See `automation.md`.

## Branch-deployment DB swaps in translator code (JUDG)

Branch-deploy logic often lives IN the translator/resource code, not just in
platform config. The test projects:

```python
# BEFORE (Dagster): DB name computed from Dagster Cloud env vars, in Python
PURINA_DATABASE_NAME = (
    f"PURINA_CLONE_{os.environ['DAGSTER_CLOUD_PULL_REQUEST_ID']}"
    if os.getenv("DAGSTER_CLOUD_IS_BRANCH_DEPLOYMENT") == "1" else "PURINA"
)
```

You MUST find and rewrite these. `DAGSTER_CLOUD_IS_BRANCH_DEPLOYMENT` and
`DAGSTER_CLOUD_PULL_REQUEST_ID` do not exist on Astro. The clean landing is the
dbt `branch_deployment` target with its own database, selected by the preview
Deployment's `ProfileConfig` (Option A above), so the clone-DB name lives in
`profiles.yml`, not Python. Grep the whole repo for `DAGSTER_CLOUD_` before
declaring the dbt migration done; these strings also appear in metadata URLs.

## dbt tests: `enable_asset_checks` → `TestBehavior` (MECH)

`DagsterDbtTranslatorSettings(enable_asset_checks=True)` surfaces dbt tests as
Dagster asset checks. **Check the project's dagster-dbt version before assuming
blocking semantics:** the default flipped to `True` in dagster-dbt 0.23.0
(dbt-core >= 1.6). Older in-the-wild projects defaulted to `False`, where dbt
tests were observations that did NOT block downstream. If the source project ran
with the old default, a faithful migration uses `AFTER_ALL` or `NONE`, not the
blocking `AFTER_EACH`. Cosmos runs the same tests natively; choose where via
`RenderConfig(test_behavior=...)`:

| `TestBehavior` | Behavior | Use when |
|---|---|---|
| `AFTER_EACH` (default) | test task right after each model; a failing test blocks that model's children | closest to Dagster blocking checks |
| `AFTER_ALL` | one test task after the whole run | tests are cheap and you want one gate |
| `BUILD` | uses `dbt build` (interleaves run + test per node) | mirrors `dbt build` semantics |
| `NONE` | skip tests entirely | tests run elsewhere |

`AFTER_EACH` is the faithful default: it reproduces blocking-check semantics (a
failed test stops downstream models). `should_detach_multiple_parents_tests=True`
(Cosmos >= 1.8.2) splits a test spanning multiple parents into a standalone task.
`enable_source_tests_as_checks` in Dagster maps to source tests being rendered by
Cosmos; verify source-test rendering in your Cosmos version.

## Selectors: `build_dbt_asset_selection` / `select`/`exclude` → `RenderConfig` (JUDG)

`@dbt_assets(select=..., exclude=...)` and `build_dbt_asset_selection(...)` map
to `RenderConfig(select=[...], exclude=[...])`. **Do NOT naively split the
Dagster string into a list.** dbt selector combination is delimiter-sensitive and
the test projects relies on it:

- **comma = intersection (AND)**: `"tag:a,tag:b"` selects models matching BOTH.
- **space = union (OR)**: `"tag:a tag:b"` selects models matching EITHER.

The test projects deliberately uses both: `select=",".join([...])` (intersection) and
`exclude=" ".join([INCREMENTAL_SELECTOR, SNAPSHOT_SELECTOR])` (union). Cosmos
joins the elements of a `RenderConfig` list with **spaces** (union) when it builds
the dbt command, so each list element is one union term. That means:

```python
# BEFORE (Dagster): comma-joined = INTERSECTION; space-joined = UNION
@dbt_assets(select="config.materialized:incremental,tag:nightly",   # AND
            exclude="config.materialized:incremental resource_type:snapshot")  # OR

# AFTER (Cosmos): keep an intersection INSIDE one element; split a union across elements
RenderConfig(
    select=["config.materialized:incremental,tag:nightly"],   # one comma element = AND preserved
    exclude=["config.materialized:incremental", "resource_type:snapshot"],  # two elements = OR
)
```

Splitting a comma-joined `select` into separate list elements silently converts
an intersection into a union and BROADENS the selected set (a real correctness
bug in the emitted DAG). Verify Cosmos' list-join behavior against your Cosmos
version before trusting the union assumption above. Selector syntax otherwise
carries over: `tag:`, `path:`, `config.materialized:`, `config.meta.<key>:`, and
graph operators. The test projects splits its project into three `@dbt_assets`
(non-partitioned, incremental/partitioned, snapshots); each becomes its own
`DbtDag`/`DbtTaskGroup` with the matching select/exclude. Dagster `AssetSelection`
DSL that resolves against the graph (`.downstream()`, `.upstream()`) has no Cosmos
runtime analog: resolve those to concrete dbt selectors at migration time.

## Streaming post-processors: strip Insights, reroute metadata (NONE / JUDG)

The test projects dbt bodies end in a chain that has NO Cosmos equivalent:

```python
# BEFORE (Dagster): dagster_open_platform dbt/assets.py
yield from (
    dbt.cli(_dbt_args("build", config), context=context)
    .stream()
    .fetch_column_metadata()   # column schema into asset metadata
    .fetch_row_counts()        # row counts into asset metadata
    .with_insights()           # Dagster+ Insights (cost/usage) hook
)
```

Cosmos runs dbt directly, so `.stream()` and every post-processor on it vanish.
Handle each:

- `.fetch_column_metadata()` / `.fetch_row_counts()` (JUDG): these enriched the
  Dagster asset catalog. On Astro the equivalent is **OpenLineage / Astro
  lineage** (column schema, row facets), enabled per Deployment, NOT a hand-rolled
  metadata call. Accept the reframing; do not try to reproduce the exact metadata
  keys.
- `.with_insights()` and the `InsightsBigQueryResource` / `InsightsSnowflakeResource`
  / `create_snowflake_insights_asset_and_schedule` symbols (NONE): these are
  Dagster+ Insights, a code-level product API. They **import-error on Astro** and
  MUST be stripped, not translated. Astro Insights is UI-configured, no code.

These symbols are in the `astro-deployment.md` grep checklist (alongside
`DAGSTER_CLOUD_`); a build that still imports `dagster_cloud.dagster_insights`
will fail at parse time. Grep and remove before declaring the dbt migration done.

## Config-driven backfill routing (JUDG)

The test projects routes backfills to a different warehouse via run config and run tags,
in Python:

```python
# BEFORE (Dagster): op Config + run-tag conditional warehouse swap
class DbtConfig(dg.Config):
    full_refresh: bool = False
    backfill: bool = False

# on a backfill run, inject --vars and point at a bigger warehouse + longer timeout
vars_arg = {"backfill": True,
            "backfill_snowflake_warehouse": "BACKFILL_WH",
            "backfill_statement_timeout_seconds": 24 * 60 * 60}
```

Map the pieces:

- `dg.Config` fields (`full_refresh`, `backfill`) → **DAG `Params`** (typed),
  read in the task and passed through to dbt `--vars` via `operator_args`.
- run-tag-conditional warehouse (`DBT_BACKFILL_RUN_TAG` → `BACKFILL_WH` + longer
  `statement_timeout`) → a **backfill-specific `ProfileConfig`** (or a
  `profile_args` override selected when the `backfill` param is set), so backfill
  runs bind the larger warehouse and timeout. There is no run-tag-reads-warehouse
  indirection in Airflow; the branch becomes an explicit param check that picks
  the profile or `--vars`.

Keep the `--vars backfill=True` injection: it drives dbt macro behavior in the
project and must still reach dbt. Only the *routing* mechanism (tags/config)
changes, not the dbt-side contract.

## Python assets up/downstream of dbt (JUDG)

A Python `@asset` that reads a dbt model (or feeds one) is a cross-boundary edge.
Two translations:

- **Same DAG**: `DbtTaskGroup` inside a DAG, with Python `@task`s wired before/
  after it via `>>`. Best when the Python step is tightly coupled to this dbt run.
- **Cross-DAG**: the dbt DAG emits an `Asset` on completion; the Python asset-DAG
  uses `schedule=[that_asset]`. Best when they run on different cadences.

### Cosmos asset emission is a RUNTIME event, not parse-time (verified, eval 1)

Do NOT assume a rendered Cosmos DAG carries model outlets. On Cosmos 1.15 /
Airflow 3.3, dbt task `outlets` are **empty at parse time**. Cosmos attaches an
`AssetAlias` and registers the model assets **during execution** ("Assigning
outlets with DatasetAlias in Airflow 3"). Two consequences the migrator must
handle:

- **Gate 3 outlet assertions must exempt dbt tasks.** Assert outlets on Python
  tasks only; a parse-time / DagBag inspection sees nothing on Cosmos tasks. Do
  not fail the gate on "missing" dbt outlets.
- **Cross-DAG `schedule=[Asset(uri)]` on a dbt model only resolves after the
  first run.** The alias materializes at execution, so the consuming DAG cannot
  bind the asset until one run has emitted it, and the URI must be captured from a
  RUN (run log), not from a rendered DAG.

The verified runtime URI form for a dbt-duckdb model (captured from a real run):

```
duckdb:/usr/local/airflow/include/data/example.duckdb/example/dbt_schema/<model>
```

That is scheme + profile-path + database + schema + model. Note the `//` after
the scheme **collapses in `Asset.uri`** (`duckdb:/...`) but is **kept in
`Asset.name`** (`duckdb:///...`); wire cross-DAG consumers against the exact
`.uri` form from a run, not a hand-derived string. Pin your own convention for
Python-asset URIs (see `assets.md`); `get_asset_key_for_model(...)` lookups from
the source resolve to whatever Cosmos runtime URI you standardize on.

## Partitioned dbt assets (JUDG)

A real project runs an incremental `@dbt_assets` with `partitions_def=` and passes
`min_date`/`max_date` dbt vars derived from `context.partition_time_window`. In
Cosmos, pass run-scoped `--vars` via `operator_args`, computed from
`dag_run.partition_key`. The partition-key → window derivation is the shared-recipe
problem in `partitions.md`: producer and every consumer must derive identical
`min_date`/`max_date` from the key. Do not reinvent it here.

Watch the `BackfillPolicy.single_run()` interaction. The test projects pairs it with
partitions, and on a single-run backfill `context.partition_time_window` spans the
**whole** requested range, not one partition, so `min_date`/`max_date` become one
dbt invocation covering the entire range (the test projects also pads: `min_date` shifts
back 3 hours, `max_date` forward 1 day). There is NO single-run backfill in Airflow (verified in testing). The equivalent is one MANUALLY TRIGGERED run
with explicit range params (the task ignores `partition_key` and reads the params),
feeding the full-range `(start, end)` into `--vars`. Reproduce the same padding in
the window helper, or the backfill query bounds shift. Do NOT emit one dbt run per
partition when the source used `single_run`; that changes the query semantics and
the row set.

## Execution modes on Astro (JUDG)

`ExecutionConfig(execution_mode=...)`. `ExecutionMode.LOCAL` runs dbt in the
Airflow worker: simplest, and the default on Astro when dbt deps fit the image.
Use `VIRTUALENV` to isolate dbt's Python deps from Airflow's; use `KUBERNETES` /
`DOCKER` (or cloud-run modes `AWS_EKS`, `AWS_ECS`, `GCP_CLOUD_RUN_JOB`,
`AZURE_CONTAINER_INSTANCE`) to run each model in its own pod/container. Start
with `LOCAL`; escalate only when dependency conflicts or isolation demand it.

## dbt Cloud (`dagster_dbt.cloud_v2`) → dbt Cloud provider (JUDG)

If the source runs dbt in **dbt Cloud** (the `dagster_dbt.cloud_v2` surface:
`DbtCloudWorkspace`, `@dbt_cloud_assets` / `dbt_cloud_assets`,
`load_dbt_cloud_asset_specs`, `build_dbt_cloud_polling_sensor`), the target is
`apache-airflow-providers-dbt-cloud`, NOT Cosmos. Cosmos runs dbt itself; the dbt
Cloud provider triggers a job that dbt Cloud runs.

Job triggering and polling map cleanly (MECH-ish): a `DbtCloudWorkspace` job run
becomes a `DbtCloudRunJobOperator`, and `build_dbt_cloud_polling_sensor` becomes
`DbtCloudJobRunSensor`. Verify these names against the provider docs before
emitting (the provider evolves: the old `DbtCloudJobRunAsyncSensor` was removed in
favor of `DbtCloudJobRunSensor(deferrable=True)`).

```python
# AFTER: trigger a dbt Cloud job and wait, in one task (deferrable)
from airflow.providers.dbt.cloud.operators.dbt import DbtCloudRunJobOperator

run_dbt = DbtCloudRunJobOperator(
    task_id="run_dbt_cloud_job",
    dbt_cloud_conn_id="dbt_cloud_default",   # a Connection backed by DbtCloudHook
    job_id=12345,
    deferrable=True,                          # defers to the triggerer instead of polling a worker
)
# Discovery: confirm the current operator/sensor/hook names and args against
# airflow.apache.org/docs/apache-airflow-providers-dbt-cloud/stable/operators.html
# A standalone wait uses DbtCloudJobRunSensor(deferrable=True); DbtCloudHook is the connection type.
```

The hard loss is granularity. `load_dbt_cloud_asset_specs` gives Dagster one asset
PER MODEL inside a Cloud job; the provider has **no per-model analog**. To Airflow,
the models inside a Cloud job are invisible: a job run is one opaque task. So any
cross-DAG wiring that keyed on an individual dbt model must instead key on the
**JOB** (JUDG). A downstream DAG waits on the whole job's completion, not on a
specific model. Document this granularity loss in the report; per-model lineage
inside dbt Cloud does not survive.

Env-branched CLI-vs-Cloud definitions are common (the cold-eval project selected
dbt Cloud vs local dbt at import time on an env var, one `Definitions` with both
branches). Migrate the branch the deployment **actually uses** (Cosmos for the CLI
branch, this provider for the Cloud branch), and record the other branch as a
dispositioned alternate in the manifest, not silently dropped. If both branches
genuinely ship, they are two target shapes, so say which Deployment uses which.

## Legacy spellings to catch

The scanner must also flag pre-`@dbt_assets` code, common in older projects:

- `load_assets_from_dbt_project(...)` and `load_assets_from_dbt_manifest(...)`
  (superseded by `@dbt_assets`) → same Cosmos `DbtDag`/`DbtTaskGroup` target.
- `dbt_cli_resource` (snake_case, legacy) → `DbtCliResource` is already gone in
  the Cosmos model; both map to Cosmos invoking dbt directly.
- `DbtManifestAssetSelection.build(...)` (real projects' schedules use it) → resolve to
  concrete dbt selectors for `RenderConfig`.

## What could not be verified

- Cosmos `node_converters` is the stated hook for custom asset keys/groups, but
  its exact API surface was not doc-confirmed in this pass; verify before emitting
  `node_converters` code. It is materially less expressive than a Dagster translator.
- `enable_source_tests_as_checks` → Cosmos source-test rendering parity not
  doc-confirmed; verify per Cosmos version.
- Cross-DAG wiring against dbt-model assets is now RUNTIME-verified (verified in testing): the
  asset is emitted via `AssetAlias` at execution, URI form above. What remains
  unconfirmed is `should_detach_multiple_parents_tests` (>=1.8.2); verify per
  Cosmos version.

Sources: [Cosmos configuration](https://astronomer.github.io/astronomer-cosmos/configuration/index.html), [RenderConfig select/exclude](https://astronomer.github.io/astronomer-cosmos/configuration/selecting-excluding.html), [ProfileConfig / profiles_yml_filepath](https://astronomer.github.io/astronomer-cosmos/profiles/index.html).
