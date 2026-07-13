# IO managers and data passing

> **STATUS: reviewed; hardened through testing** (predicate-lift, key_format identity, and single-writer findings applied).

The central hard problem of this migration direction. Dagster IO managers persist every asset/op output implicitly and load every input on demand; Airflow tasks share nothing unless code makes them. Dagster's own retired compiler (`dagster-airflow` 0.x) hit exactly this wall: it required configured shared storage for every intermediate value. There is no general translation. Instead, make an explicit decision **per edge** (producer output → consumer input), using the tree below.

## The per-edge decision tree

For every edge in the inventory, in order:

1. **Fuse producer and consumer into one task** when the intermediate is pipeline-internal: nobody materializes it independently, no other consumer exists, no operational value in observing it. Fusing eliminates the handoff entirely. Do NOT fuse when the upstream is independently scheduled, has multiple consumers, is a real dataset someone queries, or carries its own checks/metadata; collapsing an independently-materializable chain loses per-asset observability.
2. **Explicit storage read/write** for everything that is a real asset (the default). The producer task writes to the same storage the IO manager used; every consumer reads from it. Keep the storage layout the Dagster project already uses, at least through cutover, so side-by-side parity comparison stays trivial.
3. **XCom** only for small control values (ids, counts, paths, flags) via TaskFlow returns. For medium payloads, configure the object-storage XCom backend and let it spill by size:

```ini
[core]
xcom_backend = airflow.providers.common.io.xcom.backend.XComObjectStorageBackend

[common.io]
xcom_objectstorage_path = s3://conn_id@mybucket/xcom
xcom_objectstorage_threshold = 1048576
xcom_objectstorage_compression = gzip
```

Never pass dataframes or models through default XCom (metadata DB).

## Inventory: what to collect per edge

The scanner emits one record per edge: producer asset/op key, consumer key, `io_manager_key` (remember the implicit default is `fs_io_manager`), the Python type annotation of the output and of each consumer's input (they can differ, see heterogeneous inputs), any `AssetIn(metadata=...)` directives, partitioning of both sides, and whether producer/consumer land in the same generated DAG. Same-DAG edges may still need storage (parallel branches on separate workers); cross-DAG edges always do.

## Recipes by IO manager class

### Pickle IO managers (fs / S3 / GCS / ADLS2)

Write a small helper in `include/io_helpers.py` exposing `write_pickle(key, obj)` / `read_pickle(key)` against the same bucket/prefix the IO manager used. Producer calls write at the end; consumers call read at the start. This is also the answer for **opaque Python objects** (sklearn models, scipy matrices, custom dataclasses): they stay pickles in object storage; XCom is not an option and fusing away an independently-materialized model asset is usually wrong.

### Partitioned file IO managers: the path round-trip rule

Real IO managers encode the partition **window** into the storage key. From a real project (`project_fully_featured/resources/parquet_io_manager.py`):

```
{prefix}/{asset_key}/{start:%Y%m%d%H%M%S}_{end:%Y%m%d%H%M%S}.pq
```

In Airflow the producer gets `dag_run.partition_key` (a single string), and a different consumer DAG gets a mapped key. Both must reconstruct the **identical** `(start, end)` window to hit the same file.

**Rule: one shared derivation function, used by every producer and every consumer of that asset.**

```python
# include/partition_paths.py
# THE strategy (proven testing, and what partitions.md prescribes): pass this same
# string as key_format= on the producing timetable, so Airflow keys are byte-identical
# to Dagster keys and paths round-trip as the identity. Only if you cannot override
# key_format does conversion apply (Airflow's default is "%Y-%m-%dT%H:%M:%S").
KEY_FMT = "%Y-%m-%d-%H:%M"   # = the SOURCE project's Dagster fmt (hourly default shown)

def hourly_window(partition_key: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(partition_key, KEY_FMT)
    return start, start + timedelta(hours=1)

def parquet_path(prefix: str, asset_key: str, partition_key: str) -> str:
    # reproduces the Dagster-era path exactly
    start, end = hourly_window(partition_key)
    return f"{prefix}/{asset_key}/{start:%Y%m%d%H%M%S}_{end:%Y%m%d%H%M%S}.pq"
```

Never inline the format string in a task body; a drifted copy produces silent misses (consumer reads nothing, no error). During side-by-side, assert the Airflow-derived path equals the path Dagster actually wrote.

### Warehouse IO managers (Snowflake / BigQuery / DuckDB)

**Non-partitioned**: this case genuinely simplifies. The table was always the real interface; producer runs its SQL/writes via the provider hook, consumers SELECT. Delete the abstraction happily.

**Partitioned**: the IO manager was silently providing an idempotency contract. From a real project (`snowflake_io_manager.py`): on write, DELETE rows in the partition's time window, then append; on read, apply the same window WHERE clause. Reimplement BOTH sides or backfills stop being idempotent:

- Producer: **lift the ORIGINAL delete predicate verbatim; do not re-derive a canonical one.** Real IO managers vary in operator inclusivity and column transforms: a real project uses `WHERE TO_TIMESTAMP(time::INT) BETWEEN '{start}' AND '{end}'`, a CLOSED interval over an epoch-int column. Rewriting that as `time >= :start AND time < :end` changes boundary rows at every partition edge (parity mismatch) and type-errors on the epoch column. Then insert. Wrapping delete+insert in one transaction where the warehouse allows is an improvement, not parity: Dagster issued them as separate statements with no atomicity guarantee.
- Consumer (partitioned): apply the same original predicate, window derived from the shared helper above.
- Checklist per table: what is the original predicate (column expression including transforms like `TO_TIMESTAMP(x::INT)`, closed vs half-open interval)? Does a suitable time column exist (the Dagster manager assumed one)? Are delete and read windows derived from the same function? Is a failed run safe to retry (delete-then-insert makes it so)?

Two warehouse-proven amendments (verified in testing):

- **Verbatim lifting preserves BUGS too.** A CLOSED interval (`BETWEEN`) is not partition-disjoint: the boundary row belongs to two windows, and re-running a partition after its neighbor silently DELETES the shared boundary row, identically on both the original Dagster manager and the faithful port (measured: 1689 -> 1688, both sides, degraded checksums equal). Surface this as a SOURCE defect in the migration report; rewriting to half-open (`>= start AND < end`) is the fix but is a deliberate behavior change, decided and documented, never silent.
- **Bootstrap: the recipe cannot cold-start.** The first-ever materialization fails on the DELETE (`Object does not exist`); the original Dagster manager shares this flaw (it never ran against an empty schema). The port needs `CREATE TABLE IF NOT EXISTS` (or tolerate object-not-found on DELETE) before the first write.
- **Session parameters change the predicate's meaning.** Under `TIMESTAMP_TYPE_MAPPING=TIMESTAMP_LTZ` with a non-UTC session, the same `TO_TIMESTAMP(...) BETWEEN` matches ZERO rows. Pin `session_parameters` (timezone, timestamp mapping) on the Airflow Connection to match what Dagster's connection used; see `astro-deployment.md`.

**Column-projection metadata** (`AssetIn(metadata={"columns": [...]})`) becomes an explicit column list in the consumer's SELECT. It was never magic; it compiled to SQL anyway.

### Env-swapped IO managers (local dev parity)

Real-world pattern (`project_fully_featured/definitions.py`): the same asset code runs against DuckDB locally and Snowflake in prod because `DAGSTER_DEPLOYMENT` selects the IO manager. Inlining Snowflake SQL into task bodies destroys local dev. Preserve the indirection with a deployment-aware helper:

```python
# include/warehouse.py
def warehouse_hook():
    if os.environ.get("DEPLOYMENT", "local") == "local":
        return DuckDBHook(...)          # local astro dev
    return SnowflakeHook(snowflake_conn_id="warehouse")
```

and keep task bodies engine-neutral (or accept the loss explicitly in the migration report; never lose it silently). Airflow Connections per Astro Deployment carry the env-specific credentials.

### Heterogeneous inputs

One consumer may read N inputs from N different storage systems with different in-memory types; real projects have a single function reading two S3 pickles plus a column-projected Snowflake table, and assets written as pandas but read as Spark by a different consumer. There is no single "load inputs" translation: each input gets its own explicit read, and cross-engine edges (pandas out, Spark in) need an explicit conversion choice (read the parquet with Spark directly; don't round-trip through pandas).

### Unbounded rollups

A non-partitioned downstream of a partitioned upstream consumes **all partitions to date** (one real project's DuckDB manager only permits exactly this). No native Airflow mapper expresses it; windows and `RollupMapper` are bounded. Translate it as an explicit full scan (`SELECT ... FROM t` / glob over the asset's whole prefix) and document that its cost grows with history.

## Single-writer stores under Airflow parallelism

Dagster's default in-process execution serialized writes that Airflow's parallel tasks will not (verified in testing). DuckDB in particular is a single-writer store: two concurrent tasks writing the same file lock-conflict or corrupt. When the migrated DAG fans out writers to a single-writer store, either serialize them (an Airflow Pool with 1 slot on the writing tasks), write per-task outputs and consolidate in a downstream task, or move the store to a concurrent-writer backend as a documented change. Silent reliance on "it worked in Dagster" is exactly the class of parity failure that only appears under load.

## Validation

- Parity: run the same logical window through Dagster and the migrated DAGs; compare row counts + checksums per output table/file (rubric dimension 5).
- Path drift: unit-test the shared derivation helpers against paths Dagster actually produced (pull real examples from the Dagster instance's materialization metadata before decommissioning it).
- Idempotency: re-run a migrated partitioned producer for the same window twice; row counts must not grow.
