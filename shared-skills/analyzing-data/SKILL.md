---
name: analyzing-data
description: Queries data warehouse and answers business questions about data. Handles questions requiring database/warehouse queries including "who uses X", "how many Y", "show me Z", "find customers", "what is the count", data lookups, metrics, trends, or SQL analysis.
---

# Data Analysis

Answer business questions by finding the right table, then querying it.

## ⚠️ MANDATORY FIRST STEP - DO THIS BEFORE ANYTHING ELSE

**STOP. Before calling ANY other tool, you MUST call `lookup_pattern` first:**

```
lookup_pattern("<user's question here>")
```

This is NON-NEGOTIABLE. Do not call `lookup_concept`, `list_schemas`, `list_tables`, or `run_sql` until you have checked for patterns.

**Why?** Patterns contain proven strategies that save 5-10 tool calls and avoid timeouts. Skipping this wastes time and may lead to failed queries.

---

## Workflow

Copy this checklist and check off items as you complete them:

```
Analysis Progress:
- [ ] Step 1: lookup_pattern (check for cached strategy)
- [ ] Step 2: Grep codebase for table definitions
- [ ] Step 3: Read SQL file to get table/column names
- [ ] Step 4: run_sql query
- [ ] Step 5: learn_concept (ALWAYS - before presenting results)
- [ ] Step 6: learn_pattern (ALWAYS if discovery required - before presenting results)
- [ ] Step 7: record_pattern_outcome (if you used a pattern in Step 1)
- [ ] Step 8: Present results to user
```

## ⚠️ MANDATORY: Complete Steps 5-7 BEFORE Presenting Results

**DO NOT write any summary or results to the user until you have:**
1. ✅ Called `learn_concept(...)` - ALWAYS, no exceptions
2. ✅ Called `learn_pattern(...)` - ALWAYS if query required discovery (3+ tool calls)
3. ✅ Called `record_pattern_outcome(...)` - If you used a pattern from Step 1

**This is a HARD GATE.** Present results only after caching is complete.

### Step 1: Check cached patterns

```
lookup_pattern("<user's question>")
```

If `found: true` → follow returned strategy, skip to Step 4.

### Step 2: Search codebase for table definitions

**Run this Grep before using ANY warehouse MCP tools.**

```
Grep pattern="<concept>" glob="**/*.sql"
```

Example for ARR question:
```
Grep pattern="ARR" glob="dags/declarative/**/*.sql"
```

| Repo Type | Where to Look |
|-----------|---------------|
| **Gusty** | `dags/declarative/04_metric/`, `06_reporting/`, `05_mart/` |
| **dbt** | `models/marts/`, `models/staging/` |

### Step 3: Read the SQL file

When Grep finds matches, read the SQL file to get:
- Exact table name from the `schema:` frontmatter
- Available columns from the SELECT
- Any important filters or joins

### Step 4: Query the warehouse

```
run_sql("<query>")
```

**Query tips:**
- Use LIMIT during exploration
- Filter early with WHERE
- Prefer pre-aggregated tables (`METRICS_*`, `MART_*`, `AGG_*`) over raw fact tables
- For 100M+ row tables: no JOINs or GROUP BY on first query (see [reference/discovery-warehouse.md](reference/discovery-warehouse.md))

### Step 5: Cache the concept (ALWAYS)

**⚠️ MANDATORY after EVERY successful query - do this BEFORE presenting results:**

```
learn_concept(concept="<topic>", table="DB.SCHEMA.TABLE", key_column="id", date_column="created_at")
```

### Step 6: Save pattern (MANDATORY if discovery required)

**⚠️ MANDATORY if ANY of these are true:**
- Query required 3+ tool calls
- You discovered something non-obvious (e.g., specific filters needed)
- Initial approach failed/timed out and you found a better way
- Query involved a large table with specific filtering strategies

**Do NOT ask the user. Just save it.**

```
learn_pattern(
    pattern_name="<name>",
    question_types=["who uses X", "how many X"],
    strategy=["Step 1...", "Step 2..."],
    tables_used=["DB.SCHEMA.TABLE"],
    gotchas=["What to avoid"],
    example_query="<working SQL>"
)
```

### Step 7: Record pattern outcome (if you used a pattern)

**If Step 1 returned a pattern and you used it:**

```
record_pattern_outcome("pattern_name", success=True)   # or False if it didn't help
```

This tracks pattern effectiveness - patterns with poor success rates get flagged.

### Step 8: Present results

**Only after completing Steps 5-7**, present results to the user:

| Section | Content |
|---------|---------|
| **Summary** | One paragraph answer |
| **Key Metrics** | Table with values |
| **Query** | SQL for reuse |

---

## Using cached patterns

When `lookup_pattern` returns `found: true`:
1. Follow the `strategy` steps
2. Use `tables_used` directly (skip discovery)
3. Avoid the `gotchas`
4. Adapt `example_query` for user's specific question
5. **Call `record_pattern_outcome(name, success=True/False)` after** ← Don't forget!

---

## Complete Flow Examples

### With Pattern (fast path)

```
1. User asks: "Who uses S3Operator?"
2. lookup_pattern("who uses S3Operator") → Found! "operator_usage" pattern
3. Follow pattern strategy:
   - Use TASK_RUNS (not DEPLOYMENT_OPERATOR_LOG)
   - ILIKE '%S3%' for variants
   - Add 90-day date filter
4. run_sql(...) → Success!
5. record_pattern_outcome("operator_usage", success=True)  ← REQUIRED
```

### Without Pattern (first time discovery)

```
1. User asks: "Who uses FeatureX?"
2. lookup_pattern(...) → Not found
3. lookup_concept("featurex") → Not found
4. Discovery: Grep codebase → Read SQL file → Find TASK_RUNS
5. run_sql(...) → Times out! Try with date filter → Success!
6. learn_concept("featurex", "HQ.MODEL_ASTRO.TASK_RUNS", ...)  ← REQUIRED
7. learn_pattern("operator_usage", ...) ← REQUIRED (discovery took 3+ calls)
8. Present results to user
```

---

## Cache Tools Reference

| Tool | When to Use |
|------|-------------|
| `lookup_pattern("question")` | **FIRST** - check for proven strategy |
| `record_pattern_outcome(name, success)` | **AFTER using pattern** - track effectiveness |
| `learn_pattern(...)` | After non-trivial query - save strategy |
| `lookup_concept("X")` | Check if we know which table has concept X |
| `learn_concept(...)` | **AFTER successful query** - save concept → table |
| `get_cached_table("DB.SCHEMA.TABLE")` | Get cached column info for a table |
| `list_patterns()` | See all saved patterns |
| `cache_status()` | Debug - see what's cached |
| `clear_cache()` | Reset if cache is stale |

---

## Fallback: Warehouse discovery

Only if Step 2 Grep returned no results:

```
lookup_concept("<concept>")
list_schemas()
list_tables(database, schema)
get_tables_info(database, schema, [tables])
```

---

## Reference

- [reference/discovery-warehouse.md](reference/discovery-warehouse.md) - Large table handling
- [reference/common-patterns.md](reference/common-patterns.md) - SQL templates
