# Automation: schedules, sensors, declarative automation

> **STATUS: reviewed; hardened through testing** (catchup run-storm, on_cron inversion, eager OR/partitioned-guard, sensor partitioned-trap, logical_date fallback applied).

This is the semantic minefield of the migration: most automation constructs have an Airflow spelling that LOOKS equivalent and fires at different times. Every mapping here must produce an equivalence row in the migration report (rubric dimension 4): source trigger, target trigger, and the delta in one reviewable sentence.

## Cron schedules

`ScheduleDefinition(cron_schedule=..., execution_timezone=...)` → DAG `schedule` + timezone. Mechanical EXCEPT catchup:

| Source | `catchup` | Why |
|---|---|---|
| Non-partitioned Dagster schedule | `False` | Dagster never catches up missed ticks for plain schedules; Airflow 3's default (`False`) matches, but set it explicitly |
| Partitioned-job schedule (`build_schedule_from_partitioned_job`) | `True`, BUT check `start_date` first | Dagster fills missed partitions; without catchup the migrated DAG silently skips gaps. With an old `start_date` (e.g. 2020) `catchup=True` schedules every missed tick at unpause, a run storm in the tens of thousands. For old start dates: `catchup=False` + an explicit bounded backfill, documented in the equivalence row |

Getting this wrong produces either a burst of surprise historical runs or silently missing partitions. The equivalence row must state which behavior was preserved.

`@schedule` functions computing `RunRequest(run_config=...)` per tick: Airflow schedules cannot compute config. Translate to DAG `params` with defaults plus a leading task that computes and pushes the derived values (or templating when the computation is date arithmetic). Tag JUDG; diff the computed configs for a sample of ticks during validation. Date arithmetic in that leading task must use `dag_run.logical_date or dag_run.run_after`: `logical_date` is None on manually triggered runs (verified in testing), and a computed-config task that assumes it crashes exactly when a human triggers the DAG by hand.

Legacy spellings to normalize first: `@hourly_schedule`/`@daily_schedule`/etc. decorators, `schedule_definition` kwargs on old jobs.

## Declarative automation: decompose, then map

Real projects rarely use bare `eager()`. Decompose every `AutomationCondition` expression into operators and map each:

| Operator | Airflow target | Class |
|---|---|---|
| `cron_tick_passed(x) & ~in_progress()` (the dominant idiom in the wild) | Plain cron DAG + `max_active_runs=1` | MECH |
| `cron_tick_passed(x)` | Cron schedule | MECH |
| `on_cron(x)` on an asset with NO deps | Cron schedule (the dep-wait clause is vacuous) | MECH (check deps before routing on_cron to REDESIGN; the inversion below only bites when deps exist) |
| `~in_progress()` | `max_active_runs=1` | MECH |
| `any_deps_updated()` | Asset-aware schedule on deps | JUDG (success-only updates) |
| `missing()` / `newly_missing()` | First-run semantics; no repeated-trigger analog | JUDG (note: `on_missing()` does not exist; `newly_missing()` is the real operator) |
| `in_latest_time_window()` | Latest-window guard in task logic | JUDG |
| `code_version_changed()` | Cron + state-aware dbt builds (Fusion / dbt State): each run rebuilds only changed models, skipping the rest | JUDG (latency is cadence-bounded, not deploy-triggered; state-aware stack is beta-era, verify versions; see `dbt.md`) |
| `any_deps_match(...)`, `.allow()`, `.ignore()` | Per-dep scoping has no schedule analog | REDESIGN |
| `.since()`, `.newly_true()`, custom compositions | Manual review | REDESIGN |

Do NOT route an expression to REDESIGN before decomposing: `cron_tick_passed & ~in_progress` looks like a "complex composition" and is actually the easiest case in this file.

### `eager()`

`AutomationCondition.eager()` ≈ "materialize when any dep updates," and a bare asset-aware schedule approximates it while dropping four guarantees. Dagster's eager will NOT fire when:

1. any upstream partition is missing,
2. any upstream is currently in progress,
3. the asset itself is in progress,
4. outside the latest time window (partitioned assets).

A bare asset-aware schedule fires anyway. Recoverable pieces: (3) is `max_active_runs=1`; (2) can be approximated with a leading guard task that checks upstream DAG states.

Two splits matter for the default translation:

- **Multi-dep assets: use the OR composition `schedule=(a | b | ...)`, not the list form.** A bracketed list `schedule=[a, b]` means ALL-updated (AND) and under-fires relative to eager, which triggers on ANY newly updated dep. Reserve the list form for assets whose automation genuinely required all deps; state the AND/OR choice in the equivalence row. One measured delta (verified in testing): `AssetAny` fires once PER EVENT, so an upstream that materializes twice in quick succession triggers two downstream runs, where a coalescing cursor sensor or eager's since-last-handled would fire once. `max_active_runs=1` bounds the concurrency but not the run count; note it in the row.
- **Partitioned eager assets: guarantee (4) is load-bearing, keep it.** Without the latest-time-window restriction, every upstream update re-materializes old partitions (a behavior change and a cost blowup, and partitioned-eager is a common real-world pattern). Add a latest-window guard in the task or scope the trigger to the latest partition. For non-partitioned assets, (1) and (4) are generally not worth simulating.

Default translation: OR-composed asset schedule + `max_active_runs=1` (+ latest-window guard when partitioned), with the remaining deltas stated in the equivalence row.

### `on_cron()`: inverted, do not map naively

`on_cron(cron)` = after the cron tick, wait until ALL deps have updated since that tick, then run once (AND, time-gates-data). `AssetOrTimeSchedule` = run on the tick OR on any asset update (OR). A naive swap fires early and often. Options, in preference order:

1. **Cron DAG + leading dep-freshness guard**: schedule on the cron; first task checks (via `inlet_events` timestamps or `GET /api/v2/assets/events`) that every upstream updated since the previous tick, and defers/retries until true (deferrable sensor with timeout). Closest semantics; costs a guard task per DAG.
2. **`PartitionedAssetTimetable` with a mapper carrying `wait_policy=WaitForAll`** (wait policies attach to the MAPPER, e.g. `RollupMapper(..., wait_policy=WaitForAll())`, not the timetable) when both sides are time-partitioned on compatible cadences: the wait policy IS the all-deps gate. Cleanest when it applies.
3. **Accept `AssetOrTimeSchedule` with a documented delta** when the deps update reliably more often than the cron anyway and early fires are harmless. The report must say the AND became an OR.

## Sensors

Classify by SEMANTICS, not decorator. Scanner heuristic from real projects: a plain `@sensor` whose body fetches materialization events for multiple assets and combines them through a cursor is a hand-rolled multi-asset sensor; translate it as a boolean asset schedule (MECH), not as generic-sensor REDESIGN. Second heuristic: a `@sensor` that gates purely on wall-clock (checks the day/hour and fires) is a schedule wearing a sensor decorator; translate it as a cron DAG (MECH).

**CRITICAL partitioned-upstream trap (verified in testing):** when ANY upstream asset is partitioned, a plain boolean asset schedule (`schedule=[a, b]` or `(a & b)`) on a non-partition-aware consumer NEVER triggers: Airflow 3.3's asset manager drops partition-stamped events for non-partitioned consumers, with no error anywhere. The correct translation is `PartitionedAssetTimetable(assets=(a & b), ...)` even when the consumer itself looks unpartitioned. Check the upstreams' partitioning BEFORE choosing the schedule form, and behaviorally verify the trigger (see `validation.md` Gate 4).

| Pattern | Target | Class |
|---|---|---|
| Fires on materialization(s), no other logic | Boolean asset schedule (`schedule=[a]`, `(a & b)`, `(a \| b)`); partitioned upstream → `PartitionedAssetTimetable` (see trap above) | MECH |
| Polls an external condition (file, API, queue) | Deferrable sensor / `@task.sensor(poke_interval=, timeout=, mode="reschedule")` returning `PokeReturnValue`; or `AssetWatcher` + `MessageQueueTrigger` when the source is one of the six supported queues | JUDG |
| Cursor state | Airflow `Variable` (or XCom within one DAG); document that Dagster's per-evaluation cursor transactionality is lost | JUDG |
| Metadata filtering, computed `run_config`, cross-job triggering | Asset schedule + guard/config task, or full redesign | REDESIGN |
| `@run_status_sensor` / `@run_failure_sensor` | DAG/task callbacks for in-code reactions; Astro alerts for notifications (no DAG code needed) | JUDG |
| `AddDynamicPartitionsRequest` from a sensor | Runtime partition emission or external asset events; see `partitions.md` | JUDG |

Queue-backed sensors deserve special attention: if the Dagster sensor polls SQS/Kafka/Pub/Sub/Service Bus/IBM MQ/Redis, the Airflow version is BETTER than the original (event-driven `AssetWatcher`, no poll loop). Flag these as upgrade opportunities, not just translations.

## Freshness

Two Dagster APIs share one class name; disambiguate by call form before mapping:

- `FreshnessPolicy.time_window(fail_window=, warn_window=)` / `.cron(...)` (classmethods): the current policy API.
- `FreshnessPolicy(maximum_lag_minutes=...)` OR `FreshnessPolicy(cron_schedule=...)` (plain kwargs on the class, not classmethods) = `LegacyFreshnessPolicy` semantics. Both legacy signals matter; keying only on `maximum_lag_minutes` misclassifies legacy cron-form policies.
- Builder trio `build_last_update_freshness_checks` / `build_time_partition_freshness_checks` / `build_sensor_for_freshness_checks`: superseded but common.

ALL of them route to the observability layer: Astro **DAG Timeliness** alerts (UI-configured, no DAG code) and/or `DeadlineAlert` (3.1+, experimental; `DAGRUN_QUEUED_AT`, `AVERAGE_RUNTIME`, `FIXED_DATETIME` references). **Never translate freshness to a downstream check task**: it would be gated on the asset's success and cannot fire in exactly the stale/failed case freshness exists to catch. Two deltas to document: Dagster freshness is asset-scoped while deadline alerts are DAG-run-scoped (per-asset freshness on a multi-asset DAG needs per-asset alerts or DAG splitting), and warn/fail dual thresholds map to two alerts or one alert plus duration.

Legacy `AutoMaterializePolicy.eager()/.lazy()` and `auto_materialize_policy=`: normalize to the equivalent `AutomationCondition` first (eager → eager; lazy → freshness-driven, route to observability), then map with this file.

## Operational: unpausing fires immediately

Unpausing a migrated DAG is not neutral (verified in testing): a cron DAG runs its last missed tick, and a partition-timetable DAG runs the CURRENT partition, the moment it is unpaused. For cron DAGs the immediate run is usually the run you wanted. For partitioned domains it is usually NOT: the current partition is the in-progress window, so the first post-flip run materializes PARTIAL data on a live project (rehearsal finding). Time the flip just after a window closes, or pause-and-clear the first run and backfill the last completed window instead. The cutover checklist in `astro-deployment.md` carries the full flip order.

## Validation

- Every trigger gets an equivalence row: source spelling, target spelling, delta sentence. Zero undocumented deltas is the rubric gate.
- Simulate a week: for cron schedules, enumerate tick times in both systems (respecting timezone + catchup) and diff. For asset-driven triggers, replay a recorded day of Dagster materialization events and check which DAGs would have fired.
- For on_cron translation option 1, test the guard's timeout path: what happens when a dep never updates (Dagster: silently waits; the guard must fail loudly or skip cleanly per the report's stated choice).
