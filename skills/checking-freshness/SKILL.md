---
name: checking-freshness
description: Quick data freshness check. Use when the user asks if data is up to date, when a table was last updated, if data is stale, or needs to verify data currency before using it.
---

# Data Freshness Check

Quickly determine if data is fresh enough to use.

<!-- astro-cli-version:start -->
## Astro CLI version

Commands in this skill, including its reference files, are written for Astro CLI v2. Before anything else, run this as a command of its own, with nothing chained before or after it, and choose the dialect from what it prints: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`
On Windows `cmd.exe`, which has no `/dev/null`, run `astro local af --help >NUL 2>&1 && echo v2 || echo v1` instead.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI. Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` and `--output json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is the line under it, starting `# v1:`. Where something behaves differently on v1, a line starting **v1:** says how. If `af` is not on PATH, write `uvx --from astro-airflow-mcp af <args>` out in full in every command. Don't put it in a shell variable or alias: zsh won't split `$AF`, and shell state doesn't carry over between commands.
- v2 replaced `astro dev` with `astro local`; `astro dev <cmd>` on v2 fails and names its replacement.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project, although the probe printed v2. Switch to the v1 forms: the standalone `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.
- `-d` and `-o` mean deployment and output in v2, but DAG id and offset in v1, so never carry either into a v1 command. `--dag-id`, `--offset`, `--state`, `--limit`, `--try`, `--map-index`, and `--timeout` mean the same in both.
- If a command here, or in the project's `AGENTS.md`, disagrees with the installed CLI, trust the CLI: check `astro <cmd> --help` (v1: `af <cmd> --help` or `astro dev <cmd> --help`).
<!-- astro-cli-version:end -->

## Freshness Check Process

For each table to check:

### 1. Find the Timestamp Column

Look for columns that indicate when data was loaded or updated:
- `_loaded_at`, `_updated_at`, `_created_at` (common ETL patterns)
- `updated_at`, `created_at`, `modified_at` (application timestamps)
- `load_date`, `etl_timestamp`, `ingestion_time`
- `date`, `event_date`, `transaction_date` (business dates)

Query INFORMATION_SCHEMA.COLUMNS if you need to see column names.

### 2. Query Last Update Time

```sql
SELECT
    MAX(<timestamp_column>) as last_update,
    CURRENT_TIMESTAMP() as current_time,
    TIMESTAMPDIFF('hour', MAX(<timestamp_column>), CURRENT_TIMESTAMP()) as hours_ago,
    TIMESTAMPDIFF('minute', MAX(<timestamp_column>), CURRENT_TIMESTAMP()) as minutes_ago
FROM <table>
```

### 3. Check Row Counts by Time

For tables with regular updates, check recent activity:

```sql
SELECT
    DATE_TRUNC('day', <timestamp_column>) as day,
    COUNT(*) as row_count
FROM <table>
WHERE <timestamp_column> >= DATEADD('day', -7, CURRENT_DATE())
GROUP BY 1
ORDER BY 1 DESC
```

## Freshness Status

Report status using this scale:

| Status | Age | Meaning |
|--------|-----|---------|
| **Fresh** | < 4 hours | Data is current |
| **Stale** | 4-24 hours | May be outdated, check if expected |
| **Very Stale** | > 24 hours | Likely a problem unless batch job |
| **Unknown** | No timestamp | Can't determine freshness |

## If Data is Stale

Check Airflow for the source pipeline:

1. **Find the DAG**: Which DAG populates this table? Use `astro local af dags list` and look for matching names.

2. **Check DAG status**:
   - Is the DAG paused? Use `astro local af dags get <dag_id>`
   - Did the last run fail? Use `astro local af dags stats`
   - Is a run currently in progress?

3. **Diagnose if needed**: If the DAG failed, use the **debugging-dags** skill to investigate.

### On Astro

If you're running on Astro, you can also:

- **DAG history in the Astro UI**: Check the deployment's DAG run history for a visual timeline of recent runs and their outcomes
- **Astro alerts for SLA monitoring**: Configure alerts to get notified when DAGs miss their expected completion windows, catching staleness before users report it

### On OSS Airflow

- **Airflow UI**: Use the DAGs view and task logs to verify last successful runs and SLA misses

## Output Format

Provide a clear, scannable report:

```
FRESHNESS REPORT
================

TABLE: database.schema.table_name
Last Update: 2024-01-15 14:32:00 UTC
Age: 2 hours 15 minutes
Status: Fresh

TABLE: database.schema.other_table
Last Update: 2024-01-14 03:00:00 UTC
Age: 37 hours
Status: Very Stale
Source DAG: daily_etl_pipeline (FAILED)
Action: Investigate with **debugging-dags** skill
```

## Quick Checks

If user just wants a yes/no answer:
- "Is X fresh?" -> Check and respond with status + one line
- "Can I use X for my 9am meeting?" -> Check and give clear yes/no with context
