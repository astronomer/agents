---
name: analyzing-data-observe-benchmark
description: Discovers data assets using Astro Observability catalog and queries data via SQL.
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

# EXECUTE IMMEDIATELY - NO EXPLORATION

## YOUR FIRST TOOL CALL MUST BE:

Tool: `mcp__plugin_data_observe__search_assets`
Parameters: `{"search": "<keywords>", "asset_types": ["snowflakeTable"], "limit": 30}`

This MCP tool is already available to you. Call it NOW like you call Bash or Read.

---

## AFTER MCP returns tables, run SQL:

```bash
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "df = run_sql('SELECT ...'); print(df)"
```

---

## STRICT RULES

- First call = MCP search (mandatory)
- Second call = SQL query (mandatory)
- For "total ARR" questions: get the MAX date value, not SUM of all rows
- Tables from METRICS_* or MART_* schemas are best
- DO NOT use ls, find, --help, Glob, Read, or Grep
