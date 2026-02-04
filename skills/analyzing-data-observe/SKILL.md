---
name: analyzing-data-observe
description: Discovers data assets using Astro Observability catalog. Handles questions about "what tables exist", "find assets", "who owns this table", "what DAGs produce data", "show me Snowflake tables", asset discovery, metadata lookup, and data lineage exploration.
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

# Data Asset Discovery (Catalog) + SQL Execution

Discover data assets using Observe catalog, then query data using SQL.

## CRITICAL: Required Tools - NO CODEBASE READING

**You MUST use ONLY these specific tools:**

1. **`search_assets()`** - Observe MCP tool for discovering tables
2. **`run_sql()`** - SQL execution via kernel for querying data

**FORBIDDEN - DO NOT USE:**
- Grep, Read, or Glob to search the codebase
- Reading any JSON files for cached results
- Searching for answers in benchmark files or test results
- INFORMATION_SCHEMA queries (use Observe MCP instead)

**WORKFLOW:**
1. Use `search_assets()` to discover relevant tables
2. Use `run_sql()` to query the discovered tables
3. Return results directly - never read from filesystem

---

## Workflow

**Step 1: Discovery** - Use the `search_assets` MCP tool (NOT codebase search)
```python
# Use the Observe MCP tool - this queries the live catalog
search_assets(search="customer", asset_types=["snowflakeTable"], limit=10)
```

**Step 2: Get Column Details** - Use `get_asset` to retrieve column schema
```python
# Get column names, types, and descriptions for accurate SQL
get_asset(asset_id="HQ.MART_CUST.CURRENT_ASTRO_CUSTS")
```

**Step 3: Query Data** - Use SQL via kernel to get actual data
```bash
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "df = run_sql('SELECT COUNT(*) FROM HQ.MART_CUST.CURRENT_ASTRO_CUSTS'); print(df)"
```

## Example: "How many customers use Airflow 3?"

```
1. search_assets(search="deployment", asset_types=["snowflakeTable"])
   → Finds HQ.MODEL_ASTRO.DEPLOYMENTS table

2. get_asset(asset_id="HQ.MODEL_ASTRO.DEPLOYMENTS")
   → Returns columns: ORG_ID, AIRFLOW_VERSION, DEPLOYMENT_ID, etc.

3. run_sql("SELECT COUNT(DISTINCT ORG_ID) FROM HQ.MODEL_ASTRO.DEPLOYMENTS WHERE AIRFLOW_VERSION LIKE '3%'")
   → Returns actual count
```

**IMPORTANT**:
- Step 1 uses the Observe MCP `search_assets` tool (NOT Grep/Read)
- Step 2 uses `get_asset` to get column schema (returns column names, types, descriptions)
- Step 3 uses SQL to query actual data (NOT reading cached results)

---

## Overview

This skill combines:
- **Observe MCP**: Fast catalog search across all warehouses
- **SQL Execution**: Query actual data via Jupyter kernel

Use Observe for discovery, SQL for data retrieval.

---

## ⚡ Performance Best Practices

**CRITICAL**: The Observe API is fast, but multiple round-trips are slow. Minimize tool calls.

### ✅ DO: Single-Call Patterns

**Use high limits** (50-100, not 20):
```python
search_assets(search="customer", limit=100)  # Get everything in one call
```

**Use search results directly** - they contain metadata:
```python
# search_assets returns: assetId, name, type, namespace, description
# This is usually enough! Don't call get_asset unless you need lineage.
```

**Leverage filters** instead of post-processing:
```python
# Good: Filter in the query
search_assets(asset_types=["snowflakeTable"], namespaces=["prod"])

# Bad: Get everything, filter in Python
search_assets()  # Then manually filter results
```

**Format and return immediately**:
```python
# Make ONE search call, format the results, done.
# Don't paginate "just in case" - only if user asks for more.
```

### ❌ DON'T: Inefficient Anti-Patterns

**Don't paginate unnecessarily**:
```python
# Bad: Fetching all 243 customer tables
search_assets(search="customer", limit=20, offset=0)
search_assets(search="customer", limit=20, offset=20)
... (12 more calls)

# Good: Get enough to answer the question
search_assets(search="customer", limit=50)  # Usually sufficient
```

**Don't call get_asset in loops**:
```python
# Bad: One API call per asset
for asset in results:
    get_asset(asset['assetId'])  # 100 calls!

# Good: Use search results directly
# Only call get_asset if user needs lineage/ownership details
```

**Don't make redundant searches**:
```python
# Bad: Multiple searches when one would work
search_assets(asset_types=["snowflakeTable"])
search_assets(asset_types=["databricksTable"])
search_assets(asset_types=["bigQueryTable"])

# Good: Single search with multiple types
search_assets(asset_types=["snowflakeTable", "databricksTable", "bigQueryTable"])
```

### 🎯 Target: 1-3 Tool Calls Per Query

- **Simple listing**: 1 call (search + format)
- **Filtered search**: 1-2 calls (search, maybe refine)
- **Detailed lookup**: 2-3 calls (search + get_asset for specific item)

**If you're making >5 calls, you're doing it wrong.**

---

## When to Use This Skill

Use this skill for:
- **Asset Discovery**: "What tables exist?", "Find customer tables", "List all Snowflake tables"
- **Cross-Warehouse Search**: "Show me all tables across Snowflake, Databricks, and BigQuery"
- **Lineage Discovery**: "Which DAGs write to this table?", "What tasks produce customer data?"
- **Metadata Lookup**: "Who owns the ORDERS table?", "When was this asset last updated?"
- **Filter Discovery**: "What namespaces have assets?", "Which DAGs exist?"

**For SQL follow-up**:
- After discovering tables, use `run_sql()` to query the data
- DO NOT use schema discovery queries (SHOW TABLES, INFORMATION_SCHEMA) - use the catalog instead

---

## Available Tools

The Observe MCP provides these tools (automatically available, no setup needed):

### 1. `search_assets` - Primary Discovery Tool

Search and filter catalog assets. **This should be your main tool - it returns rich metadata.**

**Key Parameters**:
- `search` (string): Full-text search query
- `asset_types` (list): Filter by type:
  - Tables: `snowflakeTable`, `databricksTable`, `bigQueryTable`
  - Airflow: `airflowDag`, `airflowTask`, `airflowDataset`
  - OpenLineage: `openLineageDataset`
- `namespaces` (list): Filter by deployment namespace
- `dags` (list): Filter by DAG ID
- `dag_tags` (list): Filter by DAG tags
- `owners` (list): Filter by DAG owner
- `include_only_leaf_assets` (bool): Only leaf assets (no downstream deps)
- `include_only_root_assets` (bool): Only root assets (no upstream deps)
- `limit` (int): Max results (default: 20, **recommend 50-100**)
- `offset` (int): Pagination offset (only use if user needs more results)
- `sorts` (list): Sort criteria (e.g., `["assetId:asc"]`)

**Returns**: JSON with:
- `total_assets`: Total matching count
- `returned_count`: Results in this response
- `assets`: Array with `assetId`, `name`, `assetType`, `namespace`, `description`, etc.

**⚡ Performance tip**: Results include most metadata you need! Only call `get_asset` if you need detailed lineage or ownership.

### 2. `get_asset` - Column Schema & Detailed Lookup

Get detailed information about a **specific** asset, including **column definitions**.

**When to use**:
- ✅ **Before writing SQL** - get column names, types, and descriptions
- ✅ User asks about a specific table's ownership or lineage
- ✅ Need upstream/downstream dependencies
- ✅ Need connection details

**When NOT to use**:
- ❌ Just listing tables (use search_assets results directly)
- ❌ In loops over many assets

**Note**: `search_assets` returns empty `columns: []`. Use `get_asset` to retrieve full column schema.

**Parameters**:
- `asset_id` (string): The asset ID from search results

**Returns**: JSON with complete asset details including deployment, workspace, connection info, lineage metadata

### 3. `list_asset_filters` - Discover Filter Values

List available filter values for refining searches.

**Parameters**:
- `filter_type` (string): One of `namespace`, `dag_id`, `dag_tag`, `owner`
- `search` (string, optional): Search within filter values
- `limit` (int): Max results (default: 100)

**Returns**: JSON with available filter values

**Use when**: User asks "what namespaces exist?" or you need to discover available filters.

### 4. `get_connection_info` - Debug Connection

Get current Astro Cloud connection configuration.

**Returns**: JSON with organization ID, API URL, context, user email

**Use when**: Debugging authentication issues or user asks "what org am I connected to?"

---

## Efficient Workflows

### Pattern 1: Simple Listing (1 call)

**User asks**: "List Snowflake tables"

```python
# Single call - done!
search_assets(
    asset_types=["snowflakeTable"],
    limit=50  # Get plenty in one go
)
# Format results from response, return to user
```

**Calls**: 1
**Expected time**: 5-10 seconds

---

### Pattern 2: Keyword Search (1 call)

**User asks**: "Find all customer tables"

```python
# Single call with high limit
search_assets(
    search="customer",
    asset_types=["snowflakeTable", "databricksTable", "bigQueryTable"],
    limit=100  # Get all relevant results at once
)
# Format results showing: table name, warehouse, database
# Return immediately - don't paginate unless user asks for more
```

**Calls**: 1
**Expected time**: 5-10 seconds

---

### Pattern 3: Cross-Warehouse Summary (1 call)

**User asks**: "What tables do we have across all warehouses?"

```python
# Single call gets everything
results = search_assets(
    asset_types=["snowflakeTable", "databricksTable", "bigQueryTable"],
    limit=100
)
# Group by asset_type in Python
# Present summary: "Snowflake: X tables, Databricks: Y tables, ..."
```

**Calls**: 1
**Expected time**: 5-10 seconds

---

### Pattern 4: List DAGs (1 call)

**User asks**: "Which Airflow DAGs produce data?"

```python
# Single call - the search result shows if DAGs produce data
search_assets(
    asset_types=["airflowDag"],
    limit=100  # Get many DAGs at once
)
# Format and categorize from the results
# No need to check each DAG individually!
```

**Calls**: 1
**Expected time**: 5-10 seconds

**Note**: DAG metadata in search results usually indicates if it produces data. Don't call get_asset for each DAG.

---

### Pattern 5: Query Data with Column Discovery (3 calls)

**User asks**: "What's the total ARR?"

```python
# Call 1: Find relevant tables
results = search_assets(
    search="ARR",
    asset_types=["snowflakeTable"],
    limit=10
)

# Call 2: Get column schema for the best match
asset_details = get_asset(asset_id="HQ.METRICS_FINANCE.CONTRACT_ARR_MONTHLY")
# Returns: columns with names, types, descriptions (ARR_AMT, PRODUCT, EOM_DATE, etc.)

# Call 3: Query with accurate column names
run_sql("SELECT SUM(ARR_AMT) FROM HQ.METRICS_FINANCE.CONTRACT_ARR_MONTHLY WHERE EOM_DATE = (SELECT MAX(EOM_DATE) FROM HQ.METRICS_FINANCE.CONTRACT_ARR_MONTHLY)")
```

**Calls**: 3
**Expected time**: 15-20 seconds

**Important**: Always use `get_asset` before writing SQL to get accurate column names!

---

### Pattern 6: Filtered Discovery (1-2 calls)

**User asks**: "What tables are in the production namespace?"

```python
# Option A: If you know namespace name (1 call)
search_assets(
    asset_types=["snowflakeTable", "databricksTable", "bigQueryTable"],
    namespaces=["prod"],
    limit=100
)

# Option B: If you need to discover namespaces (2 calls)
# Call 1: Discover namespaces
filters = list_asset_filters(filter_type="namespace")

# Call 2: Search with discovered namespace
search_assets(
    asset_types=["snowflakeTable"],
    namespaces=["<production_namespace_from_filters>"],
    limit=100
)
```

**Calls**: 1-2
**Expected time**: 5-15 seconds

---

## Advanced Filters

### Use include_only_leaf_assets / include_only_root_assets

```python
# Find tables that aren't consumed by anything (leaf nodes)
search_assets(
    asset_types=["snowflakeTable"],
    include_only_leaf_assets=True,
    limit=50
)

# Find source tables (no upstream dependencies)
search_assets(
    asset_types=["snowflakeTable"],
    include_only_root_assets=True,
    limit=50
)
```

### Combine Multiple Filters

```python
# Production Snowflake tables owned by data-eng team
search_assets(
    asset_types=["snowflakeTable"],
    namespaces=["prod"],
    owners=["data-eng"],
    limit=100
)
```

---

## Response Format Guidelines

### Always Include Summary Stats

```markdown
Found 47 customer-related tables:
- Snowflake: 32 tables
- BigQuery: 15 tables

Top tables:
1. HQ.MART_CUST.CURRENT_ASTRO_CUSTS
2. HQ.DELIVERY.CUSTOMER_BOT_COLLECTED_DETAILS
...
```

### Don't Over-Fetch

If user asks "do we have customer tables?", don't fetch all 243 results. Fetch 20-50 and show them a representative sample.

```markdown
# Good response:
"Yes, found 243 customer-related tables. Here are the top 20:"

# Bad response:
"Let me fetch all 243 tables..." (makes 12+ API calls)
```

### Present Metadata from Search Results

```markdown
# search_assets already gives you:
- Table name (assetId)
- Asset type (warehouse)
- Namespace (deployment)
- Description

# Use this directly! Example:
| Table | Warehouse | Namespace | Description |
|-------|-----------|-----------|-------------|
| CUSTOMERS | Snowflake | prod | Customer data |
```

---

## When to Paginate

**Only paginate if**:
- ✅ User explicitly asks for "all results"
- ✅ User says "show me more"
- ✅ Total count is reasonable (<500) and user needs comprehensive list

**Don't paginate if**:
- ❌ User just asks "what customer tables exist?" (20-50 is enough)
- ❌ Total count is huge (>1000) - summarize instead
- ❌ User didn't ask for complete enumeration

**Pagination pattern** (when needed):
```python
# First call
page1 = search_assets(search="customer", limit=100, offset=0)

# Only if needed
if page1['total_assets'] > 100 and user_wants_more:
    page2 = search_assets(search="customer", limit=100, offset=100)
```

---

## SQL Execution

After discovering assets via the catalog, you can execute SQL queries to analyze the data.

### Available Functions

The kernel starts automatically on first Bash command. These functions are available:

| Function | Description |
|----------|-------------|
| `run_sql(query, limit=100)` | Execute SQL, return Polars DataFrame |
| `run_sql_pandas(query, limit=100)` | Execute SQL, return Pandas DataFrame |

### Example Workflow

```bash
# 1. Discover tables via catalog (Observe MCP)
search_assets(search="customer", asset_types=["snowflakeTable"])

# 2. Execute SQL on discovered table
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "df = run_sql('SELECT * FROM HQ.MART_CUST.CURRENT_ASTRO_CUSTS LIMIT 10')"
uv run ${CLAUDE_PLUGIN_ROOT}/skills/analyzing-data/scripts/cli.py exec "print(df)"
```

**Note**: For discovery, use Observe MCP. For querying data, use the kernel's `run_sql()`. Do NOT use schema discovery queries like `SHOW TABLES` or `INFORMATION_SCHEMA` - that's what the catalog is for.

---

## Limitations

- **Catalog Freshness**: Data may have slight latency (typically minutes) from event processing
- **Column Schema**: Use `get_asset` to retrieve column details (not available in `search_assets`)
- **Lineage Scope**: Only shows lineage captured by Airflow/OpenLineage

---

## Troubleshooting

**No results found**:
- Check spelling and try broader search terms
- Try without `asset_types` filter to see if assets exist
- Use `list_asset_filters` to discover available namespaces/DAGs

**Authentication errors**:
- Use `get_connection_info` to verify connection
- User needs to run `astro login` first
- Check that organization ID is correct

**Too many results**:
- Add more specific `search` terms
- Filter by `namespaces`, `dags`, or `owners`
- Use higher `limit` (50-100) to get more in one call

**Slow performance**:
- ✅ Check you're not making >5 tool calls
- ✅ Increase `limit` to reduce pagination
- ✅ Use search results directly instead of calling `get_asset`
- ✅ Combine filters in one call instead of multiple searches

---

## Performance Checklist

Before returning results, ask yourself:

- [ ] Did I use `limit=50` or higher? (Not 20)
- [ ] Did I use search results directly? (Not calling get_asset unnecessarily)
- [ ] Did I make 1-3 tool calls? (Not 5+)
- [ ] Did I only paginate if user needs more? (Not "just in case")
- [ ] Did I combine filters in one call? (Not multiple searches)

**Target**: 1-3 calls, 10-15 seconds per query
