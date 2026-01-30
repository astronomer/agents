# Benchmarks

Performance benchmarks for asset discovery and search.

## Available Benchmarks

1. **[Asset Search Comparison](./README.md#asset-search-comparison)** - Warehouse Direct vs Observe Catalog
2. **[Model Performance](./MODEL_BENCHMARK_README.md)** - Opus vs Sonnet vs Haiku

---

## Asset Search Comparison

Compares performance and capabilities of different approaches to discovering data assets.

## Approaches

### 1. Warehouse Direct
- **Method**: SQL queries to INFORMATION_SCHEMA in Snowflake/Databricks/BigQuery
- **Pros**: Real-time data, detailed schema information
- **Cons**: Separate query per warehouse, no cross-warehouse search, no Airflow lineage

### 2. Observe Catalog
- **Method**: Astro Observability centralized catalog API
- **Pros**: Single query for cross-warehouse search, includes Airflow lineage, no credentials needed
- **Cons**: May have slight latency from event processing

## Test Scenarios

1. **search_by_keyword**: Find tables containing "customer"
2. **list_all_snowflake_tables**: List all Snowflake tables
3. **cross_warehouse_search**: Search across Snowflake, Databricks, BigQuery
4. **airflow_assets**: Find Airflow DAGs and tasks
5. **search_with_pagination**: Large result set (500+ results)

## Running Benchmarks

### Prerequisites

```bash
# Install dependencies
pip install snowflake-connector-python  # Optional, for warehouse benchmarks

# Authenticate with Astro (for observe catalog benchmarks)
astro login
```

### Run All Benchmarks

```bash
# With both approaches
python asset_search_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --snowflake-account your-account \
  --snowflake-user your-user \
  --snowflake-password your-password

# Observe only (no warehouse credentials needed)
python asset_search_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v

# Custom output file
python asset_search_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --output my_results.json
```

### Example Output

```
============================================================
Scenario: cross_warehouse_search
Description: Search across all warehouse types
============================================================

[Warehouse Direct]
  ✓ 45 results in 234.56ms
    Queries: 1
  ❌ Databricks not implemented
  ❌ BigQuery not implemented

[Observe Catalog]
  ✓ 127 results in 89.34ms
    Queries: 1
    Total available: 127

================================================================================
BENCHMARK SUMMARY
================================================================================

📊 Average Performance:
--------------------------------------------------------------------------------
Warehouse Direct:
  - Avg time: 234.56ms
  - Avg queries per scenario: 1.0
  - Scenarios tested: 3

Observe Catalog:
  - Avg time: 89.34ms
  - Avg queries per scenario: 1.0
  - Scenarios tested: 5

🎯 Key Advantages:
--------------------------------------------------------------------------------
Observe Catalog:
  ✓ Single query for cross-warehouse search
  ✓ Unified API across Snowflake, Databricks, BigQuery
  ✓ Includes Airflow lineage (DAGs, tasks, datasets)
  ✓ Centralized catalog with consistent metadata
  ✓ No warehouse credentials needed

Warehouse Direct:
  ✓ Real-time data (always current)
  ✓ Detailed schema information
  ✓ Access to warehouse-specific metadata
  ✗ Requires separate query per warehouse
  ✗ No cross-warehouse search capability
  ✗ No Airflow lineage information

💾 Results saved to: benchmark_results.json
```

## Metrics Collected

Each benchmark result includes:
- `scenario`: Test scenario name
- `approach`: "warehouse_direct" or "observe_catalog"
- `execution_time_ms`: Query execution time in milliseconds
- `num_queries`: Number of API calls/SQL queries required
- `num_results`: Number of results returned
- `error`: Error message if query failed
- `metadata`: Additional context (query text, total count, etc.)

## Analyzing Results

Results are saved to `benchmark_results.json` for further analysis:

```python
import json
import pandas as pd

# Load results
with open('benchmark_results.json') as f:
    results = json.load(f)

# Convert to DataFrame for analysis
df = pd.DataFrame(results)

# Compare average execution time by approach
df.groupby('approach')['execution_time_ms'].mean()

# Compare query counts
df.groupby('approach')['num_queries'].sum()

# Success rate by approach
df.groupby('approach')['error'].apply(lambda x: (x.isna().sum() / len(x)) * 100)
```

## Adding New Scenarios

Add to the `SCENARIOS` list in `asset_search_benchmark.py`:

```python
SearchScenario(
    name="my_scenario",
    description="What this scenario tests",
    search_term="optional_keyword",
    asset_types=["snowflakeTable"],  # Optional filter
    limit=100,  # Max results
)
```

## Future Enhancements

- [ ] Add Databricks and BigQuery warehouse implementations
- [ ] Test concurrent query performance
- [ ] Measure result freshness/staleness
- [ ] Add network latency simulation
- [ ] Test with production-scale datasets (millions of assets)
- [ ] Compare result quality (completeness, accuracy)
