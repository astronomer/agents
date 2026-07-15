---
name: analyzing-data
description: Queries the data warehouse with SQL and answers business questions about data. Use when answering anything that needs warehouse data - counts, metrics, trends, aggregations, joins across tables, data lookups, or ad-hoc SQL analysis (for example "who uses X", "how many Y", "show me Z", "find customers", "what is the count").
---

# Data Analysis

Answer business questions by querying the data warehouse. The kernel auto-starts on first `exec` call.

**All CLI commands below are relative to this skill's directory.** Before running any `scripts/cli.py` command, `cd` to the directory containing this file.

## Workflow

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

5. **Cache learnings** — Always cache before presenting results:
   ```bash
   # Cache concept → table mapping
   uv run scripts/cli.py concept learn <concept> <TABLE> -k <KEY_COL>
   # Cache query strategy (if discovery was needed)
   uv run scripts/cli.py pattern learn <name> -q "question" -s "step" -t "TABLE" -g "gotcha"
   ```

6. **Present findings** to user.

## Kernel Functions

| Function | Returns |
|----------|---------|
| `run_sql(query, limit=100)` | Polars DataFrame |
| `run_sql_pandas(query, limit=100)` | Pandas DataFrame |
| `run_sql_many(queries, limit=100)` | List of Polars DataFrames (one per query) |

`pl` (Polars) and `pd` (Pandas) are pre-imported.

**Run independent queries together** with `run_sql_many` — they execute concurrently (Snowflake async / connection-pool fan-out) instead of one at a time:

```bash
uv run scripts/cli.py exec "dfs = run_sql_many(['SELECT ...', 'SELECT ...']); print(dfs[0])"
```

`run_sql_many` is **fail-fast**: if any query errors, the call raises and the results of the queries that succeeded are discarded. Use separate `run_sql` calls if you need partial results.

**Timeouts:** `exec` waits up to 120s by default, then interrupts the query and returns a "client stopped waiting" message (the query may still finish server-side). Raise it for known long-running queries: `uv run scripts/cli.py exec "..." -t 600`.

**Idle kernel:** the kernel self-terminates after 2h idle (preserving state until then). Override with `ASTRO_KERNEL_IDLE_TIMEOUT` (seconds; `0` disables).

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
