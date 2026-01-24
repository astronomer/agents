---
name: analyzing-data
description: Queries data warehouse and answers business questions about data. Handles questions requiring database/warehouse queries including "who uses X", "how many Y", "show me Z", "find customers", "what is the count", data lookups, metrics, trends, or SQL analysis.
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py ensure"
          once: true
  Stop:
    - hooks:
        - type: command
          command: "uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py stop"
---

# Data Analysis

Answer business questions by querying the data warehouse. The kernel starts automatically on first use.

## Prerequisites

**uv must be installed:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Scripts are located relative to this skill file.

## MANDATORY FIRST STEP

**Before any other action, check for cached patterns:**

```bash
uv run scripts/cli.py pattern lookup "<user's question>"
```

This is NON-NEGOTIABLE. Patterns contain proven strategies that save time and avoid failed queries.

---

## Workflow

```
Analysis Progress:
- [ ] Step 1: pattern lookup (check for cached strategy)
- [ ] Step 2: concept lookup (check for known tables)
- [ ] Step 3: Search codebase for table definitions (Grep)
- [ ] Step 4: Read SQL file to get table/column names
- [ ] Step 5: Execute query via kernel (run_sql)
- [ ] Step 6: learn_concept (ALWAYS before presenting results)
- [ ] Step 7: learn_pattern (ALWAYS if discovery required)
- [ ] Step 8: record_pattern_outcome (if you used a pattern in Step 1)
- [ ] Step 9: Present findings to user
```

---

## CLI Commands

### Kernel Management

```bash
uv run scripts/cli.py start           # Start kernel with Snowflake
uv run scripts/cli.py exec "..."      # Execute Python code
uv run scripts/cli.py status          # Check kernel status
uv run scripts/cli.py restart         # Restart kernel
uv run scripts/cli.py stop            # Stop kernel
uv run scripts/cli.py install plotly  # Install additional packages
```

### Concept Cache (concept -> table mappings)

```bash
# Look up a concept
uv run scripts/cli.py concept lookup customers

# Learn a new concept
uv run scripts/cli.py concept learn customers HQ.MART_CUST.CURRENT_ASTRO_CUSTS -k ACCT_ID

# List all concepts
uv run scripts/cli.py concept list

# Import concepts from warehouse.md
uv run scripts/cli.py concept import -p /path/to/warehouse.md
```

### Pattern Cache (query strategies)

```bash
# Look up patterns for a question
uv run scripts/cli.py pattern lookup "who uses operator X"

# Learn a new pattern
uv run scripts/cli.py pattern learn operator_usage \
    -q "who uses X operator" \
    -q "which customers use X" \
    -s "1. Query TASK_RUNS for operator_class" \
    -s "2. Join with ORGS on org_id" \
    -t "HQ.MODEL_ASTRO.TASK_RUNS" \
    -t "HQ.MODEL_ASTRO.ORGANIZATIONS" \
    -g "TASK_RUNS is huge - always filter by date"

# Record pattern outcome
uv run scripts/cli.py pattern record operator_usage --success

# List all patterns
uv run scripts/cli.py pattern list

# Delete a pattern
uv run scripts/cli.py pattern delete operator_usage
```

### Table Schema Cache

```bash
# Look up cached table schema
uv run scripts/cli.py table lookup HQ.MART_CUST.CURRENT_ASTRO_CUSTS

# Cache a table schema
uv run scripts/cli.py table cache DB.SCHEMA.TABLE -c '[{"name":"id","type":"INT"}]'

# List all cached tables
uv run scripts/cli.py table list

# Delete from cache
uv run scripts/cli.py table delete DB.SCHEMA.TABLE
```

### Cache Management

```bash
# View cache statistics
uv run scripts/cli.py cache status

# Clear all caches
uv run scripts/cli.py cache clear

# Clear only stale entries (older than 90 days)
uv run scripts/cli.py cache clear --stale-only
```

---

## Quick Start Example

```bash
# 1. Check for existing patterns
uv run scripts/cli.py pattern lookup "how many customers"

# 2. Check for known concepts
uv run scripts/cli.py concept lookup customers

# 3. Execute query
uv run scripts/cli.py exec "df = run_sql('SELECT COUNT(*) FROM HQ.MART_CUST.CURRENT_ASTRO_CUSTS')"
uv run scripts/cli.py exec "print(df)"

# 4. Cache what we learned
uv run scripts/cli.py concept learn customers HQ.MART_CUST.CURRENT_ASTRO_CUSTS -k ACCT_ID
```

---

## Available Functions in Kernel

Once kernel starts, these are available:

| Function | Description |
|----------|-------------|
| `run_sql(query, limit=100)` | Execute SQL, return Polars DataFrame |
| `run_sql_pandas(query, limit=100)` | Execute SQL, return Pandas DataFrame |
| `pl` | Polars library (imported) |
| `pd` | Pandas library (imported) |

---

## Table Discovery via Codebase

If concept/pattern cache miss, search the codebase:

```
Grep pattern="<concept>" glob="**/*.sql"
```

| Repo Type | Where to Look |
|-----------|---------------|
| **Gusty** | `dags/declarative/04_metric/`, `06_reporting/`, `05_mart/` |
| **dbt** | `models/marts/`, `models/staging/` |

---

## Known Tables Quick Reference

| Concept | Table | Key Column | Date Column |
|---------|-------|------------|-------------|
| customers | HQ.MART_CUST.CURRENT_ASTRO_CUSTS | ACCT_ID | - |
| organizations | HQ.MODEL_ASTRO.ORGANIZATIONS | ORG_ID | CREATED_TS |
| deployments | HQ.MODEL_ASTRO.DEPLOYMENTS | DEPLOYMENT_ID | CREATED_TS |
| task_runs | HQ.MODEL_ASTRO.TASK_RUNS | - | START_TS |
| dag_runs | HQ.MODEL_ASTRO.DAG_RUNS | - | START_TS |
| users | HQ.MODEL_ASTRO.USERS | USER_ID | - |
| accounts | HQ.MODEL_CRM.SF_ACCOUNTS | ACCT_ID | - |

**Large tables (always filter by date):** TASK_RUNS (6B rows), DAG_RUNS (500M rows)

---

## Query Tips

- Use LIMIT during exploration
- Filter early with WHERE clauses
- Prefer pre-aggregated tables (`METRICS_*`, `MART_*`, `AGG_*`)
- For 100M+ row tables: no JOINs or GROUP BY on first query

---

## Reference

- [reference/discovery-warehouse.md](reference/discovery-warehouse.md) - Large table handling, warehouse discovery
