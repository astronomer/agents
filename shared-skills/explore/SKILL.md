---
name: explore
description: Discover and explore data for a concept or domain. Use when the user asks what data exists for a topic (e.g., "ARR", "customers", "orders"), wants to find relevant tables, or needs to understand what data is available before analysis.
---

# Data Exploration

Discover what data exists for a concept or domain. Answer "What data do we have about X?"

## Fast Table Validation

**When you have multiple candidate tables, quickly validate before committing to complex queries.**

### Strategy: Progressive Complexity

Start with the **simplest possible query**, then add complexity only after each step succeeds:

```
Step 1: Does the data exist?     → Simple LIMIT query, no JOINs
Step 2: How much data?           → COUNT(*) with same filters
Step 3: What are the key IDs?    → SELECT DISTINCT foreign_keys LIMIT 100
Step 4: Get related details      → JOIN on the specific IDs from step 3
```

**Never jump from step 1 to complex aggregations.** If step 1 returns 50 rows, use those IDs directly:

```sql
-- After finding deployment_ids in step 1:
SELECT o.org_name, d.deployment_name
FROM DEPLOYMENTS d
JOIN ORGANIZATIONS o ON d.org_id = o.org_id
WHERE d.deployment_id IN ('id1', 'id2', 'id3')  -- IDs from step 1
```

### When a Metadata Table Returns 0 Results

If a smaller metadata/config table (like `*_LOG`, `*_CONFIG`) returns 0 results, **check the execution/fact table** before concluding data doesn't exist.

Metadata tables may have gaps or lag. The actual execution data (in tables with millions/billions of rows) is often more complete.

### Use Row Counts as a Signal

When `list_tables` returns row counts:
- **Millions+ rows** → likely execution/fact data (actual events, transactions, runs)
- **Thousands of rows** → likely metadata/config (what's configured, not what happened)

For questions like "who is using X" or "how many times did Y happen", prioritize high-row-count tables first - they contain actual activity data.

⚠️ **CRITICAL: Tables with 1B+ rows require special handling**

If you see a table with billions of rows (like 6B), you MUST:
1. Use simple queries only: `SELECT col1, col2 FROM table WHERE filter LIMIT 100`
2. NO JOINs, NO GROUP BY, NO aggregations on the first query
3. Only add complexity after the simple query succeeds

**If your query times out**, simplify it - don't give up. Remove JOINs, remove GROUP BY, add LIMIT.

### Example: Finding Feature Usage

If looking for "customers using feature X" and you see:
- `FEATURE_CONFIG` (50K rows) - likely config/metadata
- `USER_EVENTS` (500M rows) - likely execution data

**Try the larger table first** with a quick validation:
```sql
SELECT COUNT(*) FROM USER_EVENTS WHERE feature ILIKE '%X%' AND event_ts >= DATEADD(day, -30, CURRENT_DATE)
```
If count > 0, proceed. If 0, try the config table.

### Querying Large Tables (100M+ rows)

**Pattern: Find examples first, aggregate later**

For billion-row tables, even ILIKE with date filters can timeout. Use LIMIT on a **simple query** (no JOINs, no GROUP BY):

```sql
-- Step 1: Find examples (fast - stops after finding matches)
-- NO JOINS, NO GROUP BY - just find rows
SELECT col_a, col_b, foreign_key_id
FROM huge_table
WHERE col_a ILIKE '%term%'
  AND ts >= DATEADD(day, -30, CURRENT_DATE)
LIMIT 100

-- Step 2: Use foreign keys from step 1 to get details
SELECT o.name, o.details
FROM other_table o
WHERE o.id IN ('id1', 'id2', 'id3')  -- IDs from step 1
```

**CRITICAL: LIMIT only helps without GROUP BY**

```sql
-- ❌ STILL SLOW: LIMIT with GROUP BY - must scan ALL rows first to compute groups
SELECT col, COUNT(*) FROM huge_table WHERE x ILIKE '%term%' GROUP BY col LIMIT 100

-- ✅ FAST: LIMIT without GROUP BY - stops after finding 100 rows
SELECT col, id FROM huge_table WHERE x ILIKE '%term%' LIMIT 100
```

**Anti-patterns for large tables:**
- ❌ JOINs + GROUP BY + LIMIT (LIMIT doesn't help)
- ❌ `UPPER(col) LIKE '%TERM%'` (use ILIKE instead)
- ❌ Wide date ranges without LIMIT

## Exploration Process

### Step 1: Search for Relevant Tables

Search across all schemas for tables matching the concept:

```sql
SELECT
    TABLE_CATALOG as database,
    TABLE_SCHEMA as schema,
    TABLE_NAME as table_name,
    ROW_COUNT,
    COMMENT as description
FROM <database>.INFORMATION_SCHEMA.TABLES
WHERE LOWER(TABLE_NAME) LIKE '%<concept>%'
   OR LOWER(COMMENT) LIKE '%<concept>%'
ORDER BY TABLE_SCHEMA, TABLE_NAME
LIMIT 30
```

Also check for related terms:
- Synonyms (e.g., "revenue" for "ARR", "client" for "customer")
- Abbreviations (e.g., "arr" for "annual recurring revenue")
- Related concepts (e.g., "orders" often relates to "customers")

### Step 2: Categorize by Data Layer

Group discovered tables by their role in the data architecture:

| Layer | Naming Patterns | Purpose |
|-------|-----------------|---------|
| **Raw/Staging** | `raw_`, `stg_`, `staging_` | Source data, minimal transformation |
| **Intermediate** | `int_`, `base_`, `prep_` | Cleaned, joined, business logic applied |
| **Marts/Facts** | `fct_`, `fact_`, `mart_` | Business metrics, analysis-ready |
| **Dimensions** | `dim_`, `dimension_` | Reference/lookup tables |
| **Aggregates** | `agg_`, `summary_`, `daily_` | Pre-computed rollups |
| **Reporting** | `rpt_`, `report_`, `dashboard_` | BI/reporting optimized |

### Step 3: Get Schema Details

For the most relevant tables (typically 2-5), use `get_tables_info` to retrieve:
- Column names and types
- Column descriptions
- Key fields

Focus on tables that appear to be:
- The "main" or canonical source
- Most recent/actively maintained
- Appropriate grain for analysis

### Step 4: Understand Relationships

Identify how tables relate to each other:

```sql
-- Look for common key columns
SELECT COLUMN_NAME, COUNT(*) as table_count
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN (<discovered_tables>)
GROUP BY COLUMN_NAME
HAVING COUNT(*) > 1
ORDER BY table_count DESC
```

Common relationship patterns:
- `customer_id` joins customer tables
- `order_id` joins order tables
- `date` or `event_date` for time-series alignment

### Step 5: Check Data Freshness

For key tables, verify they're actively maintained:

```sql
SELECT
    MAX(<timestamp_column>) as last_update,
    COUNT(*) as row_count
FROM <table>
```

Flag tables that:
- Haven't been updated recently
- Have suspiciously low row counts
- Might be deprecated

### Step 6: Sample the Data

For the primary table(s), get sample rows to understand content:

```sql
SELECT * FROM <table> LIMIT 10
```

## Output: Exploration Report

### Summary
One paragraph explaining what data exists for this concept and which tables are most useful.

### Discovered Tables

| Table | Schema | Rows | Last Updated | Purpose |
|-------|--------|------|--------------|---------|
| `acct_product_arr` | MART_FINANCE | 42K | Today | Primary ARR by account/product |
| `usage_arr_daily` | METRICS | 800K | Today | Daily usage-based ARR detail |
| `arr_change_multi` | METRICS | 15K | Today | ARR movement tracking |

### Recommended Tables

**For most analysis, use:** `MART_FINANCE.ACCT_PRODUCT_ARR`
- Monthly grain, account-level
- Includes both contract and usage ARR
- Has current month flag for easy filtering

**For daily granularity:** `METRICS_FINANCE.USAGE_ARR_DAILY`
- Day-level detail
- Usage/consumption based ARR only

**For ARR movements:** `METRICS_FINANCE.ARR_CHANGE_MULTI`
- New, expansion, contraction, churn
- Good for cohort analysis

### Key Schema Details

For the primary table(s), show:

| Column | Type | Description |
|--------|------|-------------|
| `acct_id` | VARCHAR | Account identifier |
| `arr_amt` | NUMBER | Total ARR amount |
| `eom_date` | DATE | End of month date |

### Relationships

```
[dim.customers] --< [fct.orders] --< [agg.daily_sales]
       |                  |
       +--< [fct.arr] ----+
```

### Sample Queries

Provide 3-5 starter queries for common questions:

```sql
-- Total ARR by product
SELECT product, SUM(arr_amt) as total_arr
FROM mart_finance.acct_product_arr
WHERE is_current_mth = TRUE
GROUP BY product;

-- Top 10 customers
SELECT parent_name, SUM(arr_amt) as arr
FROM mart_finance.acct_product_arr
WHERE is_current_mth = TRUE
GROUP BY parent_name
ORDER BY arr DESC
LIMIT 10;
```

### Next Steps

Suggest logical follow-ups:
- "To deep-dive on a specific table, use the profile skill"
- "To check data freshness, use the freshness skill"
- "To understand where this data comes from, use the sources skill"
