---
name: warehouse-init
description: "Initialize warehouse schema discovery and generate .astro/warehouse.md with table metadata for instant lookups. Use when the user says /astronomer-data:warehouse-init, asks to explore their database, list all tables, scan schema, what tables are available, set up data discovery, or check what data exists. Run once per project, refresh when schema changes."
---

# Initialize Warehouse Schema

Generate a comprehensive, user-editable schema reference file for the data warehouse.

## What This Does

1. Discovers all databases, schemas, tables, and columns from the warehouse
2. **Enriches with codebase context** (dbt models, gusty SQL, schema docs)
3. Records row counts and identifies large tables
4. Generates `.astro/warehouse.md` - a version-controllable, team-shareable reference
5. Enables instant concept→table lookups without warehouse queries

**Scripts:** `../analyzing-data/scripts/` — All CLI commands below are relative to the `analyzing-data` skill's directory. Before running any `scripts/cli.py` command, `cd` to `../analyzing-data/` relative to this file.

## Process

### Step 1: Read Warehouse Configuration

```bash
cat ~/.astro/agents/warehouse.yml
```

Get the list of databases to discover (e.g., `databases: [HQ, ANALYTICS, RAW]`).

### Step 2: Search Codebase for Context (Parallel)

Launch an Explore subagent in parallel with Step 3 to find business context:

- dbt models (`**/models/**/*.yml`, `**/schema.yml`) — extract table/column descriptions, primary keys, tests
- Gusty/declarative SQL (`**/dags/**/*.sql` with YAML frontmatter) — parse description, primary_key, tests
- AGENTS.md or CLAUDE.md files with data layer documentation

Return a mapping of `table_name -> {description, primary_key, important_columns, layer}`.

### Step 3: Parallel Warehouse Discovery

Launch one subagent per database (all in a single message for parallelism). Each subagent discovers metadata via SQL:

```bash
# Query schemas
uv run scripts/cli.py exec "df = run_sql('SELECT SCHEMA_NAME FROM {DATABASE}.INFORMATION_SCHEMA.SCHEMATA')"
uv run scripts/cli.py exec "print(df)"

# Query tables with row counts
uv run scripts/cli.py exec "df = run_sql('SELECT TABLE_SCHEMA, TABLE_NAME, ROW_COUNT, COMMENT FROM {DATABASE}.INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA, TABLE_NAME')"
uv run scripts/cli.py exec "print(df)"

# For important schemas (MODEL_*, METRICS_*, MART_*), query columns
uv run scripts/cli.py exec "df = run_sql('SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COMMENT FROM {DATABASE}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ''{SCHEMA}''')"
uv run scripts/cli.py exec "print(df)"
```

Flag tables with >100M rows as "large".

**Validate:** Verify each subagent returned schema/table/column data before proceeding. Re-run any failed databases.

### Step 4: Discover Categorical Value Families

For key categorical columns (like OPERATOR, STATUS, TYPE, FEATURE), discover value families:

```bash
uv run cli.py exec "df = run_sql('''
SELECT DISTINCT column_name, COUNT(*) as occurrences
FROM table
WHERE column_name IS NOT NULL
GROUP BY column_name
ORDER BY occurrences DESC
LIMIT 50
''')"
uv run cli.py exec "print(df)"
```

Group related values into families by common prefix/suffix (e.g., `Export*` for ExportCSV, ExportJSON, ExportParquet).

### Step 5: Merge and Validate Results

Combine warehouse metadata + codebase context into:

1. **Quick Reference table** — concept → table mappings (pre-populated from code if found)
2. **Categorical Columns** — value families for key filter columns
3. **Database sections** — one per database with schema subsections
4. **Table details** — columns, row counts, descriptions from code, large table warnings

**Validate:** Confirm merged output covers all configured databases and enriched descriptions from code are correctly attached before generating the file.

### Step 6: Generate warehouse.md

Write to `.astro/warehouse.md` (default) or `~/.astro/agents/warehouse.md` (if `--global`).

The output should contain: a Quick Reference table (concept → table mappings), Categorical Columns section, Data Layer Hierarchy, then one section per database with schema subsections. Each table entry includes columns, row count, description (from code if found), and a warning for tables >100M rows.

**Validate:** Read back the generated file and confirm it contains all expected databases and is valid markdown.

### Step 7: Pre-populate Cache

After generating warehouse.md, populate the concept cache:

```bash
uv run cli.py concept import -p .astro/warehouse.md
uv run cli.py concept learn customers HQ.MART_CUST.CURRENT_ASTRO_CUSTS -k ACCT_ID
```

### Step 8: Offer CLAUDE.md Integration (Ask User)

Ask whether to append the Quick Reference table to CLAUDE.md for always-in-context schema lookups (improves complex query accuracy). If yes, append to `.claude/CLAUDE.md` or `CLAUDE.md`, avoiding duplicates.

## After Generation

Report summary: database count, schema count, table count, enriched tables count, cached concepts count.

## Command Options

| Option | Effect |
|--------|--------|
| `/astronomer-data:warehouse-init` | Generate .astro/warehouse.md |
| `/astronomer-data:warehouse-init --refresh` | Regenerate, preserving user edits |
| `/astronomer-data:warehouse-init --database HQ` | Only discover specific database |
| `/astronomer-data:warehouse-init --global` | Write to ~/.astro/agents/ instead |

## Refresh Behavior

When `--refresh` is specified: read existing warehouse.md, preserve HTML comments, user-added Quick Reference entries, and user-added descriptions. Update row counts and add new tables. Mark removed tables with `<!-- REMOVED -->`.

## Cache Management

The runtime cache has a **7-day TTL** by default. Run `/astronomer-data:warehouse-init --refresh` when:
- **Schema changes**: Tables added, renamed, or removed
- **Column changes**: New columns added or types changed
- **After deployments**: If your data pipeline deploys schema migrations

```bash
uv run scripts/cli.py cache status
uv run scripts/cli.py cache clear --stale-only
uv run scripts/cli.py cache clear
```
