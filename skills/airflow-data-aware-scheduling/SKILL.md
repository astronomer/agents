---
name: airflow-data-aware-scheduling
description: Implements asset-based data-aware scheduling in Apache Airflow 3.x. Use when the user wants to trigger Dags based on data updates, declare data-driven dependencies between Dags, use asset outlets/inlets, use the @asset decorator, schedule on asset events, combine asset and time-based schedules, pass metadata via asset event extras, use asset aliases, set up event-driven scheduling with message queues, partition Dag runs, use partition key mappers, create asset listeners, query the asset REST API, or debug queued asset events. Covers Assets, asset events, AssetAlias, AssetWatcher, AssetOrTimeSchedule, CronPartitionTimetable, PartitionedAssetTimetable, and partition key mappers.
---

# Asset-Based Data-Aware Scheduling in Apache Airflow

Assets let Dags declare explicit dependencies on data and schedule runs based on data updates rather than time. An asset can represent anything, concrete data entities like a table in a database, or abstract concepts like a business process having been completed. A task declares its successful completion produces asset events to an asset (via `outlets`), and downstream Dags can be scheduled based on one or a combination of asset events.

> **Airflow version**: This skill covers Airflow 3.x. **NEVER use `from airflow.datasets import Dataset`** — always use `from airflow.sdk import Asset`.
>
> **Airflow is not a data monitor**: Airflow assets only detect updates through task completions (outlets), API calls, or UI actions. Assets do **not** detect changes in an external data tool made from outside Airflow. To react to external events, use [event-driven scheduling](#event-driven-scheduling) with AssetWatchers to schedule Dags based on messages in a message queue, or [sensors and deferrable operators](#when-not-to-use-assets) to schedule Dags based on any other condition being true in an external system, for example a file being uploaded to a blob storage or an HTTPS request returning a specified status code.
>
> **Partitioned assets** (`CronPartitionTimetable`, `PartitionedAssetTimetable`) require **Airflow 3.2+**.

---

## When to use what

| User needs to... | Go to section |
|---|---|
| Declare that a task produces or reads a data entity | [Assets, outlets, and inlets](#assets-outlets-and-inlets) |
| Create a simple one-task-one-asset Dag | [`@asset` decorator](#asset-decorator) |
| Trigger a Dag when upstream data is updated | [Asset schedules](#asset-schedules) |
| Use OR/AND logic across multiple assets | [Conditional asset scheduling](#conditional-asset-scheduling) |
| Run a Dag on both a cron schedule and asset updates | [Combined asset and time-based scheduling](#combined-asset-and-time-based-scheduling) |
| Pass metadata between producer and consumer tasks | [Asset event extras](#asset-event-extras) |
| Determine asset names at runtime (including when using dynamic tasks) | [Asset aliases](#asset-aliases) |
| Trigger a Dag based on messages in a message queue | [Event-driven scheduling](#event-driven-scheduling) |
| Partition data processing by time period or segment | [Partitioned Dag runs and asset events](#partitioned-dag-runs-and-asset-events-airflow-32) |
| Normalize or transform partition keys | [Partition key mappers](#partition-key-mappers-airflow-32) |
| Run code whenever any asset event occurs globally | [Asset listeners](#asset-listeners) |
| Debug why a multi-asset Dag hasn't triggered yet | [Queued asset events](#queued-asset-events) |
| Create asset events or query assets via API | [REST API endpoints](#rest-api-endpoints) |

### When NOT to use assets

Assets do not monitor external systems directly. If you need to react to a condition in an external system that isn't published to a message queue, use:

- **[Sensors](https://www.astronomer.io/docs/learn/what-is-a-sensor)**: Synchronously poll for a condition.
- **[Deferrable operators](https://www.astronomer.io/docs/learn/deferrable-operators)**: Asynchronously wait, releasing the worker slot.

If the external event *is* published to a message queue (SQS, Kafka, Pub/Sub, etc.), use [event-driven scheduling](#event-driven-scheduling).

---

## Quick import reference

```python
# Core — all Airflow 3.x versions
from airflow.sdk import Asset, AssetAlias, Metadata, dag, task

# Combined asset + time scheduling
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

# Partitioned scheduling (Airflow 3.2+)
from airflow.sdk import CronPartitionTimetable, PartitionedAssetTimetable

# Partition key mappers (Airflow 3.2+)
from airflow.sdk import (
    IdentityMapper,
    ToHourlyMapper,
    ToDailyMapper,
    ToWeeklyMapper,
    ToMonthlyMapper,
    ToQuarterlyMapper,
    ToYearlyMapper,
    ProductMapper,
    AllowedKeyMapper,
)
```

---

## Assets, outlets, and inlets

An asset is identified by a unique **name** string. Optionally attach a URI for a concrete data entity. An asset is registered as soon as it appears in `outlets`, `inlets`, or `schedule`.

### Outlets — declaring a producer task

Any task with `outlets` becomes a **producer task**. On successful completion it creates an **asset event** for each listed asset.

```python
from airflow.sdk import Asset, dag, task
from airflow.providers.standard.operators.bash import BashOperator

@dag
def my_producer_dag():

    @task(outlets=[Asset("my_asset")])
    def produce_data():
        pass

    produce_data()

    BashOperator(
        task_id="produce_bash",
        bash_command="echo 'done'",
        outlets=[Asset("my_asset_bash")],
    )

my_producer_dag()
```

A task can produce to multiple assets: `outlets=[Asset("a"), Asset("b")]`.

### Inlets — reading asset event information

`inlets` give a task access to asset events. Defining inlets does **not** affect the Dag's schedule.

```python
@task(inlets=[Asset("my_asset")])
def read_asset_info(inlet_events):
    asset_events = inlet_events[Asset("my_asset")]
    if asset_events:
        print(asset_events[-1].extra)

read_asset_info()
```

### `@asset` decorator

Creates a Dag with a single task that updates an asset of the same name:

```python
from airflow.sdk import asset

@asset(schedule="@daily")
def my_asset():
    pass
```

Chain `@asset` Dags by scheduling one on another:

```python
from airflow.sdk import asset

@asset(schedule="@daily")
def extracted_data():
    return {"a": 1, "b": 2}

@asset(schedule=extracted_data)
def transformed_data(context):
    data = context["ti"].xcom_pull(
        dag_id="extracted_data",
        task_ids="extracted_data",
        key="return_value",
        include_prior_dates=True,
    )
    return {k: v * 2 for k, v in data.items()}
```

Use `@asset.multi` to update several assets from one Dag:

```python
from airflow.sdk import Asset, asset

@asset.multi(schedule="@daily", outlets=[Asset("asset_a"), Asset("asset_b")])
def my_multi_asset():
    pass
```

---

## Asset schedules

### Basic asset schedule

One asset — triggers on every update:

```python
from airflow.sdk import Asset, dag

@dag(schedule=[Asset("my_asset")])
def my_consumer_dag():
    ...

my_consumer_dag()
```

Multiple assets in a **[]** list — triggers when **all** have received at least one update each (then resets). To create more complex asset-scheduling logic including OR/AND see [Conditional asset scheduling](#conditional-asset-scheduling).

```python
@dag(schedule=[Asset("asset_a"), Asset("asset_b")])
def needs_both():
    ...

needs_both()
```

### Key scheduling rules

| Rule | Detail |
|------|--------|
| Paused Dags ignore updates | Asset events only count while unpaused. Unpausing starts with a blank slate. |
| Each producer completion triggers | If `task1` and `task2` both produce `asset_a`, the consumer runs twice. |
| First outlet wins | Consumer triggers as soon as the first task with the outlet finishes. |
| Events coalesce for multi-asset schedules | If `a` updates 5 times before `b` updates once, the consumer runs **once** when `b` fires. |
| Only successful tasks emit events | Skipped or failed tasks do **not** create asset events. |
| No data interval | Asset-triggered runs have no data interval. Use the partition_key passed by partitioned asset schedules for time-based segmentation. |

### Queued asset events

When a Dag is scheduled on multiple assets, events that arrive before the full condition is met are **queued**. Once all required assets have at least one event, the Dag run triggers and the queue resets.

Inspect queued events via the Airflow UI (click the Dag's schedule) or the REST API:

- `GET /api/v2/dags/{dag_id}/assets/queuedEvents` — all queued events for a Dag
- `GET /api/v2/dags/{dag_id}/assets/{asset_id}/queuedEvents` — queued events for a specific asset/Dag pair
- `GET /api/v2/assets/{asset_id}/queuedEvents` — all queued events for an asset across all Dags
- `DELETE` variants of the above to clear queued events

---

## Conditional asset scheduling

Use `|` (OR) and `&` (AND) operators inside **`()`** (not `[]`) for complex expressions:

```python
from airflow.sdk import Asset, dag

@dag(
    schedule=(
        Asset("raw_orders") | Asset("raw_returns")
    ),
)
def run_on_either():
    ...

run_on_either()


@dag(
    schedule=(
        (Asset("raw_orders") | Asset("raw_returns"))
        & (Asset("dim_customers") | Asset("dim_products"))
    ),
)
def run_on_one_from_each_group():
    ...

run_on_one_from_each_group()
```

> **`()` not `[]`**: Square brackets `[]` mean "all must update" (AND-only). Parentheses let you use `|` and `&`.

---

## Combined asset and time-based scheduling

Use `AssetOrTimeSchedule` to run a Dag on **either** a cron schedule **or** asset updates:

```python
from airflow.sdk import Asset, dag
from pendulum import datetime
from airflow.timetables.assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable

@dag(
    start_date=datetime(2025, 3, 1),
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 0 * * *", timezone="UTC"),
        assets=(Asset("my_asset_a") | Asset("my_asset_b")),
    ),
)
def runs_daily_or_on_asset_update():
    ...

runs_daily_or_on_asset_update()
```

---

## Asset event extras

### Attach extra information (producer side)

**Option A — `Metadata` class** (use `yield`):

```python
from airflow.sdk import Asset, Metadata, task

my_asset = Asset("my_asset")

@task(outlets=[my_asset])
def produce_with_extras():
    row_count = 42
    yield Metadata(my_asset, {"row_count": row_count})
    return "done"

produce_with_extras()
```

**Option B — `outlet_events` from context**:

```python
from airflow.sdk import Asset, task

my_asset = Asset("my_asset")

@task(outlets=[my_asset])
def produce_with_context(outlet_events):
    outlet_events[my_asset].extra = {"row_count": 42}
    return "done"

produce_with_context()
```

Both approaches require the asset to be in the task's `outlets`.

### Retrieve extra information (consumer side)

**From triggering events** (only in asset-triggered Dag runs):

```python
from airflow.sdk import task

@task
def consume_triggering(triggering_asset_events):
    for asset, event_list in triggering_asset_events.items():
        print(event_list[0].extra)
        print(event_list[0].source_run_id)

consume_triggering()
```

**From inlets** (works in any Dag run type, inlets do not affect the Dag's schedule):

```python
from airflow.sdk import Asset, task

my_asset = Asset("my_asset")

@task(inlets=[my_asset])
def consume_via_inlet(inlet_events):
    events = inlet_events[my_asset]
    if events:
        print(events[-1].extra)

consume_via_inlet()
```

---

## Asset aliases

Use `AssetAlias` when the asset name is determined at runtime (e.g., dynamic task mapping, variable bucket names).

### Producing to an alias

**With `Metadata`**:

```python
from airflow.sdk import Asset, AssetAlias, Metadata, task

my_alias = AssetAlias("my_alias")

@task(outlets=[my_alias])
def dynamic_produce():
    bucket = "my-bucket"
    yield Metadata(
        asset=Asset(f"updated_{bucket}"),
        extra={"k": "v"},
        alias=my_alias,
    )

dynamic_produce()
```

**With `outlet_events`**:

```python
from airflow.sdk import Asset, AssetAlias, task

my_alias = AssetAlias("my_alias")

@task(outlets=[my_alias])
def dynamic_produce_context(outlet_events):
    bucket = "other-bucket"
    outlet_events[my_alias].add(Asset(f"updated_{bucket}"), extra={"k": "v"})

dynamic_produce_context()
```

### Consuming from an alias

```python
from airflow.sdk import AssetAlias, dag

@dag(schedule=[AssetAlias("my_alias")])
def alias_consumer():
    ...

alias_consumer()
```

Once a producer attaches an asset to the alias, any future update to that asset (from any source) also triggers Dags scheduled on the alias.

### Aliases with traditional operators

Use the `post_execute` parameter (experimental) to attach events:

```python
from airflow.sdk import Asset, AssetAlias
from airflow.providers.standard.operators.bash import BashOperator

my_alias = AssetAlias("my_alias")

def _attach(context, result):
    context["outlet_events"][my_alias].add(Asset("s3://bucket/file.txt"))

BashOperator(
    task_id="produce",
    bash_command="echo hi",
    outlets=[my_alias],
    post_execute=_attach,
)
```

---

## Event-driven scheduling

Event-driven scheduling triggers a Dag from messages in an external message queue. An `AssetWatcher` polls a `MessageQueueTrigger`; when a message arrives, it creates an asset event with the message payload in `extra`.

### Pattern

```python
from airflow.providers.common.messaging.triggers.msg_queue import MessageQueueTrigger
from airflow.sdk import Asset, AssetWatcher, dag, task

trigger = MessageQueueTrigger(
    aws_conn_id="aws_default",
    queue="https://sqs.<region>.amazonaws.com/<account>/<queue>",
    waiter_delay=30,
)

sqs_asset = Asset(
    "sqs_queue_asset",
    watchers=[AssetWatcher(name="sqs_watcher", trigger=trigger)],
)


@dag(schedule=[sqs_asset])
def event_driven_dag():

    @task
    def process_message(triggering_asset_events):
        for event in triggering_asset_events[sqs_asset]:
            print(event.extra["payload"]["message_batch"][0]["Body"])

    process_message()


event_driven_dag()
```

### Supported message queue providers

| Provider | Package | Minimum version |
|----------|---------|-----------------|
| Amazon SQS | `apache-airflow-providers-amazon` | `>=9.7.0` |
| Apache Kafka | `apache-airflow-providers-apache-kafka` | `>=1.9.0` |
| Google Pub/Sub | `apache-airflow-providers-google` | `>=19.5.0` |
| Azure Service Bus | `apache-airflow-providers-microsoft-azure` | `>=12.9.0` |
| Redis Pub/Sub | `apache-airflow-providers-redis` | `>=4.3.0` |

All providers also require `apache-airflow-providers-common-messaging>=1.0.2`.

For Kafka, `MessageQueueTrigger` accepts an `apply_function` parameter (a dotted Python path to a callable in your project's `include/` folder) that transforms the raw message before it reaches the asset event.

You can create custom triggers for unsupported message queues by inheriting from `BaseEventTrigger`.

---

## Partitioned Dag runs and asset events (Airflow 3.2+)

Partitioned runs attach a `partition_key` string to Dag runs and asset events, enabling time- or segment-based data processing.

### CronPartitionTimetable — producing partitioned events

Creates scheduled runs with an automatic `partition_key` based on the `run_after` timestamp:

```python
from airflow.sdk import dag, task, Asset, CronPartitionTimetable

my_asset = Asset("partitioned_asset")

@dag(schedule=CronPartitionTimetable("0 0 * * *", timezone="UTC"))
def daily_producer():

    @task(outlets=[my_asset])
    def extract(**context):
        pk = context["dag_run"].partition_key
        print(f"Processing partition: {pk}")

    extract()

daily_producer()
```

Only **scheduled** and **backfill** runs get automatic partition keys. Manual runs do not, unless you provide one in the trigger config or API request.

Use `run_offset` to shift the partition key relative to the cron expression:

```python
CronPartitionTimetable("0 * * * *", timezone="UTC", run_offset=-12)
```

> **Important**: Partitioned asset events do **not** trigger non-partition-aware Dags. They only trigger Dags using `PartitionedAssetTimetable`.

### PartitionedAssetTimetable — consuming partitioned events

```python
from airflow.sdk import dag, task, PartitionedAssetTimetable, Asset

@dag(schedule=PartitionedAssetTimetable(assets=Asset("partitioned_asset")))
def partitioned_consumer():

    @task
    def process(**context):
        print(context["dag_run"].partition_key)

    process()

partitioned_consumer()
```

This Dag only runs on **partitioned** asset events — regular asset events are ignored.

### Combined partitioned asset schedules

Combine multiple assets with `&` and `|`:

```python
from airflow.sdk import dag, PartitionedAssetTimetable, Asset

asset_a = Asset("orders")
asset_b = Asset("returns")

@dag(schedule=PartitionedAssetTimetable(assets=(asset_a & asset_b)))
def needs_both_partitioned():
    ...

needs_both_partitioned()
```

Triggers only when both assets receive partitioned events with the **same** partition key.

### Accessing the partition key in tasks

```python
from airflow.sdk import task
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

@task
def use_partition(**context):
    print(context["dag_run"].partition_key)

BashOperator(
    task_id="bash_partition",
    bash_command="echo {{ dag_run.partition_key }}",
)

SQLExecuteQueryOperator(
    task_id="query_partition",
    conn_id="my_conn",
    sql="""
    SELECT * FROM orders
    WHERE order_date >= DATEADD(day, -1, '{{ dag_run.partition_key }}'::DATE)
      AND order_date < '{{ dag_run.partition_key }}'::DATE
    ;""",
)
```

---

## Partition key mappers (Airflow 3.2+)

Mappers normalize partition keys to a desired grain. Provide them via `partition_mapper_config` or `default_partition_mapper` on `PartitionedAssetTimetable`.

| Mapper | Input example | Output |
|--------|--------------|--------|
| `IdentityMapper()` | `2026-03-16T09:37:51` | `2026-03-16T09:37:51` (unchanged) |
| `ToHourlyMapper()` | `2026-03-16T09:37:51` | `2026-03-16T09` |
| `ToDailyMapper()` | `2026-03-16T09:37:51` | `2026-03-16` |
| `ToWeeklyMapper()` | `2026-03-16T09:37:51` | `2026-03-16 (W12)` |
| `ToMonthlyMapper()` | `2026-03-16T09:37:51` | `2026-03` |
| `ToQuarterlyMapper()` | `2026-03-16T09:37:51` | `2026-Q1` |
| `ToYearlyMapper()` | `2026-03-16T09:37:51` | `2026` |
| `AllowedKeyMapper(["a","b"])` | `a` | `a` (rejects keys not in list) |
| `ProductMapper(m1, m2, ...)` | `Finance\|2026-03-16T09:00` | Applies one mapper per `\|`-delimited segment |

### Per-asset mapper config

```python
from airflow.sdk import (
    dag, task, Asset, PartitionedAssetTimetable,
    ToDailyMapper, ToWeeklyMapper,
)

asset_a = Asset("hourly_events")
asset_b = Asset("weekly_reports")

@dag(
    schedule=PartitionedAssetTimetable(
        assets=(asset_a | asset_b),
        partition_mapper_config={
            asset_a: ToDailyMapper(),
            asset_b: ToWeeklyMapper(),
        },
    )
)
def mixed_grain():
    ...

mixed_grain()
```

### Default mapper

```python
@dag(
    schedule=PartitionedAssetTimetable(
        assets=Asset("my_asset"),
        default_partition_mapper=ToDailyMapper(),
    )
)
```

### Composite partition keys

Use `|`-delimited segments with `ProductMapper`:

```python
from airflow.sdk import (
    dag, task, Asset, PartitionedAssetTimetable,
    ProductMapper, IdentityMapper, ToDailyMapper, AllowedKeyMapper,
)

@dag(
    schedule=PartitionedAssetTimetable(
        assets=Asset("segmented_data"),  # with a partition key like "Finance|2026-03-16T09:00:00|Revenue"
        partition_mapper_config={
            Asset("segmented_data"): ProductMapper(
                IdentityMapper(),
                ToDailyMapper(),
                AllowedKeyMapper(["Revenue", "ARR"]),
            ),
        },
    )
)
def composite_consumer():

    @task
    def process(**context):
        pk = context["dag_run"].partition_key
        print(pk)  # e.g. "Finance|2026-03-16|Revenue"

    process()

composite_consumer()
```

The partition key must have the same number of `|`-delimited segments as mappers in the `ProductMapper`, and each segment must be valid for its mapper.

> **Chaining Dags**: When chaining several Dags with partitioned asset schedules, partition key mappers must be identical for all Dags after the first one in the chain.

---

## Asset listeners

Listeners are [Airflow plugins](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/plugins.html) that run code when asset-related events occur anywhere in the Airflow instance.

```python
from airflow.plugins_manager import AirflowPlugin
from airflow.listeners.types import AssetEvent
from airflow.serialization.definitions.assets import SerializedAsset, SerializedAssetAlias
from airflow.listeners import hookimpl
import sys


@hookimpl
def on_asset_created(asset: SerializedAsset):
    """Runs when a new asset is registered."""
    pass


@hookimpl
def on_asset_alias_created(asset_alias: SerializedAssetAlias):
    """Runs when a new asset alias is registered."""
    pass


@hookimpl
def on_asset_changed(asset: SerializedAsset):
    """Runs when any asset change occurs."""
    pass

@hookimpl
def on_asset_event_emitted(asset_event: AssetEvent):
    """Runs when an asset event is emitted."""
    pass

class AssetListenerPlugin(AirflowPlugin):
    name = "asset_listener_plugin"
    listeners = [sys.modules[__name__]]
```

Place this file in `plugins/` choose the relevant function(s) and the code that should execute when the event occurs. Restart required after changes.

---

## Ways to create an asset event

| Method | Partitioned? | Notes |
|--------|-------------|-------|
| Task with `outlets` completes successfully | Only if Dag uses `CronPartitionTimetable` | Most common method |
| `POST /api/v2/assets/events` ([see REST API](#rest-api-endpoints)) | Optional `partition_key` in body | Cross-deployment dependencies |
| **Create Asset Event** button in Airflow UI | Optional `partition_key` in dialog | **Materialize** runs the producing Dag, **Manual** creates event directly |
| `@asset` decorator Dag completes | No | Shorthand for one-task-one-asset Dags |
| `AssetWatcher` receives a `TriggerEvent` | No | Event-driven scheduling from message queues |

---

## REST API endpoints

The Airflow 3 REST API uses `/api/v2/assets/` paths (not the old `/api/v1/datasets/` from Airflow 2). All asset operations are under the `Asset` tag in the [API reference](https://airflow.apache.org/docs/apache-airflow/stable/stable-rest-api-ref.html#tag/Asset).

### Assets and aliases

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v2/assets` | List all assets (filterable) |
| `GET` | `/api/v2/assets/{asset_id}` | Get a single asset with its producing tasks, consuming Dags, aliases, and watchers |
| `GET` | `/api/v2/assets/aliases` | List all asset aliases |
| `GET` | `/api/v2/assets/aliases/{asset_alias_id}` | Get a single asset alias |

### Asset events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v2/assets/events` | List asset events (filterable by `asset_id`, time range, etc.) |
| `POST` | `/api/v2/assets/events` | Create an asset event — body accepts `asset_id`, optional `extra` dict and `partition_key` |
| `POST` | `/api/v2/assets/{asset_id}/materialize` | Materialize an asset by triggering the Dag run that produces it |

### Queued asset events

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v2/dags/{dag_id}/assets/queuedEvents` | All queued events for a Dag |
| `GET` | `/api/v2/dags/{dag_id}/assets/{asset_id}/queuedEvents` | Queued events for a specific asset/Dag pair |
| `GET` | `/api/v2/assets/{asset_id}/queuedEvents` | All queued events for an asset across all Dags |
| `DELETE` | `/api/v2/dags/{dag_id}/assets/queuedEvents` | Clear all queued events for a Dag |
| `DELETE` | `/api/v2/dags/{dag_id}/assets/{asset_id}/queuedEvents` | Clear queued events for a specific asset/Dag pair |
| `DELETE` | `/api/v2/assets/{asset_id}/queuedEvents` | Clear all queued events for an asset |

### Dag run context

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v2/dags/{dag_id}/dagRuns/{dag_run_id}/upstreamAssetEvents` | Get asset events that triggered a specific Dag run |

### Dag filtering

The `GET /api/v2/dags` endpoint supports `has_asset_schedule` (boolean) and `asset_dependency` (name or URI) query parameters to filter Dags by their asset relationships.

---

## Common pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| Consumer Dag never triggers | Dag is paused | Unpause the Dag |
| Consumer fires too often | Multiple tasks produce same asset | Each producer completion triggers independently — consolidate if needed |
| `triggering_asset_events` is empty | Dag was triggered manually | Guard with `for asset, events in triggering_asset_events.items()` |
| Using `from airflow.datasets import Dataset` | Airflow 2.x import | Use `from airflow.sdk import Asset` |
| `[]` with `\|` operator fails | Square brackets don't support conditional expressions | Use `()` for conditional scheduling |
| Partitioned events don't trigger consumer | Consumer uses `schedule=[Asset(...)]` | Use `PartitionedAssetTimetable` |
| Regular events don't trigger partitioned consumer | Consumer uses `PartitionedAssetTimetable` | Partitioned consumers only react to partitioned events |
| Partition key mapper mismatch in chain | Downstream Dag uses different mapper | Keep mappers identical for all Dags after the first |
| Manual Dag run has no partition key | `CronPartitionTimetable` only sets keys for scheduled/backfill runs | Provide `partition_key` in trigger config or API |

---

## References

- [Basic asset-based scheduling](https://www.astronomer.io/docs/learn/airflow-datasets)
- [Advanced asset-based scheduling](https://www.astronomer.io/docs/learn/airflow-advanced-asset-scheduling)
- [Partitioned Dag runs and asset events](https://www.astronomer.io/docs/learn/airflow-partitioned-runs)

## Related skills

- **authoring-dags**: Workflow and best practices for writing Dags
- **annotating-task-lineage**: Adding lineage metadata with inlets and outlets
- **airflow-plugins**: Building plugins (relevant for asset listeners)
