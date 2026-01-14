---
name: discover-data
description: Discover and explore data for a concept or domain. Use when the user asks what data exists for a topic (e.g., "ARR", "customers", "orders"), wants to find relevant tables, or needs to understand what data is available before analysis.
---

# Data Exploration

Discover what data exists for a concept or domain. Answer "What data do we have about X?"

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
