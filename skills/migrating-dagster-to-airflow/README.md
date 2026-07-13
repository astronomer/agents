# migrating-dagster-to-airflow

A skill for migrating Dagster projects to Apache Airflow 3 on Astro. It contains a concept map of how every Dagster construct translates to Airflow 3, reference docs for the parts that are genuinely hard to translate, and a workflow that takes a project from a read-only scan to verified output parity and incremental cutover.

Airflow 3 made assets first-class, which is what makes this migration natural: most Dagster concepts (assets, partitions, materializations, asset-driven scheduling) have direct Airflow 3 counterparts, and the ones that don't are called out with a documented alternative rather than papered over.

## How it works

The skill drives a migration through six phases:

1. **Inventory**: [`scripts/inventory.py`](scripts/inventory.py) scans the Dagster repo read-only and lists every definition, so nothing gets missed. The agent then classifies each one from the concept map ([`reference/mapping.md`](reference/mapping.md)): mechanical, needs judgment, redesign, or no equivalent with a documented alternative. The inventory ends with a recommendation: migrate, or migrate with named conditions; if several losses genuinely have no acceptable answer, it will say so in writing.
2. **Plan**: DAG boundaries, plus a decision for every producer-consumer handoff. Dagster's IO managers persist outputs implicitly while Airflow tasks share nothing, which makes this the hardest part; [`reference/io-and-data-passing.md`](reference/io-and-data-passing.md) carries the decision tree.
3. **Trial** a few representative pipelines end to end.
4. **Migrate piece by piece**, each definition passing six checks: lint, import, structure, execution, output parity against the still-running Dagster deployment, and safe re-runs ([`reference/validation.md`](reference/validation.md)). Known failures and their fixes live in [`reference/troubleshooting.md`](reference/troubleshooting.md); progress is tracked by [`scripts/status.py`](scripts/status.py), which refuses to call the migration done while anything is unaccounted for.
5. **Platform layer**: connections, secrets, alerts, CI/CD ([`reference/astro-deployment.md`](reference/astro-deployment.md)).
6. **Cut over gradually**: Dagster stays the system of record until parity is measured; schedules flip last; rollback is one step.

## Using it

```bash
claude "Use the migrating-dagster-to-airflow skill to migrate ~/my-dagster-repo to Airflow 3 on Astro"
```

The early phases are read-only; nothing touches the Dagster deployment or its schedules until the cutover phase at the end. If you're the human driving it, read [`reference/quickstart.md`](reference/quickstart.md) first: hour-one commands, a glossary, and what can and cannot break.

## What a translation looks like

```python
# Dagster: an hourly-partitioned asset
@asset(partitions_def=HourlyPartitionsDefinition(start_date=datetime(2020, 12, 1)))
def events(context):
    start, end = context.partition_time_window
    ...

# Airflow 3: the same asset, natively partitioned; keys kept byte-identical
# to Dagster's so every storage path still resolves
@asset(uri="s3://lake/events",
       schedule=CronPartitionTimetable("0 * * * *", timezone="UTC",
                                       key_format="%Y-%m-%d-%H:%M"))
def events(dag_run):
    key = dag_run.partition_key
    ...
```

[`reference/mapping.md`](reference/mapping.md) covers the full surface this way, including a Dagster-to-Airflow-3 concept table for anyone newer to the Airflow side.

## How it's been tested

Seven full migrations before shipping: Dagster's OSS examples, two community projects (253 and 296 definitions), Dagster Labs' own open-source data platform, a synthetic project that uses every Dagster feature, and one run against a real production Snowflake. Wherever a project could actually run, the migrated pipelines produced the same output data as the original, checked table by table, including a live cutover rehearsal with rollback. Verified against Airflow 3.3 / Astro Runtime 3.3-2 / astronomer-cosmos 1.15 / Dagster 1.13; version-dependent guidance says which version it was checked on, and `SKILL.md` explains how to re-verify on newer stacks.
