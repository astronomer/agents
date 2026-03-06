---
name: analyzing-data
description: Queries data warehouse and answers business questions about data. Handles questions requiring database/warehouse queries including "who uses X", "how many Y", "show me Z", "find customers", "what is the count", data lookups, metrics, trends, or SQL analysis.
---

# Data Analysis

Answer business questions by querying the data warehouse. Uses the Observe catalog for fast discovery when available, with SQL-based fallback.

**All CLI commands below are relative to this skill's directory.** Before running any `scripts/cli.py` command, `cd` to the directory containing this file.

## Step 0: Check Observe MCP Availability

**Before doing any discovery work**, check if `Observe_ListAssets` is available in your tool list.

- **Available** → Use the **Observe-Assisted Workflow** (faster, cross-warehouse discovery)
- **Not available** → Use the **SQL-Only Workflow** (INFORMATION_SCHEMA + pattern/concept cache)

The check result applies for the entire conversation. Do not re-check on every question.

---

## Observe-Assisted Workflow

Use this when the Observe MCP tools are available. Observe provides fast catalog search across all warehouses; SQL provides actual data retrieval.

### Workflow

1. **Discover tables** via `Observe_ListAssets`
2. **Get column schema** via `Observe_GetAsset` (before writing SQL)
3. **Execute SQL** via `run_sql()` to get actual data
4. **Cache learnings** (see [Caching](#shared-caching) below)
5. **Present findings** to user

### Handling Observe Errors

- **"Observe is not enabled"** or **403/feature-not-enabled** → Tell the user: *"Astro Observe isn't enabled on your organization. Visit https://www.astronomer.io/product/observe/ to learn more and enable it."* Then fall back to the **SQL-Only Workflow**.
- **Auth errors (401/expired token)** → Tell the user to run `astro login` to refresh their token, then retry.
- **Table found in catalog but `run_sql` fails** → The table may be in a warehouse the user hasn't configured credentials for. Run `uv run scripts/cli.py warehouse list` and tell them which warehouse connection is missing.

### Discovery (Observe MCP Tools)

#### `Observe_ListAssets` — Primary Discovery Tool

Search and filter catalog assets. Returns rich metadata — often enough without a follow-up call.

**Parameters** (all optional):
- `search` (string): Full-text search query
- `assetTypes` (string): Comma-separated types: `snowflakeTable`, `databricksTable`, `bigQueryTable`, `airflowDag`, `airflowTask`, `airflowDataset`, `openLineageDataset`
- `namespaces` (string): Comma-separated deployment namespace filter
- `dags` (string): Comma-separated DAG ID filter
- `dagTags` (string): Comma-separated DAG tag filter
- `owners` (string): Comma-separated owner filter
- `includeOnlyLeafAssets` (boolean): Only leaf assets (no downstream deps)
- `includeOnlyRootAssets` (boolean): Only root assets (no upstream deps)
- `limit` (number): Max results (default: 20, **recommend 50-100**)
- `offset` (number): Pagination offset

**Returns** JSON with: `totalCount`, `limit`, `offset`, `assets[]` (each with `id`, `name`, `type`, `namespace`, `description`, `deploymentDetails`, `workspaceDetails`, `metadata`)

#### `Observe_GetAsset` — Column Schema & Detail Lookup

Get full details for a specific asset including **column definitions**.

**When to use**: Before writing SQL (to get accurate column names/types), for lineage, ownership details.
**When NOT to use**: Just listing tables — use `Observe_ListAssets` results directly.

**Parameters**:
- `assetId` (string, required): The asset FQDN from `Observe_ListAssets` results (`id` field)

**Returns**: Full asset details including `columns` (names, types, descriptions), `connectionAcct`, `database`, `schema`, `tableName`, lineage, etc.

### Observe Performance Best Practices

**Target: 1-3 tool calls per query.** If you're making >5 calls, you're doing it wrong.

- Use `limit=50` or higher (not 20)
- Use search results directly — don't call `Observe_GetAsset` unless you need column schema or lineage
- Combine filters: `assetTypes="snowflakeTable,databricksTable,bigQueryTable"` instead of 3 separate calls
- Only paginate if the user explicitly asks for more results
- Don't call `Observe_GetAsset` in loops

### Example: "How many customers use Airflow 3?"

```
1. Observe_ListAssets(search="deployment", assetTypes="snowflakeTable")
   → Finds DEPLOYMENTS table (FQN varies by warehouse)

2. Observe_GetAsset(assetId="<id from step 1>")
   → Returns columns: ORG_ID, AIRFLOW_VERSION, DEPLOYMENT_ID, etc.

3. run_sql("SELECT COUNT(DISTINCT ORG_ID) FROM <table FQN> WHERE AIRFLOW_VERSION LIKE '3%'")
   → Returns actual count
```

---

## SQL-Only Workflow

Use this when the Observe MCP is not available. Relies on pattern/concept caches and INFORMATION_SCHEMA queries.

### Workflow

1. **Pattern lookup** — Check for a cached query strategy:
   ```bash
   uv run scripts/cli.py pattern lookup "<user's question>"
   ```
   If a pattern exists, follow its strategy. Record the outcome after executing:
   ```bash
   uv run scripts/cli.py pattern record <name> --success  # or --failure
   ```

2. **Concept lookup** — Find known table mappings:
   ```bash
   uv run scripts/cli.py concept lookup <concept>
   ```

3. **Table discovery** — If cache misses, search the codebase (`Grep pattern="<concept>" glob="**/*.sql"`) or query `INFORMATION_SCHEMA`. See [reference/discovery-warehouse.md](reference/discovery-warehouse.md).

4. **Execute query**:
   ```bash
   uv run scripts/cli.py exec "df = run_sql('SELECT ...')"
   uv run scripts/cli.py exec "print(df)"
   ```

5. **Cache learnings** (see [Caching](#shared-caching) below)

6. **Present findings** to user.

---

## Shared: SQL Execution

Both workflows use the same kernel for SQL execution. The kernel auto-starts on first `exec` call.

### Kernel Functions

| Function | Returns |
|----------|---------|
| `run_sql(query, limit=100)` | Polars DataFrame |
| `run_sql_pandas(query, limit=100)` | Pandas DataFrame |

`pl` (Polars) and `pd` (Pandas) are pre-imported.

### Example

```bash
uv run scripts/cli.py exec "df = run_sql('SELECT * FROM HQ.MART_CUST.CURRENT_ASTRO_CUSTS LIMIT 10')"
uv run scripts/cli.py exec "print(df)"
```

---

## Shared: Caching

Both workflows should cache learnings for future queries.

```bash
# Cache concept → table mapping
uv run scripts/cli.py concept learn <concept> <TABLE> -k <KEY_COL>
# Cache query strategy
uv run scripts/cli.py pattern learn <name> -q "question" -s "step" -t "TABLE" -g "gotcha"
```

**Tip**: Even with Observe discovery, cache the concept/table mapping so future queries skip the catalog lookup.

---

## CLI Reference

### Kernel

```bash
uv run scripts/cli.py warehouse list      # List warehouses
uv run scripts/cli.py start [-w name]     # Start kernel (with optional warehouse)
uv run scripts/cli.py exec "..."          # Execute Python code
uv run scripts/cli.py status              # Kernel status
uv run scripts/cli.py restart             # Restart kernel
uv run scripts/cli.py stop                # Stop kernel
uv run scripts/cli.py install <pkg>       # Install package
```

### Concept Cache

```bash
uv run scripts/cli.py concept lookup <name>                     # Look up
uv run scripts/cli.py concept learn <name> <TABLE> -k <KEY_COL> # Learn
uv run scripts/cli.py concept list                               # List all
uv run scripts/cli.py concept import -p /path/to/warehouse.md   # Bulk import
```

### Pattern Cache

```bash
uv run scripts/cli.py pattern lookup "question"                                      # Look up
uv run scripts/cli.py pattern learn <name> -q "..." -s "..." -t "TABLE" -g "gotcha"  # Learn
uv run scripts/cli.py pattern record <name> --success                                # Record outcome
uv run scripts/cli.py pattern list                                                   # List all
uv run scripts/cli.py pattern delete <name>                                          # Delete
```

### Table Schema Cache

```bash
uv run scripts/cli.py table lookup <TABLE>            # Look up schema
uv run scripts/cli.py table cache <TABLE> -c '[...]'  # Cache schema
uv run scripts/cli.py table list                       # List cached
uv run scripts/cli.py table delete <TABLE>             # Delete
```

### Cache Management

```bash
uv run scripts/cli.py cache status                # Stats
uv run scripts/cli.py cache clear [--stale-only]  # Clear
```

## References

- [reference/discovery-warehouse.md](reference/discovery-warehouse.md) — Large table handling, warehouse exploration, INFORMATION_SCHEMA queries
- [reference/common-patterns.md](reference/common-patterns.md) — SQL templates for trends, comparisons, top-N, distributions, cohorts

## Troubleshooting

### Observe not enabled on org
- Tell the user: *"Astro Observe isn't enabled on your organization. Visit https://www.astronomer.io/product/observe/ to learn more and enable it."*
- Fall back to SQL-Only Workflow

### Observe MCP auth errors
- User needs to run `astro login` first (tokens expire ~1 hour)
- Check that `ASTRO_ORG_ID` is correct or configured in `~/.astro/config.yaml`
- Fall back to SQL-Only Workflow if unresolvable

### Warehouse credentials not configured
- Run `uv run scripts/cli.py warehouse list` to check available connections
- Config lives at `~/.astro/agents/warehouse.yml`
