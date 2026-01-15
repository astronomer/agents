# /data:init Performance Benchmark

Comparison of query performance **with** and **without** the `warehouse.md` schema file.

## Test Query

> "Who uses HITLOperator the most?"

This query requires:
1. Finding the right table (TASK_RUNS)
2. Understanding it has an OPERATOR column
3. Knowing it's a large table (6.2B rows) requiring date filters
4. Joining with ORGANIZATIONS for customer names

---

## Results

| Metric | WITHOUT warehouse.md | WITH warehouse.md | Improvement |
|--------|---------------------|-------------------|-------------|
| **Total Duration** | 95.7 sec | 27.0 sec | **3.5x faster** |
| **Tool Calls** | 7 | 3 | **57% fewer** |
| **Discovery Calls** | 6 | 1 | **83% fewer** |
| **Tokens (est.)** | ~15,000 | ~4,000 | **73% fewer** |

---

## Detailed Breakdown

### WITHOUT warehouse.md (Baseline)

| Step | Tool | Purpose | Time Impact |
|------|------|---------|-------------|
| 1 | `Glob` | Check for warehouse.md | - |
| 2 | `run_sql` | Check cache | - |
| 3 | `Grep` | Search codebase for SQL models | Network I/O |
| 4 | `list_schemas` | Discover all schemas | **Warehouse query** |
| 5 | `list_tables` | List tables in MODEL_ASTRO | **Warehouse query** |
| 6 | `get_tables_info` | Get column details | **Warehouse query** |
| 7 | `run_sql` | Execute actual query | **Warehouse query** |

**Total tool calls:** 7
**Warehouse queries:** 4
**Context consumed:** ~15,000 tokens (schema metadata returned in full)

### WITH warehouse.md (Optimized)

| Step | Tool | Purpose | Time Impact |
|------|------|---------|-------------|
| 1 | `Glob` | Check for warehouse.md | - |
| 2 | `Read` | Read Quick Reference table | **Local file** |
| 3 | `run_sql` | Execute actual query | **Warehouse query** |

**Total tool calls:** 3
**Warehouse queries:** 1
**Context consumed:** ~4,000 tokens (only read ~100 lines of markdown)

---

## Why This Matters

### 1. Faster Response Time
- 3.5x faster end-to-end
- Discovery phase eliminated (no list_schemas, list_tables, get_tables_info)
- Only the actual query hits the warehouse

### 2. Lower Token Usage
- 73% fewer tokens consumed
- Less context = more room for complex queries
- Cheaper API costs for production use

### 3. Better Accuracy
- Pre-populated Quick Reference provides consistent table mappings
- Warnings about large tables (>100M rows) prevent timeouts
- Date filter columns explicitly documented

### 4. Team Knowledge Sharing
- `warehouse.md` is version-controllable
- Team can add business context via comments
- New team members benefit immediately

---

## Sample warehouse.md Quick Reference

```markdown
## Quick Reference

| Concept | Table | Key Column | Date Column |
|---------|-------|------------|-------------|
| customers | HQ.MART_CUST.CURRENT_ASTRO_CUSTS | ACCT_ID | - |
| organizations | HQ.MODEL_ASTRO.ORGANIZATIONS | ORG_ID | CREATED_TS |
| task_runs | HQ.MODEL_ASTRO.TASK_RUNS | - | START_TS |
| dag_runs | HQ.MODEL_ASTRO.DAG_RUNS | - | START_TS |
```

With this reference, the agent immediately knows:
- Which table to query
- What date column to filter on (critical for billion-row tables)
- How to join tables (key columns)

---

## How to Reproduce

```bash
# Run /data:init to generate warehouse.md
cd your-project
claude
> /data:init-warehouse

# Test a query
> Who uses HITLOperator the most?
```

---

## Conclusion

The `/data:init` command provides:

| Benefit | Impact |
|---------|--------|
| Faster queries | 3.5x improvement |
| Fewer tool calls | 57% reduction |
| Lower token usage | 73% reduction |
| Better accuracy | Explicit warnings for large tables |
| Team collaboration | Version-controllable schema docs |

**Recommendation:** Run `/data:init` once per project, refresh when schema changes.
