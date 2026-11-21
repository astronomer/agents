---
name: tracing-upstream-lineage
description: Trace upstream data lineage. Use when the user asks where data comes from, what feeds a table, upstream dependencies, data sources, or needs to understand data origins.
---

# Upstream Lineage: Sources

Trace the origins of data - answer "Where does this data come from?"

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

## Lineage Investigation

### Step 1: Identify the Target Type

Determine what we're tracing:
- **Table**: Trace what populates this table
- **Column**: Trace where this specific column comes from
- **DAG**: Trace what data sources this DAG reads from

### Step 2: Find the Producing DAG

Tables are typically populated by Airflow DAGs. Find the connection:

1. **Search DAGs by name**: Use `astro local af dags list` and look for DAG names matching the table name
   - `load_customers` -> `customers` table
   - `etl_daily_orders` -> `orders` table

2. **Explore DAG source code**: Use `astro local af dags source <dag_id>` to read the DAG definition
   - Look for INSERT, MERGE, CREATE TABLE statements
   - Find the target table in the code

3. **Check DAG tasks**: Use `astro local af tasks list <dag_id>` to see what operations the DAG performs

### On Astro

If you're running on Astro, the **Lineage tab** in the Astro UI provides visual lineage exploration across DAGs and datasets. Use it to quickly trace upstream dependencies without manually searching DAG source code.

### On OSS Airflow

Use DAG source code and task logs to trace lineage (no built-in cross-DAG UI).

### Step 3: Trace Data Sources

From the DAG code, identify source tables and systems:

**SQL Sources** (look for FROM clauses):
```python
# In DAG code:
SELECT * FROM source_schema.source_table  # <- This is an upstream source
```

**External Sources** (look for connection references):
- `S3Operator` -> S3 bucket source
- `PostgresOperator` -> Postgres database source
- `SalesforceOperator` -> Salesforce API source
- `HttpOperator` -> REST API source

**File Sources**:
- CSV/Parquet files in object storage
- SFTP drops
- Local file paths

### Step 4: Build the Lineage Chain

Recursively trace each source:

```
TARGET: analytics.orders_daily
    ^
    +-- DAG: etl_daily_orders
            ^
            +-- SOURCE: raw.orders (table)
            |       ^
            |       +-- DAG: ingest_orders
            |               ^
            |               +-- SOURCE: Salesforce API (external)
            |
            +-- SOURCE: dim.customers (table)
                    ^
                    +-- DAG: load_customers
                            ^
                            +-- SOURCE: PostgreSQL (external DB)
```

### Step 5: Check Source Health

For each upstream source:
- **Tables**: Check freshness with the **checking-freshness** skill
- **DAGs**: Check recent run status with `astro local af dags stats`
- **External systems**: Note connection info from DAG code

## Lineage for Columns

When tracing a specific column:

1. Find the column in the target table schema
2. Search DAG source code for references to that column name
3. Trace through transformations:
   - Direct mappings: `source.col AS target_col`
   - Transformations: `COALESCE(a.col, b.col) AS target_col`
   - Aggregations: `SUM(detail.amount) AS total_amount`

## Output: Lineage Report

### Summary
One-line answer: "This table is populated by DAG X from sources Y and Z"

### Lineage Diagram
```
[Salesforce] --> [raw.opportunities] --> [stg.opportunities] --> [fct.sales]
                        |                        |
                   DAG: ingest_sfdc         DAG: transform_sales
```

### Source Details

| Source | Type | Connection | Freshness | Owner |
|--------|------|------------|-----------|-------|
| raw.orders | Table | Internal | 2h ago | data-team |
| Salesforce | API | salesforce_conn | Real-time | sales-ops |

### Transformation Chain
Describe how data flows and transforms:
1. Raw data lands in `raw.orders` via Salesforce API sync
2. DAG `transform_orders` cleans and dedupes into `stg.orders`
3. DAG `build_order_facts` joins with dimensions into `fct.orders`

### Data Quality Implications
- Single points of failure?
- Stale upstream sources?
- Complex transformation chains that could break?

### Related Skills
- Check source freshness: **checking-freshness** skill
- Debug source DAG: **debugging-dags** skill
- Trace downstream impacts: **tracing-downstream-lineage** skill
- Add manual lineage annotations: **annotating-task-lineage** skill
- Build custom lineage extractors: **creating-openlineage-extractors** skill
