# Benchmarks

Performance benchmarks for asset discovery and search.

## Available Benchmarks

1. **[Warehouse vs Observe (with Validation)](#warehouse-vs-observe-benchmark)** - Proper benchmark with ground truth validation ⭐ NEW
2. **[Asset Search Comparison](#asset-search-comparison)** - Legacy benchmark (no validation)
3. **[Model Performance](./MODEL_BENCHMARK_README.md)** - Opus vs Sonnet vs Haiku

---

## Warehouse vs Observe Benchmark

**NEW**: Proper benchmark comparing Warehouse SQL vs Observe Semantic Search with ground truth validation.

### Key Features

- **Ground truth validation**: Results validated against pre-computed correct answers
- **Quality metrics**: Precision, recall, F1 score (not just speed/cost)
- **True comparison**: Warehouse actually runs SQL, Observe uses semantic search

### Quick Start

```bash
# 1. Generate ground truth (requires warehouse connection)
python ground_truth.py --use-kernel

# 2. Run benchmark
python warehouse_vs_observe_benchmark.py --org-id <YOUR_ORG_ID>
```

### Files

| File | Description |
|------|-------------|
| `warehouse_vs_observe_benchmark.py` | Main benchmark runner |
| `ground_truth.py` | Generate ground truth from warehouse |
| `validation.py` | Validation utilities (extract tables, calculate P/R/F1) |
| `PROPER_BENCHMARK_DESIGN.md` | Detailed design documentation |

### Metrics

| Category | Metrics |
|----------|---------|
| **Performance** | Time (ms), Turns, Cost ($) |
| **Quality** | Precision, Recall, F1 Score |

### Example Output

```
══════════════════════════════════════════════════════════════════════
Scenario: find_customer_tables
──────────────────────────────────────────────────────────────────────

Metric               Warehouse            Observe
────────────────────────────────────────────────────────────────
Time                 8523ms               12341ms
Turns                3                    2
Cost                 $0.0234              $0.0187
Precision            95.2%                87.3%
Recall               78.4%                92.1%
F1 Score             85.9%                89.6%

Winner: OBSERVE (F1: 89.6% vs 85.9%)
```

See `PROPER_BENCHMARK_DESIGN.md` for full documentation.

---

## Asset Search Comparison

Compares performance and capabilities of two skill-based approaches to discovering data assets.

## Approaches

Both approaches use Claude Code skills to ensure fair comparison of the underlying mechanisms.

### 1. Catalog Skill (analyzing-data-observe)
- **Method**: Uses Observe MCP to query Astro Observability centralized catalog
- **Skill**: `analyzing-data-observe`
- **MCP**: `astro-observe-mcp`
- **Pros**:
  - Single query for cross-warehouse search
  - Includes Airflow lineage (DAGs, tasks, datasets)
  - No warehouse credentials needed
  - Fast metadata lookups
- **Cons**:
  - Cannot execute SQL queries
  - May have slight latency from event processing
  - Limited column-level details

### 2. Warehouse Skill (analyzing-data)
- **Method**: Direct SQL queries to INFORMATION_SCHEMA in each warehouse
- **Skill**: `analyzing-data`
- **Connection**: Direct warehouse connections (Snowflake, Postgres, etc.)
- **Pros**:
  - Real-time data, always current
  - Detailed schema information
  - Can execute SQL queries for data analysis
- **Cons**:
  - Separate query per warehouse
  - No cross-warehouse search capability
  - No Airflow lineage information
  - Requires warehouse credentials

## Test Scenarios

1. **find_customer_tables**: Find all tables related to customers
2. **list_snowflake_tables**: List all Snowflake tables (first 20)
3. **cross_warehouse_search**: Search across Snowflake, Databricks, BigQuery with summary by type
4. **find_airflow_lineage**: Find Airflow DAGs that produce data
5. **table_metadata**: Get ownership and deployment info for customer tables

## Running Benchmarks

### Prerequisites

```bash
# Authenticate with Astro (required for catalog approach)
astro login

# Configure warehouse credentials (required for warehouse approach)
# See skills/analyzing-data/SKILL.md for warehouse setup
```

### Run Benchmarks

```bash
# Test both approaches (requires warehouse config + astro login)
python catalog_vs_warehouse_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --model haiku

# Test only catalog approach (only requires astro login)
python catalog_vs_warehouse_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --catalog-only

# Test only warehouse approach (requires warehouse config)
python catalog_vs_warehouse_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --warehouse-only

# Custom output file
python catalog_vs_warehouse_benchmark.py \
  --org-id clqe2l32s023l01om0yi2nx2v \
  --output my_results.json
```

### Example Output

```
================================================================================
CATALOG SKILL vs WAREHOUSE SKILL BENCHMARK
================================================================================

Model: haiku
Scenarios: 5
Org ID: clqe2l32s023l01om0yi2nx2v

Testing:
  ✓ Catalog Skill (analyzing-data-observe + Observe MCP)
  ✓ Warehouse Skill (analyzing-data + direct queries)

================================================================================
Testing: Catalog Skill (analyzing-data-observe)
Model: haiku
================================================================================

📝 find_customer_tables: Basic table discovery by keyword
   Prompt: Find all tables related to customers in our data warehouse...
   ✓ Completed in 1234ms
     Turns: 2, Cost: $0.000123
     Result: Found 15 customer-related tables across Snowflake and BigQuery...

...

================================================================================
BENCHMARK SUMMARY: Catalog Skill vs Warehouse Skill
================================================================================
Catalog: analyzing-data-observe skill + Observe MCP
Warehouse: analyzing-data skill + direct warehouse queries
================================================================================

📊 Performance Comparison:
--------------------------------------------------------------------------------
Approach             Avg Time     Avg Turns    Avg Cost     Success
--------------------------------------------------------------------------------
catalog               1234ms          2.1    $0.000123      100%
warehouse             2345ms          3.5    $0.000234       80%

⚡ Speed Comparison:
--------------------------------------------------------------------------------
Catalog Skill is 1.90x faster than Warehouse Skill

💾 Results saved to: catalog_vs_warehouse_results.json
```

## Metrics Collected

Each benchmark result includes:
- `scenario`: Test scenario name
- `approach`: "catalog" (analyzing-data-observe) or "warehouse" (analyzing-data)
- `model`: Model used (haiku, sonnet, opus)
- `duration_ms`: Total execution time in milliseconds
- `duration_api_ms`: Pure API time (excluding overhead)
- `num_turns`: Number of agent turns
- `total_cost_usd`: Total cost in USD
- `input_tokens`: Input tokens used
- `output_tokens`: Output tokens generated
- `cache_creation_tokens`: Prompt cache creation tokens
- `cache_read_tokens`: Prompt cache read tokens
- `result_text`: The response text
- `success`: Whether execution succeeded
- `error`: Error message if failed
- `metadata`: Additional context

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

Add to the `SCENARIOS` list in `catalog_vs_warehouse_benchmark.py`:

```python
{
    "name": "my_scenario",
    "prompt": "Natural language prompt for Claude to answer",
    "description": "What this scenario tests",
}
```

**Tips for good scenario prompts**:
- Use natural language that would trigger the appropriate skill
- Ask for asset discovery, not data analysis
- Be specific about what you want back (table names, counts, metadata)
- Test that both skills can reasonably attempt the task

## Future Enhancements

- [x] Add ground truth validation for result quality ✅ **DONE** (see `warehouse_vs_observe_benchmark.py`)
- [x] Measure result completeness and accuracy ✅ **DONE** (precision/recall/F1)
- [ ] Test with more models (opus, sonnet-3.5)
- [ ] Add scenarios for complex lineage queries
- [ ] Test with production-scale datasets (millions of assets)
- [ ] Compare user experience (ease of use, clarity of responses)
- [ ] Benchmark with real user queries from production
- [ ] Add cost analysis per scenario type
