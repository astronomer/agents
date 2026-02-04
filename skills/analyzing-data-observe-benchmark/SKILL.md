---
name: analyzing-data-observe-benchmark
description: Queries data warehouse and answers business questions about data. Uses Astro Observability catalog to discover tables, then queries via SQL. Handles ARR, revenue, metrics, customer data, financial questions, and any SQL analysis.
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

# COMPLETE THE TASK - DO NOT STOP EARLY

You MUST complete these 2 steps in order:

## STEP 1: Search for tables (MCP)

```
Tool: mcp__plugin_data_observe__search_assets
Parameters: {"search": "<keywords>", "asset_types": ["snowflakeTable"], "limit": 10}
```

## STEP 2: Get column details for the best match (MCP)

Pick the most relevant table from Step 1 (prefer HQ.METRICS_* or HQ.MART_* schemas) and get its columns:

```
Tool: mcp__plugin_data_observe__get_asset
Parameters: {"asset_id": "HQ.SCHEMA.TABLE_NAME"}
```

This returns column names, types, and descriptions to help write accurate SQL.

## STEP 3: Query the data (SQL) - DO NOT SKIP THIS

After finding tables, you MUST run SQL to get the actual answer:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "df = run_sql('SELECT ... FROM HQ.SCHEMA.TABLE ...'); print(df)"
```

**CRITICAL: Do NOT stop after step 1. Do NOT ask "would you like me to query?" - just query it.**

## Rules

- All 3 steps are MANDATORY - never respond with just table names
- For ARR questions: `SELECT MAX(ARR_AMT) FROM table WHERE EOM_DATE = (SELECT MAX(EOM_DATE) FROM table)`
- For product ARR: Filter by PRODUCT column (e.g., `WHERE PRODUCT = 'Software'`)
- Tables from METRICS_* or MART_* schemas are best
- ALWAYS return a number as the final answer
