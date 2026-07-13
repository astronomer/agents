> **STATUS: reviewed; runtime-verified in testing** (Runtime 3.3); gates exercised across the test migrations.

# Validation ladder (Dagster to Airflow 3 on Astro)

How a migrating agent (or human) proves each migrated unit works. The ladder runs cheap-to-expensive: fail fast on the cheapest check, never run an expensive gate before the cheap ones pass. A unit is a translated DAG (asset-DAG, domain DAG, or job-DAG) plus its `include/` helpers.

Two rules govern every gate:

- **Advance only on gate pass.** A unit moves to the next state only when the current gate is green. See the per-unit state machine at the bottom.
- **Baseline before you migrate.** Run the source project's own tests first and record what already fails (section 0). A gate failure that matches the baseline is not caused by the migration.

---

## 0. Baseline pre-existing failures (before touching anything)

Run the Dagster project's suite and its validate command, capture the output, and store it as the baseline:

```bash
# in the source Dagster project
dagster definitions validate 2>&1 | tee baseline/dagster-validate.log
pytest -q 2>&1 | tee baseline/dagster-pytest.log
```

Any test or asset already red here is quarantined: list it in the migration report under "pre-existing, not migration-caused" and exclude it from every gate below. This feeds rubric dimension 7 (no test regressions attributable to the migration). Skipping this step means every latent bug in the source gets blamed on the migration.

dagster-dbt projects using `DbtProject(...).prepare_if_dev()` need `DAGSTER_IS_DEV_CLI=1` in the environment (or a pre-run `dbt parse`) or both baseline commands fail with a confusing manifest-not-found ImportError.

---

## Gate 1: Python import + lint (cheapest)

The file is valid Python and passes lint. No Airflow machinery yet.

```bash
python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" dags/<unit>.py
ruff check dags/<unit>.py include/
```

**Pass:** `ast.parse` raises nothing; `ruff check` exits 0. Feeds rubric dimension 2. This is the floor: nothing below it matters if this fails.

Ported source code can violate the target lint even though Dagster shipped it fine. Policy: prefer a behavior-identical fix; when a fix would change semantics, `# noqa` with a comment and keep source behavior. Faithful porting outranks lint aesthetics.

---

## Gate 2: DagBag import check (does Airflow load it?)

A file can be valid Python and still fail to produce a DAG (bad imports, top-level exceptions, duplicate DAG ids). Two equivalent checks; run both, they catch different things.

The `astro dev parse` CLI check (whole project, no running env):

```bash
astro dev parse
```

The pytest DagBag snippet. Note the Airflow 3.x import path is `airflow.dag_processing.dagbag`, **not** `airflow.models`:

```python
import pytest
from airflow.dag_processing.dagbag import DagBag

@pytest.fixture()
def dagbag():
    return DagBag()

def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}

def test_dag_present(dagbag):
    assert dagbag.get_dag(dag_id="<expected_dag_id>") is not None
```

**Pass:** zero import errors and every expected DAG id resolves. CI helper for a machine-readable list: `airflow dags list-import-errors -o json`. Feeds rubric dimension 2 (threshold 100%).

Known breakage on Runtime 3.3 / astro CLI <= 1.43.1 (playbook entries exist for both): `astro dev parse` fails on the CLI's OWN scaffolded integrity test (`DagBag.__init__() got an unexpected keyword argument 'include_examples'`, removed in Airflow 3.3) regardless of DAG health, and any DagBag call passing `include_examples=` breaks the same way. The Gate 2 source of truth is an in-process `DagBag(dag_folder=...)` (no extra kwargs) inside the scheduler container; treat `astro dev parse` as advisory until the CLI catches up, and patch `.astro/test_dag_integrity_default.py` if it blocks CI.

---

## Gate 3: Structural asserts (does it match the inventory?)

(Canonical attribute spellings for everything asserted here live in the "Runtime-verified spellings" table at the bottom of this file; the snippets below already use them.)

The DAG loads, but does its shape match what the inventory manifest says it should be? Assert task count, dependency edges, schedule string, and asset outlets against the manifest emitted by the inventory scanner. This is where rubric dimension 3 (structural equivalence) is proven per unit.

```python
import json, pytest
from airflow.dag_processing.dagbag import DagBag

MANIFEST = json.load(open("include/inventory/manifest.json"))

@pytest.fixture()
def dagbag():
    return DagBag()

def test_structure_matches_manifest(dagbag):
    spec = MANIFEST["units"]["<unit_id>"]
    # dagbag.dags (in-memory dict), NOT get_dag(): get_dag() reads SERIALIZED
    # DAGs from the metadata DB. Note Gate 3 needs a migrated AIRFLOW_HOME
    # either way (run `airflow db migrate` first in bare envs); astro-dev
    # containers ship one. See the playbook's metadata-DB entry.
    dag = dagbag.dags[spec["dag_id"]]

    # task count
    assert len(dag.tasks) == spec["task_count"]

    # dependency edges (each edge is [upstream_task_id, downstream_task_id])
    edges = {(t.task_id, d) for t in dag.tasks for d in t.downstream_task_ids}
    assert edges == {tuple(e) for e in spec["edges"]}

    # schedule. Three expectation forms, matching validate_dag.py:
    #   spec["schedule"]       cron/string forms; dag.schedule round-trips '@daily'
    #   spec["asset_schedule"] asset-driven DAGs; each URI/name must appear in the condition
    #   spec["timetable_type"] partition timetables; class-name substring
    # (schedule_interval is removed; sdk timetables have no .summary. Eval-1 probe.)
    if "schedule" in spec:
        assert dag.schedule == spec["schedule"]
    if "asset_schedule" in spec:
        cond = repr(dag.schedule) + repr(dag.timetable)
        assert all(a in cond for a in spec["asset_schedule"])
    if "timetable_type" in spec:
        assert spec["timetable_type"] in type(dag.timetable).__name__

    # asset outlets produced by this DAG's tasks. Assert PYTHON tasks only:
    # Cosmos dbt tasks have empty outlets at parse time (assets are registered
    # at execution via AssetAlias); see dbt.md.
    outlets = {a.uri for t in dag.tasks for a in getattr(t, "outlets", [])}
    assert outlets == set(spec["asset_outlets"])
```

**Pass:** every assert green. A mismatch is either a translation bug or an intentional boundary choice (an edge became a cross-DAG asset schedule instead of a task edge); the latter must be reflected in the manifest and noted in the report, not silently asserted away. Cross-DAG asset-schedule edges are verified by inspecting `dag.timetable` / the asset conditions, not `downstream_task_ids`.

---

## Gate 4: Single-DAG execution (does it run?)

Execute the unit end-to-end against dev fixtures. Four ways, roughly cheapest-first:

```python
# in-file, fastest: append to the DAG module and run it directly
if __name__ == "__main__":
    dag.test()          # single serialized process; supports use_executor=True
```

```bash
airflow dags test <dag_id> [logical_date]     # CLI, same single-process engine
astro dev pytest                              # runs the tests/ suite in the Astro env
astro run <dag_id>                            # single DAG in one worker container
```

**Pass:** the run completes with all tasks in `success`. Feeds rubric dimension 5 (every generated DAG test-runs clean). For a partitioned unit, run at least one concrete `partition_key` and confirm the task read `dag_run.partition_key` as expected. Note: `partition_key` is None under `dags test`; the local way to exercise a concrete partition is `airflow backfill create --from-date D --to-date D` (see partitions.md).

**Fused-pipeline pass (single-writer stores).** Per-stage Gate 4 green does not imply the FUSED pipeline is green: standalone DAGs each own their process, so read_only/single-writer conflicts (DuckDB) only surface when the full pipeline runs in one `dags test` process (verified in testing). Before the fused-DAG gate, de-flag read_only on single-writer helper connections and apply the pool pattern, then run the fused DAG explicitly.

**Behavioral trigger check (asset-scheduled DAGs, mandatory when any upstream is partitioned).** `dags test` proves the DAG runs when forced; it does NOT prove the schedule ever fires. A boolean asset schedule downstream of a partitioned producer silently never triggers on Airflow 3.3 (verified in testing). So for every asset-scheduled DAG: materialize one upstream for real (backfill one partition or POST an asset event) and verify a downstream run is actually created before marking the unit complete.

Local-venv gate runs have two environment traps with playbook entries (macOS fork-safety SIGABRT needing `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`, and the split API-port config where `CORE__EXECUTION_API_SERVER_URL` does not follow `API__PORT`); check the playbook before debugging empty task logs.

Fresh-container caveats for `astro dev pytest` (verified in testing): Cosmos's dbt-ls cache reads Airflow Variables at parse time and dies in a fresh container (`no such table: variable`); set `AIRFLOW__COSMOS__ENABLE_CACHE=False` in `.env` for test runs. And use `dagbag.dags[...]`, never `get_dag()` (DB-backed).

---

## Gate 5: Data parity side-by-side (does it produce the same data?)

The strongest gate: run Airflow and the still-running Dagster instance over the **same logical window**, then compare outputs. This is the ground-truth backbone, deterministic and independent of the migration itself.

1. Pick a window with known Dagster output. Do NOT assume `MaterializeResult` metadata carries fixtures: real projects often record no row counts or checksums (some deliberately removed them for performance). Default to recomputing expected values from the Dagster-produced output itself; use recorded metadata opportunistically when it exists.
2. Run the Airflow unit over the identical window (`airflow dags test <dag_id> <logical_date>`, or a concrete `partition_key`).
3. Compare per output table/file:

```bash
# row count parity
dagster_rows=$(psql -tA -c "select count(*) from <table> where <window-filter>")
airflow_rows=$(psql -tA -c "select count(*) from <table> where <window-filter>")
[ "$dagster_rows" = "$airflow_rows" ] || echo "ROW COUNT MISMATCH"

# content parity: order-independent checksum of the window
md5 <(psql -tA -c "select * from <table> where <window-filter> order by 1")
```

**Pass:** row counts equal and checksums match on every comparable output. Feeds rubric dimension 5 (parity). Float-tolerance policy (testing finding): exact checksums apply to counts, keys, strings, and integer columns; float columns computed through different summation orders can differ by 1 ulp, so compare numeric frames with a tight relative tolerance (rtol 1e-9) and record in the report which tables passed exact vs tolerance, with the rtol used. A tolerance wider than 1e-6 is not parity; investigate instead. Where side-by-side is infeasible (external services, non-deterministic outputs), substitute mocked-run assertions and say so explicitly in the report; do not claim parity you did not measure.

**Incremental / overlapping-window variant.** Incremental-merge models with padded windows (e.g. dbt vars spanning `start - 3h` to `end + 1d`) have no discrete partition column, and adjacent windows overlap, so per-window row counts double-count boundary rows. For these: run a bounded backfill over a fixed range in BOTH systems, then compare a full-table ordered checksum plus total count. The same applies to Gate 6 below (there is no `where partition=<key>` column to filter on; use the full-table comparison after re-running the same range).

**Cross-engine canonicalization (verified in testing).** Byte checksums do not transfer across engines (numpy array vs JSON VARCHAR, TIMESTAMPTZ vs NTZ): compare within one engine where possible (both schemas checksummed by the same in-warehouse SQL), and across engines canonicalize first (stable column order, id-sorted rows, normalized timestamps/nulls) in one shared pandas routine, documenting the exact method beside the numbers.

**Seeded-inputs stage parity variant (nondeterministic sources).** When source assets are unseeded generators or live-API reads, same-window reruns can never match, but full mock-out is unnecessarily weak. The recipe that works (verified in testing): snapshot the Dagster-produced storage; seed the Airflow side with the identical raw inputs; re-run everything DOWNSTREAM of the source assets task-by-task (`airflow tasks test <dag> <task>` skips the source-regeneration tasks); checksum-compare all downstream outputs. Parity then covers every transformation while exempting only the genuinely nondeterministic sources, which the report lists explicitly.

---

## Gate 6: Idempotency re-run (partitioned producers only)

A partitioned producer must be safe to re-run: a second run over the same partition must leave the output identical, not doubled. The Dagster IO manager often provided delete-then-insert partition overwrite for free; the translated task must reimplement it (see mapping.md section 3).

```bash
# run the same partition twice, expect identical output
airflow dags test <dag_id> <logical_date>   # or the concrete partition_key
rows_after_first=$(psql -tA -c "select count(*) from <table> where partition=<key>")
airflow dags test <dag_id> <logical_date>
rows_after_second=$(psql -tA -c "select count(*) from <table> where partition=<key>")
[ "$rows_after_first" = "$rows_after_second" ] || echo "NOT IDEMPOTENT: rows changed on re-run"
```

**Pass:** row count and checksum are unchanged after the second run, AND the FULL-TABLE checksum equals the pre-re-run baseline. The second condition is load-bearing (verified in testing): a non-disjoint window predicate deletes a NEIGHBOR partition's boundary row on re-run, after which first==second compares clean while data is lost. Baseline the whole table before the re-run; a doubling means the overwrite contract was dropped, a shrink means the windows overlap. Fix the task, do not relax the gate.

---

## Per-unit state machine

Each unit walks these states. It advances only when the named gate passes:

```
Translate  ->  Fix-Import  ->  Fix-Lint  ->  Fix-Tests  ->  Verify-Parity  ->  Complete
              (Gate 2)       (Gate 1)      (Gates 3,4)     (Gates 5,6)
```

(Gate 1 lint and Gate 2 import are cheap enough to run together at the top; the state names follow the Airbnb per-file machine. Order the actual gate runs cheapest-first: 1, 2, 3, 4, 5, 6.)

Track state per unit (a JSON status file or an in-band comment block) so runs are resumable and selective re-runs target only the failed state.

### Retry-with-latest-error loop

At any gate, on failure: feed the **latest** error text back to the translator and retry the same unit. This brute-force loop (retry with the last validation error in context) beats prompt engineering; most units pass in under 10 attempts, with a tail of 50 to 100. Cap attempts (suggested 15), then escalate rather than grind.

### On persistent failure at any gate

When a unit will not pass after the retry cap:

- **Mark it `deferred` with a concrete reason** in the migration report (which gate, the failing assertion or error, what a human needs to resolve it). A deferred item with a reason is honest and passes the completeness gate; a silently omitted item is an automatic run failure (rubric dimension 1).
- **Never stub to fake a pass.** A task body that returns success without doing the work fails rubric dimension 6 automatically. Borrowing Bun's reviewer rule: if a workaround needs a paragraph of justification, it is wrong.
- **Fix the class, not the instance.** If several units fail the same way, record the pattern in `troubleshooting.md` and re-sweep, rather than hand-patching each unit.

---

## Runtime-verified spellings (settled by testing, Runtime 3.3-1 / Airflow 3.3.0)

Full probe transcript: `example-migrations/assets-dbt-python/runtime-probes.md`.

- `dag.schedule_interval` is **removed** (attribute and argument), confirmed at runtime.
- **`dag.timetable.summary` does NOT exist** on `airflow.sdk` timetables; the Gate 3 snippet above must assert on **`dag.schedule`**, which exists on sdk DAGs and round-trips the authored value (`'@daily'`, asset list, timetable object). `validate_dag.py` probes `schedule` first for this reason.
- Timetable classes: cron -> `airflow.sdk...trigger.CronTriggerTimetable`; `schedule=[asset]` -> `airflow.sdk...assets.AssetTriggeredTimetable` with `asset_condition=AssetAll(...)` (list = AND); `(a | b)` -> `AssetAny(...)`.
- `downstream_task_ids`, `task.outlets`, `Asset.name`, `Asset.uri` all exist with those spellings on `airflow.sdk` objects.
- **URI normalization trap**: a host-only URI (`scheme://one_part`) is stored with a trailing slash (`'dagster://order_forecast_model/'`); assert against the normalized form.
- `DagBag.__init__` no longer accepts `include_examples` (Airflow 3.3); `astro dev parse` on CLI <= 1.43.1 fails on its own scaffolded integrity test because of this (see troubleshooting.md). The import path `airflow.dag_processing.dagbag` is confirmed.
- Partitions: `dag_run.partition_key` is a plain string in the timetable's `key_format` (default `'%Y-%m-%dT%H:%M:%S'`, e.g. `'2026-07-07T00:00:00'` — NOT Dagster's `'2026-07-07'`); it is **None on `airflow dags test` / manual runs**. To execute one concrete partition locally (Gate 4), use `airflow backfill create --from-date D --to-date D`; `dags test`/`trigger` have no partition-key flag. `PartitionedAtRuntime` and the full mapper/window surface import from `airflow.sdk` (lazily; not in `dir()`).
