# Playbook: failure classes and their fixes

Living catalog. Every validation failure that gets diagnosed lands here as a class with its fix, so the next occurrence is a lookup, not an investigation. Entries are added by the migration loop (SKILL.md rule 4) and by eval runs.

Format per entry: symptom (the error or misbehavior as observed), class (what is actually wrong), fix (what to change, in the pattern not the instance), origin (which project/eval surfaced it).

---

## dbt-core unimportable on Astro Runtime (Python 3.14): mashumaro UnserializableField

- **Symptom**: every DAG file touching Cosmos fails DagBag import (and `dbt parse` fails in the container) with `mashumaro.exceptions.UnserializableField: Field "schema" of type Optional[str] in JSONObjectSchema is not serializable`.
- **Class**: dependency resolution, not migration code. Astro Runtime 3.3-1 ships Python 3.14 (PEP 649 lazy annotations); dbt-core (<= 1.11.x) pins `mashumaro[msgpack]<3.15`, and mashumaro < 3.16 cannot build (de)serializers under Python 3.14.
- **Fix (pattern)**: version-dependent. Runtime 3.3-1 (pip installer): add `mashumaro==3.17` (any >= 3.16) to `requirements.txt`; pip warns about dbt-core's pin but installs. Runtime **3.3-2+ installs requirements with uv's STRICT resolver**, which refuses the conflicting pin outright (`No solution found when resolving dependencies` at image build) — leave requirements.txt resolvable and force the override post-resolve in the Dockerfile: `USER root` / `RUN uv pip install --system --no-deps 'mashumaro>=3.16'` / `USER astro`. Remove once dbt-core lifts the pin.
- **Origin**: test migration (`assets_dbt_python`), Runtime 3.3-1; uv-resolver variant from testing (`project_fully_featured`), Runtime 3.3-2.

## Partition-stamped asset events never trigger plain asset-scheduled consumers

- **Symptom**: a DAG with `schedule=[a, b]` / `schedule=(a & b)` downstream of a PARTITIONED producer parses clean, passes structural gates, and never runs; `asset_dag_run_queue` stays empty; no error anywhere.
- **Class**: Airflow 3.3 asset-trigger semantics. Outlet events of a partitioned DAG run are automatically partition-stamped, and `airflow/assets/manager.py::_queue_dagruns` skips non-partitioned consumer DAGs whenever the event carries a `partition_key` (`if not non_partitioned_dags or partition_key is not None: return None`).
- **Fix (pattern)**: every asset-scheduled consumer of a partitioned producer uses `PartitionedAssetTimetable(assets=<condition>)` even when the consumer is conceptually non-partitioned. Default `IdentityMapper` fires one consumer run per upstream key once ALL condition members have that key's event (AND respected; re-materialization re-fires). Add a behavioral trigger check to validation (emit upstream events, assert the consumer run appears): no parse-time gate catches this.
- **Origin**: test migration (`project_fully_featured`), Runtime 3.3-2, hn_tables_updated sensor translation.

## DuckDB (single-writer local warehouse) vs parallel Airflow tasks / Cosmos dbt processes

- **Symptom**: intermittent `IOException: Could not set lock on file "....duckdb": Conflicting lock is held in airflow worker (PID ...)` on tasks that write to a shared DuckDB file; may pass on lucky timing.
- **Class**: concurrency contract change. Dagster ran sibling asset writes through one process pool where collisions were rare, and dbt was ONE `dbt build` process; Airflow runs sibling tasks in parallel workers and Cosmos runs one dbt process per model, so a single-writer database gets concurrent writers.
- **Fix (pattern)**: a 1-slot Airflow pool on every task that opens the file — `pool=` on @task, `operator_args={"pool": ...}` on DbtTaskGroup. Declare it in `airflow_settings.yaml` (astro dev applies pools on start) and create the same pool on the Deployment.
- **Origin**: test migration (`project_fully_featured`), comments/stories view creation race; independently hit and pool-pattern-verified in testing (gauntlet) under parallel asset-triggered DAGs. Applies to any single-writer local store (DuckDB, SQLite); keep connections short-lived (open-write-close per task). Reference home: io-and-data-passing.md, "Single-writer stores under Airflow parallelism".

## `astro dev parse` fails from the CLI's own bundled integrity test on Airflow 3.3

- **Symptom**: `astro dev parse` exits nonzero with `TypeError: DagBag.__init__() got an unexpected keyword argument 'include_examples'` in `.astro/test_dag_integrity_default.py`, regardless of your DAGs.
- **Class**: tooling incompatibility. Airflow 3.3 removed `include_examples` from `DagBag.__init__`; astro CLI (<= 1.43.1) scaffolds an integrity test that still passes it.
- **Fix (pattern)**: run Gate 2 via an in-process DagBag inside the container (`DagBag(dag_folder=...)`, no kwargs) or patch `.astro/test_dag_integrity_default.py`. Do not treat the parse failure as a DAG error. validate_dag.py's TypeError fallback already handles the in-process path.
- **Origin**: test migration (`assets_dbt_python`), astro CLI 1.43.1, Runtime 3.3-1.
- **Version scope (testing, empirical)**: `astro dev parse` passes cleanly on Runtime 3.3-2 + CLI 1.43.1. The mechanism of the fix was NOT isolated (the CLI version is unchanged and Airflow 3.3 still lacks the kwarg, so presumably the 3.3-2 image or its scaffold handling changed); treat the scope as observed-not-explained, and re-test parse before assuming either behavior on a new Runtime.

## Gate 3 fails with "unexpected" edges on every unit that got a dag_id

- **Symptom**: after planning fills `dag_id` into scanner-produced units, Gate 3 reports the DAG's real task edges as `unexpected` and expects none (or expects scanner dicts like `upstream->io_manager`).
- **Class**: manifest field collision. `inventory.py` writes SOURCE dependency edges under `edges`; `validate_dag.py` reads the same key as expected TARGET task edges on any unit with a `dag_id`.
- **Fix (pattern)**: during Phase-2 enrichment, move scanner values to `source_edges` and write planned task edges under `edges` only on the one canonical unit per DAG. Long-term fix belongs in the scripts (rename one side).
- **Origin**: test migration (gauntlet), 24 spurious unit failures.

## Task crashes on manual runs: missing keyword-only argument 'logical_date'

- **Symptom**: `TypeError: <fn>() missing 1 required keyword-only argument: 'logical_date'` only on `airflow dags trigger` runs; scheduled runs fine.
- **Class**: Airflow 3 manual runs have `logical_date=None` and the sdk does not inject the context key. Hits the recommended translation of `@schedule`-computed run_config (tick-time date arithmetic in the task) and any tick-derived guard.
- **Fix (pattern)**: accept `dag_run` instead and derive `tick = dag_run.logical_date or dag_run.run_after`. Apply to every task doing tick arithmetic, not the one that failed.
- **Origin**: test migration (gauntlet), Runtime 3.3-2 (threshold DAG + am_on_cron guard).

## Backfill refused on DAGs with depends_on_past (self-dependency translation)

- **Symptom**: `airflow backfill create` exits with `InvalidReprocessBehavior: Dag has tasks for which depends_on_past=True...`.
- **Class**: CLI validation. Any Dagster self-dependency translated to `depends_on_past=True` (partitions.md recipe) hits it on the DAG's first backfill.
- **Fix (pattern)**: pass `--reprocess-behavior completed` (or `failed`) on every backfill of such DAGs; record it in the unit's runbook line. `--run-backwards` is unsupported for these DAGs.
- **Origin**: test migration (gauntlet), Airflow 3.3.

## Fresh-venv DagBag load fails: sqlite OperationalError "no such table: dag"

- **Symptom**: `validate_dag.py` (or any in-process `DagBag(dag_folder=...)`) in a clean venv/AIRFLOW_HOME dies with `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: dag` on Airflow 3.3.0.
- **Class**: environment, not DAG code. DagBag population on 3.3 touches the metadata DB even without `get_dag()`; a fresh AIRFLOW_HOME has no schema.
- **Fix (pattern)**: run `airflow db migrate` once in the AIRFLOW_HOME used for gates, before any DagBag-based gate. Containers built by `astro dev` already have a migrated DB; this bites only local-venv gate runs.
- **Origin**: test migration (dagster-open-platform), Airflow 3.3.0 / py3.12 venv.

## Migration input artifact ungenerable from the source repo (public mirror strips content)

- **Symptom**: a translation needs an artifact built FROM the source repo (dbt manifest, connector list, config file) and the repo cannot produce it — e.g. a public mirror strips `models/` so `dbt parse` fails in the SOURCE itself; or component discovery needs live-API credentials that don't exist at migration time.
- **Class**: blocked-at-source, pre-existing. Not a translation failure; never "fix" it by fabricating placeholder models, mocking discovery, or shipping a conditional factory that silently renders zero DAGs.
- **Fix (pattern)**: (a) baseline the source failure as Phase-0 evidence; (b) write the COMPLETE translation under a non-parsed directory (e.g. `deferred/<domain>/`) with an activation runbook in the file header (generate artifact in the real repo → move file into `dags/` → run gates); (c) defer the units with the baseline log as the reason; (d) for live-API discovery without creds, ship a PARTIAL static manifest derived from source config, flagged (`tables_complete: false`) plus a committed refresh script, and gate cutover on the first refresh+diff.
- **Origin**: test migration (dagster-open-platform): stripped dbt models/ (Cosmos blocked) and credential-less Fivetran discovery.

## DuckDB read_only connection refused inside `airflow dags test` (single-process runs)

- **Symptom**: a consumer task fails with `_duckdb.ConnectionException: Can't open a connection to same database file with a different configuration than existing connections` under `airflow dags test`, while the same DAG's writer tasks succeed; real executor runs may not hit it.
- **Class**: process-sharing artifact. `dags test` runs every task in ONE process; Cosmos LOCAL-mode dbt (dbt-duckdb) leaves a read-write DuckDB handle in that process, so a later task opening the same file with `read_only=True` is a config-mismatch, which DuckDB rejects per process. In production each task is its own process and the mismatch never materializes, so this bites exactly at Gate 4.
- **Fix (pattern)**: open every DuckDB connection in the shared `include/` IO helper with ONE config (plain `duckdb.connect(path)`, no `read_only`). Cross-process safety comes from the 1-slot pool (see single-writer entries above), not from read-only flags; do not scatter per-task connect calls with differing configs.
- **Origin**: test migration (`assets_dbt_python`), Runtime 3.3-2, forecast_daily order_forecast_model task.

## Gate 5 checksum mismatch from float summation order (aggregate models)

- **Symptom**: side-by-side/seeded parity shows a handful of tables "MISMATCH" under exact `EXCEPT` comparison while row counts match; diffs are ~1 ulp (e.g. 9.3e-10 on ~6.4e6 SUM() results); affected tables are exactly the ones with float aggregates over aggregates (SUM of SUMs, ratios of SUMs).
- **Class**: not a migration delta. Floating-point aggregation order differs between one `dbt build` process (Dagster) and per-model dbt invocations (Cosmos), and between parallel hash-aggregate schedules generally; associativity does not hold for float SUM.
- **Fix (pattern)**: compare float columns with a relative tolerance (rtol 1e-9 catches ulp noise, still fails real logic deltas by many orders of magnitude) and everything else exactly; record which tables passed exact vs tolerance in the parity evidence. Do not chase bit-exactness on float aggregates and do not widen tolerance beyond ~1e-6 without diagnosis.
- **Origin**: test migration (`assets_dbt_python`), company_perf/top_users, DuckDB 1.5.x both sides.

## macOS local-venv gates: fork-safety SIGABRT (empty import_error table)

- **Symptom**: on a macOS host venv, every DAG shows parse "# Errors 1" with an EMPTY import_error table; scheduler-launched tasks die with empty logs; processes abort with `objc +[NSNumber initialize] ... fork()`.
- **Class**: macOS Objective-C fork-safety killing the dag-processor's forked children and LocalExecutor workers.
- **Fix (pattern)**: `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` before any local-venv gate run. Container gates are unaffected.
- **Origin**: test migration (gauntlet), macOS host.

## Non-default API port: scheduler-run tasks fail `Not Found` with empty logs

- **Symptom**: CLI works (DB-backed) but every scheduler-launched task fails `ServerResponseError: Not Found`, task logs empty, `run_start_date=None`. May also appear to work on ports 8793/8794 (those are the component log servers, whose FastAPI even serves /openapi.json).
- **Class**: split config. Tasks talk to the Execution API at `AIRFLOW__CORE__EXECUTION_API_SERVER_URL` (default 8080), which does NOT follow `AIRFLOW__API__PORT`.
- **Fix (pattern)**: set `API__PORT`, `API__BASE_URL`, and `CORE__EXECUTION_API_SERVER_URL` together; never pick 8793/8794. Read "empty task log + Not Found in scheduler log" as this class.
- **Origin**: test migration (gauntlet), Airflow 3.3 standalone.

## Mapped-task collector: LazyXComSequence cannot be re-pushed to XCom

- **Symptom**: the downstream task aggregating a mapped fan-out (`DynamicOut.collect()` translation) dies with `TypeError: cannot serialize object of type BaseOperatorMeta` when it returns its input.
- **Class**: mapped results arrive as a lazy `LazyXComSequence`; returning or storing it re-pushes an unserializable proxy.
- **Fix (pattern)**: materialize before returning: `values = list(values)` at the top of any collector that returns or stores its input.
- **Origin**: test migration (gauntlet), Airflow 3.3.

## Backfill refused on PartitionedAssetTimetable consumers (non-periodic schedule)

- **Symptom**: `airflow backfill create` on an asset/partition-timetable consumer fails `DagNonPeriodicScheduleException: ... does not support backfills` (before depends_on_past is even considered; the existing --reprocess-behavior entry does not apply here).
- **Class**: backfills drive time-based schedules only; asset-triggered consumers have no periodic timetable.
- **Fix (pattern)**: backfill the PRODUCER while the consumer is UNPAUSED; the consumer fires once per upstream key (IdentityMapper), in order under depends_on_past. Verified testing.
- **Origin**: test migration (gauntlet).

## Backfill against a paused DAG queues runs that never execute

- **Symptom**: backfill runs sit `queued` forever, task instances state-NULL, zero warnings.
- **Class**: paused DAGs accept but never schedule backfill runs; classic cutover trap (backfilling history before flipping the DAG on).
- **Fix (pattern)**: unpause first, or check `is_paused` before `backfill create`. "Backfill runs queued + zero TIs started" reads as this class.
- **Origin**: test migration (gauntlet).


## Vendored dbt profiles invalid on modern dbt-snowflake ('schema' is a required property)

- **Symptom**: `dbt build` against the source project's own snowflake profile fails schema validation before connecting: `'schema' is a required property`.
- **Class**: dbt-snowflake tightened profile validation; older Dagster-era profiles omitted fields that defaulted implicitly.
- **Fix (pattern)**: generate a fresh profile for the migration (Cosmos ProfileConfig or a written profiles.yml) with database/schema/warehouse explicit, rather than reusing the vendored profile verbatim.
- **Origin**: test migration (project_fully_featured on real Snowflake), dbt-snowflake current.


## dlt filesystem destination fails on a pre-created dataset directory

- **Symptom**: the first dlt pipeline run in the migrated task fails with `FileExistsError` from the filesystem destination's makedirs.
- **Class**: dlt's filesystem destination creates its dataset directory without exist_ok; scaffolding that pre-creates the output tree (a natural Astro `include/` habit) breaks the first run.
- **Fix (pattern)**: do not pre-create dlt dataset directories; let dlt own its output tree. If scaffolding must exist, create only the parent.
- **Origin**: test migration (dbt_duckdb_demo_public), dlt filesystem destination.
