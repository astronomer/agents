---
name: analyzing-data-benchmark
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

Answer business questions by querying the data warehouse.

## Approach: SQL-Only

**ALLOWED:**
- SQL queries via `run_sql()` kernel function
- INFORMATION_SCHEMA queries for table/column discovery
- SHOW TABLES, DESCRIBE TABLE for schema introspection

**FORBIDDEN:**
- Observe MCP tools
- Grep, Read, or Glob to search the codebase
- Reading any JSON files

---

## Workflow

1. **Discover tables** via INFORMATION_SCHEMA or SHOW TABLES
2. **Query data** via run_sql()
3. **Return the answer**

---

## SQL Execution

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "df = run_sql('YOUR SQL HERE'); print(df)"
```

## Table Discovery

```sql
-- List all schemas
SHOW SCHEMAS IN DATABASE HQ;

-- List tables in a schema
SHOW TABLES IN SCHEMA HQ.schema_name;

-- Search for tables by name pattern
SELECT TABLE_SCHEMA, TABLE_NAME
FROM HQ.INFORMATION_SCHEMA.TABLES
WHERE TABLE_NAME ILIKE '%keyword%';

-- Find columns by name
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
FROM HQ.INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME ILIKE '%keyword%';

-- Describe a specific table
DESCRIBE TABLE HQ.schema.table_name;
```

## Query Tips

- Use LIMIT during exploration
- Filter early with WHERE clauses
- Prefer pre-aggregated tables (schemas starting with METRICS_, MART_, AGG_)
