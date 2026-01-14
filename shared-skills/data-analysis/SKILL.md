---
name: data-analysis
description: Perform data analysis using SQL queries. Use when the user wants to analyze data, answer business questions, create metrics, compare datasets, or investigate trends. Guides query construction and result interpretation.
---

# Data Analysis

Answer business questions and perform analysis using SQL queries against the data warehouse.

## Core Principle: Query Optimization

**Write optimized SQL queries when needed - ALWAYS prioritize smaller, faster queries over complex mega-queries.**

- Break complex analysis into multiple focused queries
- Use CTEs for readability, but avoid unnecessary nesting
- Filter early and aggressively with WHERE clauses
- Select only the columns you need, never SELECT *
- Use LIMIT during exploration, remove for final analysis
- Aggregate at the appropriate grain - don't over-fetch then reduce

## Analysis Process

### Step 1: Clarify the Question

Before writing any SQL, ensure you understand:
- **What metric/answer** is needed? (count, sum, rate, comparison?)
- **What time period** is relevant? (last 7 days, YTD, all-time?)
- **What grain** is expected? (per customer, per day, total?)
- **What filters** apply? (specific segment, region, product?)

If unclear, ask clarifying questions before proceeding.

### Step 2: Identify Data Sources

Use `explore` skill to find relevant tables.

⚠️ **CRITICAL: Before querying any large fact table, search for pre-aggregated tables first:**

```sql
-- Search for METRICS/MART/AGG tables that might already have what you need
SELECT table_schema, table_name, row_count, comment
FROM INFORMATION_SCHEMA.TABLES
WHERE (table_schema LIKE '%METRICS%' OR table_schema LIKE '%MART%' OR table_name LIKE '%AGG%')
  AND (LOWER(table_name) LIKE '%<concept>%' OR LOWER(comment) LIKE '%<concept>%')
```

Pre-aggregated tables are **orders of magnitude faster** and often contain exactly what you need. A metrics table with 100K rows will return in seconds; a fact table with 6B rows may timeout even with filters.

**Table selection principles:**
- **Check metrics/mart tables FIRST** - they exist for a reason
- Use row counts as a signal: millions+ rows = fact table (slow), thousands = config/metadata
- If a fact table has billions of rows, **never start with JOINs or GROUP BY**

**When multiple tables could work:**
- Run a quick `SELECT ... LIMIT 100` (no JOINs) to validate data exists
- If 0 results or timeout, try the next candidate table

### Step 3: Build Incrementally

**Start simple, then add complexity:**

```sql
-- Step 1: Verify you have the right data
SELECT COUNT(*) FROM table WHERE date_col >= '2024-01-01'

-- Step 2: Check a sample
SELECT col1, col2, col3 FROM table WHERE date_col >= '2024-01-01' LIMIT 10

-- Step 3: Build your aggregation
SELECT
    dimension_col,
    COUNT(*) as row_count,
    SUM(metric_col) as total
FROM table
WHERE date_col >= '2024-01-01'
GROUP BY dimension_col
ORDER BY total DESC
```

⚠️ **For tables with 100M+ rows, modify this pattern:**

```sql
-- Step 1: Simple filter check (NO JOINs, NO GROUP BY)
SELECT col1, col2, foreign_key FROM huge_table 
WHERE filter_col ILIKE '%term%' 
  AND date_col >= DATEADD(day, -30, CURRENT_DATE)
LIMIT 100

-- Step 2: Only if Step 1 succeeds, use the IDs you found
SELECT d.name, o.org_name
FROM dimension_table d
JOIN org_table o ON d.org_id = o.org_id
WHERE d.id IN ('id1', 'id2', 'id3')  -- IDs from Step 1
```

**If a query times out:** Remove JOINs, remove GROUP BY, add narrower date filters, add LIMIT. Don't give up - simplify.

### Step 4: Write Efficient Queries

#### Use Appropriate Filters
```sql
-- GOOD: Filter early
SELECT customer_id, SUM(amount)
FROM orders
WHERE order_date >= DATEADD(day, -30, CURRENT_DATE)
GROUP BY customer_id

-- BAD: Filter late (scans entire table)
SELECT customer_id, SUM(amount)
FROM orders
GROUP BY customer_id
HAVING MAX(order_date) >= DATEADD(day, -30, CURRENT_DATE)
```

#### Avoid SELECT *
```sql
-- GOOD: Select only needed columns
SELECT customer_id, order_date, amount
FROM orders

-- BAD: Selects everything, wastes resources
SELECT * FROM orders
```

#### Use Approximate Functions for Large Datasets
```sql
-- GOOD: Fast approximate count for exploration
SELECT APPROX_COUNT_DISTINCT(customer_id) FROM events

-- Use exact count only when precision matters
SELECT COUNT(DISTINCT customer_id) FROM events
```

#### Leverage Pre-Aggregated Tables
```sql
-- GOOD: Use daily aggregate table
SELECT SUM(daily_revenue) FROM daily_sales_summary

-- BAD: Aggregate from raw events (slower)
SELECT SUM(amount) FROM raw_transactions
```

### Step 5: Validate Results

Before presenting results, sanity-check:

1. **Row counts** - Does the number of rows make sense?
2. **Null handling** - Are NULLs being handled correctly?
3. **Duplicates** - Could joins be creating duplicates?
4. **Edge cases** - What about zero values, negative numbers?
5. **Time zones** - Are timestamps being handled consistently?

```sql
-- Quick validation query
SELECT
    COUNT(*) as total_rows,
    COUNT(DISTINCT id_col) as unique_ids,
    SUM(CASE WHEN metric_col IS NULL THEN 1 ELSE 0 END) as null_count,
    MIN(date_col) as earliest,
    MAX(date_col) as latest
FROM your_query_result
```

### Step 6: Present Findings

Structure your analysis output:

#### Summary
One paragraph answering the original question with key numbers highlighted.

#### Key Metrics
| Metric | Value | Context |
|--------|-------|---------|
| Total Revenue | $1.2M | +15% vs last month |
| Active Customers | 4,521 | Highest ever |
| Avg Order Value | $265 | Consistent with trend |

#### Supporting Data
Include the query results table, sorted meaningfully.

#### Query Used
Provide the final SQL query so it can be rerun or modified.

#### Caveats & Assumptions
- Time period analyzed: Jan 1 - Jan 31, 2024
- Excludes test accounts
- Revenue is gross, before refunds

## Common Analysis Patterns

### Trend Over Time
```sql
SELECT
    DATE_TRUNC('week', event_date) as week,
    COUNT(*) as events,
    COUNT(DISTINCT user_id) as unique_users
FROM events
WHERE event_date >= DATEADD(month, -3, CURRENT_DATE)
GROUP BY 1
ORDER BY 1
```

### Comparison (Period over Period)
```sql
SELECT
    CASE
        WHEN date_col >= DATEADD(day, -7, CURRENT_DATE) THEN 'This Week'
        ELSE 'Last Week'
    END as period,
    SUM(amount) as total,
    COUNT(DISTINCT customer_id) as customers
FROM orders
WHERE date_col >= DATEADD(day, -14, CURRENT_DATE)
GROUP BY 1
```

### Top N Analysis
```sql
SELECT
    customer_name,
    SUM(revenue) as total_revenue,
    COUNT(*) as order_count
FROM orders
JOIN customers USING (customer_id)
WHERE order_date >= '2024-01-01'
GROUP BY customer_name
ORDER BY total_revenue DESC
LIMIT 10
```

### Distribution / Histogram
```sql
SELECT
    FLOOR(amount / 100) * 100 as bucket,
    COUNT(*) as frequency
FROM orders
GROUP BY 1
ORDER BY 1
```

### Cohort Analysis
```sql
WITH first_purchase AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', MIN(order_date)) as cohort_month
    FROM orders
    GROUP BY customer_id
)
SELECT
    fp.cohort_month,
    DATE_TRUNC('month', o.order_date) as activity_month,
    COUNT(DISTINCT o.customer_id) as active_customers
FROM orders o
JOIN first_purchase fp USING (customer_id)
GROUP BY 1, 2
ORDER BY 1, 2
```

## Anti-Patterns to Avoid

### The Mega-Query
❌ Don't try to answer 5 questions in one query with complex CASE statements and multiple subqueries. 

✅ Run 5 simple queries instead - easier to debug, faster to run, clearer results.

### Over-Engineering
❌ Don't build a "flexible" query with optional parameters for every possible filter.

✅ Write a specific query for the specific question asked.

### Premature Optimization
❌ Don't spend time optimizing a query that runs once for ad-hoc analysis.

✅ Optimize queries that run repeatedly (dashboards, pipelines).

## Next Steps

After analysis is complete, suggest relevant follow-ups:
- "To dive deeper into table X, use the profile skill"
- "To understand where this data comes from, use the sources skill"
- "To set up automated monitoring, consider creating a dashboard"

