# Partitions and backfills

> **STATUS: reviewed; runtime-probed in testing** (key_format, single_run, backfill semantics).

Airflow 3.2 shipped native asset partitions (AIP-76), expanded in 3.3, so most Dagster partition patterns now translate natively instead of being redesigned onto logical dates. Version floors decide what you can use:

| Airflow version | Available |
|---|---|
| 3.2+ | `CronPartitionTimetable` (producer), `PartitionedAssetTimetable` (consumer), core mappers (`IdentityMapper`, `StartOf*Mapper`, `FixedKeyMapper`, `AllowedKeyMapper`, `ProductMapper`), `dag_run.partition_key`, partition-aware backfill |
| 3.3+ | Runtime emission `outlet_events[self].add_partitions(...)`, `RollupMapper`, `FanOutMapper`, windows (`HourWindow` ... `SegmentWindow`), wait policies (`WaitForAll`, `MinimumCount`) |

**Target Astro Runtime 3.3+.** Migrating to anything older than 3.2 means the logical-date fallback (last section), a much worse mapping.

## Producer side: time-window partitions

Dagster `HourlyPartitionsDefinition` / `DailyPartitionsDefinition` / etc. become `CronPartitionTimetable` on the producing asset:

```python
# Dagster
from dagster import HourlyPartitionsDefinition, asset
@asset(partitions_def=HourlyPartitionsDefinition(start_date=datetime(2020, 12, 1)))
def events(context):
    start, end = context.partition_time_window
    ...

# Airflow 3
from airflow.sdk import CronPartitionTimetable, asset
@asset(uri="s3://lake/events", schedule=CronPartitionTimetable("0 * * * *", timezone="UTC"))
def events(dag_run):
    key = dag_run.partition_key
    ...
```

Translation checklist per partitions definition (all fields are in the inventory):

- Cadence → cron string: daily `0 0 * * *`, hourly `0 * * * *`, weekly/monthly per `day_offset`. Dagster's `minute_offset`/`hour_offset`/`day_offset` shift the cron fields.
- Custom `TimeWindowPartitionsDefinition` sets `cron_schedule` and `fmt` INDEPENDENTLY and they can disagree (real example: daily cron with an hourly-looking `%Y-%m-%d-%H:%M` fmt). Take both from the definition; never infer the key format from the cadence.
- `timezone` carries over directly. `[JUDG]` if the Dagster def relied on the instance default.
- `start_date`: Airflow's DAG `start_date` bounds history for catchup/backfill.
- `end_date` / `end_offset` (partitions beyond "now"): no direct field; flag `[JUDG]`.
- `fmt` (the partition key format): see the key-format contract below. This is the field that silently breaks storage paths.

**The key-format contract.** Dagster default key formats: daily `%Y-%m-%d` (`2026-07-09`), hourly `%Y-%m-%d-%H:%M` (`2026-07-09-14:00`). Airflow's default is different (verified in testing): `dag_run.partition_key` is a plain string in `key_format`, default `%Y-%m-%dT%H:%M:%S`; pass `key_format=` on the timetable to control it. **Best practice (proven eval 3): set `key_format` to the SOURCE project's Dagster fmt**, so Airflow partition keys equal Dagster partition keys and every key-derived storage path round-trips as the identity: `CronPartitionTimetable("0 0 * * *", key_format="%Y-%m-%d")` made the parquet path recipe pass with zero conversion. Also probed: `partition_key` is **None under `dags test`**; the local way to run a concrete partition is `airflow backfill create --from-date D --to-date D` for that single day/window. Every piece of code that turns a key into a time window or storage path must go through one shared helper that parses the Airflow key and reformats where Dagster-era paths must be reproduced (recipe in `io-and-data-passing.md`). Unit-test it against real paths pulled from Dagster's materialization metadata.

**Per-edge window padding.** Producers commonly pad the derived window with business offsets before use, e.g. feeding dbt vars `min_date = start - 3h`, `max_date = end + 1d`. The padding lives in the producer's body, NOT in the partitions definition, so no key-derivation helper can recover it. Capture it during inventory (read the producer body) and reapply it explicitly in the translated task; assuming zero padding silently changes the data.

## Consumer side: partition mappings

**Rule (verified in testing): a partitioned producer forces the partition surface onto EVERY asset-scheduled consumer, partitioned-looking or not.** Partition-stamped asset events are dropped for non-partitioned consumers (silently: the consumer never fires), so any DAG scheduled on a partitioned asset must use `PartitionedAssetTimetable(assets=...)`, with a mapper choosing how keys map. Wait policies attach to the MAPPER (`RollupMapper(..., wait_policy=...)`), not the timetable. Version nuance: the drop behavior is the documented intent and holds on 3.3+; on Airflow 3.2.0 a bug (apache/airflow#63734) made such events WRONGLY fire non-partitioned consumers, the opposite failure. One more reason the 3.2 row in the version table above is a floor, not a recommendation.

Downstream consumers use `PartitionedAssetTimetable(assets=..., default_partition_mapper=...)`. Mapping Dagster's partition mappings:

| Dagster | Airflow 3 | Class | Notes |
|---|---|---|---|
| (default) same-partition dep, same cadence | `IdentityMapper` | MECH | |
| Hourly upstream → daily downstream (coarser) | `StartOfDayMapper` + `RollupMapper`/windows (3.3+) | JUDG | Verify aggregation semantics match the Dagster window before trusting |
| Daily upstream → hourly downstream (finer) | `FanOutMapper` (3.3+) | JUDG | |
| `TimeWindowPartitionMapping(start_offset=-1)` | Window with `Window.Direction.BACKWARD` / `SegmentWindow` | JUDG | Note the Dagster semantics: start_offset=-1 with end_offset=0 depends on the prior AND current windows (an expanded set), not a shifted single window. Offset arithmetic differs; test with a concrete date table |
| `TimeWindowPartitionMapping` on SELF (self-dependency) | `depends_on_past=True` on the task, plus explicit prev-window read | JUDG | Dagster's per-partition self-dep is stronger than depends_on_past (which is per-task-instance); document the delta |
| `AllPartitionMapping` (consume all partitions) | None: explicit full scan | NONE | The unbounded-rollup case; see `io-and-data-passing.md` |
| `LastPartitionMapping` | Read latest key explicitly in task logic | JUDG | |
| `StaticPartitionMapping` (explicit key→key dict) | `FixedKeyMapper` | JUDG | |
| `SpecificPartitionsPartitionMapping` | `AllowedKeyMapper` | JUDG | Spelling-level match; verify semantics |
| `MultiToSingleDimensionPartitionMapping`, `MultiPartitionMapping` [Beta] | Composition or redesign | REDESIGN | See multi-partitions below |

Wait policies: in Dagster, "wait for all upstream partitions" was never the partition mapping's job; it came from the automation condition (`~any_deps_missing()` inside eager) or a blocking check, and a manually triggered or non-eager downstream materializes with upstreams missing. So `WaitForAll` (the Airflow default) matches only when the Dagster side actually gated on all-present; check the asset's automation before assuming it. `MinimumCount(n)` has no Dagster analog (do not introduce it silently).

## Static partitions

`StaticPartitionsDefinition(["us", "eu", "apac"])` is usually not time at all; decide what it really is:

1. **Fan-out within a run** (all regions processed every run): dynamic task mapping, `process.expand(region=["us", "eu", "apac"])`. Simplest and usually right.
2. **Independently triggered/backfilled keys** (regions materialized separately, selectively): partitioned asset with fixed keys (`FixedKeyMapper`/`AllowedKeyMapper` on consumers) or one DAG per key when the list is tiny and stable.

The inventory should record how the Dagster project actually used it (were single-partition runs launched? per-key backfills?) and choose accordingly.

## Dynamic partitions

`DynamicPartitionsDefinition(name=...)` plus `AddDynamicPartitionsRequest` from a sensor translates to runtime partition emission (3.3+):

```python
@asset(uri="s3://lake/live", schedule=PartitionedAtRuntime())
def live(self, outlet_events):
    outlet_events[self].add_partitions(discovered_keys)
```

Caveats, both flagged in the map review:

- `PartitionedAtRuntime` is CONFIRMED importable from `airflow.sdk` on Runtime 3.3 (verified in testing)` but imports fine). `add_partitions` remains the doc-confirmed emission path.
- Retroactive-key semantics (Dagster lets a sensor add keys and separately request runs for them) are unverified on the Airflow side. If the Dagster project adds keys without immediately materializing them, flag for manual design.

The event-driven alternative often fits better: if dynamic partitions modeled "a new file/tenant arrived," an `AssetWatcher` on a queue, or an external `POST /api/v2/assets/events` with `partition_key`, is closer to intent than replicating the sensor.

## Multi-partitions

`MultiPartitionsDefinition({"date": daily, "region": static})` is REDESIGN. Options in preference order:

1. **Time partition on the DAG, dynamic task mapping over the static dimension.** Date stays a real partition (backfillable); regions become mapped tasks within each run. Covers the common date×category case well. Loses per-(date, region) selective materialization; say so in the report.
2. **`ProductMapper`** exists (3.2+) and may express two-dimensional consumption; semantics unverified against Dagster's `MultiPartitionKey`. Verify before use; do not emit blind.
3. **Key encoding** (`2026-07-09|eu` as a runtime-emitted key): preserves per-pair granularity, costs all native time-window tooling. Last resort.

## Backfills

| Dagster | Airflow 3 |
|---|---|
| Backfill selected asset partitions (UI/CLI) | `airflow backfill create --dag-id X --from-date A --to-date B` (also UI and REST); partition-aware since 3.2. from/to is the partition-date range, no off-by-one (verified in testing). DAGs with `depends_on_past=True` REFUSE backfills unless `--reprocess-behavior` is passed explicitly |
| Re-materialize only failed partitions | `--reprocess-behavior failed` (also `none`, `completed`) |
| `BackfillPolicy.single_run()` (one run spans the range) | None: no single-run backfill exists (verified in testing). Emit per-partition runs, or a manually triggered run with explicit range params whose task ignores `partition_key`; document the change |
| `BackfillPolicy.multi_run(max_partitions_per_run=n)` | Batching has no direct knob; `max_active_runs` bounds concurrency, not batch size. `[JUDG]` |
| Asset-selection backfill across the graph | Per-DAG backfills, ordered by dependency; no native graph-wide backfill. Document the operational difference |

Three rehearsal-verified realities (verified in testing), plus one from eval 5: unpausing a partition-timetable DAG fires the CURRENT partition immediately, so pause-and-clear that noise run (or accept it knowingly) before starting a historical backfill.

(1) `backfill create` on a PartitionedAssetTimetable CONSUMER is refused outright (`DagNonPeriodicScheduleException`); the recipe is to backfill the PRODUCER with the consumer UNPAUSED, and the consumer fires once per upstream key in order. (2) A backfill against a paused DAG queues runs that never execute, silently. Unpause first. (3) Under asset-triggered runs, `depends_on_past` enforces run-CREATION order, not partition order; if ordering by partition matters, verify the producer emits in order.

Idempotency is the prerequisite for any of this: partitioned producers must be safe to re-run per window (the delete-then-insert contract in `io-and-data-passing.md`). Verify with the double-run test before running a real backfill.

## Pre-3.2 fallback (logical dates)

If the target is stuck below 3.2: time partitions become `schedule` + `data_interval_start/end` with `catchup=True` for history; every other partition type degrades to params or mapped tasks; per-partition lineage and selective re-materialization are lost. This fallback is documented for completeness; prefer upgrading the target Runtime over using it.

## Validation

- Key-format round-trip: unit-test the shared key/window helper against real keys and paths from the Dagster instance.
- Partition-count parity: for a fixed window, the set of Airflow partition keys materialized must equal Dagster's partition set (compare against `dagster asset list`/materialization events before decommissioning).
- Mapper spot-check: for each consumer, pick one concrete key and assert the mapped upstream key set matches what Dagster's partition mapping produced for the same date.
- Idempotency double-run per partitioned producer.
