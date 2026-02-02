# Proper Benchmark Design: Warehouse SQL vs Observe Semantic Search

## What We're Actually Comparing

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Approach A: Data Warehouse SQL (Direct Schema Introspection)            │
│                                                                         │
│   Method: SQL queries against information_schema / SHOW commands        │
│                                                                         │
│   Tools needed:                                                         │
│   - run_sql("SHOW SCHEMAS IN DATABASE db")                             │
│   - run_sql("SHOW TABLES IN SCHEMA db.schema")                         │
│   - run_sql("SELECT * FROM information_schema.tables WHERE ...")       │
│   - run_sql("SELECT * FROM information_schema.columns WHERE ...")      │
│   - run_sql("DESC TABLE db.schema.table")                              │
│                                                                         │
│   Data path: Claude → Bash/Kernel → Snowflake/Databricks → Results     │
└─────────────────────────────────────────────────────────────────────────┘
                                   vs
┌─────────────────────────────────────────────────────────────────────────┐
│ Approach B: Observe Semantic Search (Centralized Catalog)               │
│                                                                         │
│   Method: Embedding-based search + n-gram text matching                 │
│                                                                         │
│   Tools:                                                                │
│   - search_assets(search="customer", asset_types=["snowflakeTable"])   │
│   - get_asset(asset_id="snowflake://...")                              │
│                                                                         │
│   Data path: Claude → MCP → Observe API → ClickHouse → Results         │
└─────────────────────────────────────────────────────────────────────────┘

                        Validated Against

┌─────────────────────────────────────────────────────────────────────────┐
│ Ground Truth (Pre-computed correct answers)                             │
│                                                                         │
│   For each scenario:                                                    │
│   - expected_tables: ["TABLE_A", "TABLE_B", ...]                       │
│   - expected_count: 243                                                 │
│   - expected_schemas: ["REPORTING", "MART_CUST"]                       │
│                                                                         │
│   Metrics calculated:                                                   │
│   - Precision: (correct found) / (total found)                         │
│   - Recall: (correct found) / (expected)                               │
│   - F1: 2 * (P * R) / (P + R)                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites for Proper Benchmark

### For Warehouse Approach

1. **Warehouse credentials configured**:
   ```yaml
   # ~/.astro/agents/warehouse.yml
   default: snowflake_prod
   connectors:
     snowflake_prod:
       type: snowflake
       account: fy02423.us-east-1.aws
       user: ${SNOWFLAKE_USER}
       password: ${SNOWFLAKE_PASSWORD}
       database: HQ
       warehouse: COMPUTE_WH
   ```

2. **Kernel starts successfully**:
   ```bash
   uv run scripts/cli.py start
   uv run scripts/cli.py exec "run_sql('SELECT 1')"  # Verify connection
   ```

3. **User has access to information_schema**:
   ```sql
   -- Must work
   SHOW SCHEMAS IN DATABASE HQ;
   SELECT table_name FROM information_schema.tables LIMIT 10;
   ```

### For Observe Approach

1. **Astro organization ID** with Observe enabled
2. **Valid auth token** (`astro login`)
3. **Embeddings generated** for catalog assets

### For Ground Truth

1. **Pre-compute expected results** by running warehouse queries directly:
   ```sql
   -- Ground truth for "find customer tables"
   SELECT table_name, table_schema
   FROM information_schema.tables
   WHERE LOWER(table_name) LIKE '%customer%'
   ORDER BY table_name;
   ```

2. **Store as JSON**:
   ```json
   {
     "scenario": "find_customer_tables",
     "ground_truth": {
       "tables": [
         {"name": "CUSTOMER_AIRFLOW_VERSIONS", "schema": "REPORTING"},
         {"name": "CUSTOMER_BOT_COLLECTED_DETAILS", "schema": "DELIVERY"},
         ...
       ],
       "total_count": 243
     }
   }
   ```

---

## Benchmark Scenarios

### Scenario 1: Find Tables by Keyword

**Prompt**: "Find all tables related to customers"

**Warehouse SQL approach**:
```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE LOWER(table_name) LIKE '%customer%'
   OR LOWER(table_name) LIKE '%cust%';
```

**Observe approach**:
```python
search_assets(search="customer", asset_types=["snowflakeTable"], limit=100)
```

**Ground truth**:
- 243 tables with "customer" or "cust" in name
- Must include: CUSTOMER_AIRFLOW_VERSIONS, CURRENT_ASTRO_CUSTS, etc.

**Metrics**:
- Precision: Did it return only customer tables?
- Recall: Did it find all 243?
- Time: How long?
- Turns: How many API calls?

---

### Scenario 2: List All Tables in Schema

**Prompt**: "List all tables in the REPORTING schema"

**Warehouse SQL approach**:
```sql
SHOW TABLES IN SCHEMA HQ.REPORTING;
-- or
SELECT table_name FROM information_schema.tables WHERE table_schema = 'REPORTING';
```

**Observe approach**:
```python
search_assets(asset_types=["snowflakeTable"], limit=100)
# Filter results where schema = REPORTING
```

**Ground truth**:
- Exact list of tables in REPORTING schema
- Count: N tables

**Metrics**:
- Precision: 100% (schema filter should be exact)
- Recall: Did it get all tables?
- Time, turns, cost

---

### Scenario 3: Cross-Warehouse Discovery

**Prompt**: "What tables do we have across Snowflake, Databricks, and BigQuery?"

**Warehouse SQL approach**:
```sql
-- Snowflake
SELECT COUNT(*) as snowflake_tables FROM information_schema.tables;

-- Would need separate connections for Databricks/BigQuery
-- This is where warehouse approach struggles!
```

**Observe approach**:
```python
# Single API call can span all warehouses
search_assets(
    asset_types=["snowflakeTable", "databricksTable", "bigQueryTable"],
    limit=100
)
```

**Ground truth**:
- Total counts per warehouse type
- Sample table names from each

**Note**: This scenario likely favors Observe (centralized catalog vs multiple connections).

---

### Scenario 4: Table Metadata Lookup

**Prompt**: "Who owns the CUSTOMER_AIRFLOW_VERSIONS table?"

**Warehouse SQL approach**:
```sql
-- Snowflake doesn't have owner in standard information_schema
-- Would need: SHOW TABLES LIKE 'CUSTOMER_AIRFLOW_VERSIONS';
-- Or query ACCOUNT_USAGE.TABLES (requires ACCOUNTADMIN)
```

**Observe approach**:
```python
get_asset(asset_id="snowflake://fy02423/HQ/REPORTING/CUSTOMER_AIRFLOW_VERSIONS")
# Returns: owner, deployment, namespace, etc.
```

**Ground truth**:
- Owner: "data-platform-team"
- Deployment: "clxdeploy123"
- Namespace: "quasarian-radiation-8124"

**Note**: This scenario likely favors Observe (richer metadata).

---

### Scenario 5: Column Discovery

**Prompt**: "Find tables with an 'email' column"

**Warehouse SQL approach**:
```sql
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE LOWER(column_name) LIKE '%email%';
```

**Observe approach**:
```python
# Current limitation: columns not embedded!
search_assets(search="email", asset_types=["snowflakeTable"])
# Only works if "email" is in table name or description
```

**Ground truth**:
- All tables with email columns
- Count: N tables

**Note**: This scenario currently favors Warehouse (Observe doesn't embed columns yet).

---

## Implementation

### Step 1: Generate Ground Truth

```python
# ground_truth_generator.py

import snowflake.connector
import json

def generate_ground_truth():
    conn = snowflake.connector.connect(...)

    scenarios = {}

    # Scenario 1: Find customer tables
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE LOWER(table_name) LIKE '%customer%'
           OR LOWER(table_name) LIKE '%cust%'
        ORDER BY table_name
    """)
    results = cursor.fetchall()
    scenarios["find_customer_tables"] = {
        "tables": [{"schema": r[0], "name": r[1]} for r in results],
        "count": len(results),
    }

    # Scenario 2: List REPORTING tables
    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'REPORTING'
        ORDER BY table_name
    """)
    results = cursor.fetchall()
    scenarios["list_reporting_tables"] = {
        "tables": [r[0] for r in results],
        "count": len(results),
    }

    # ... more scenarios

    with open("ground_truth.json", "w") as f:
        json.dump(scenarios, f, indent=2)
```

### Step 2: Run Warehouse Approach

```python
# benchmark_warehouse.py

def run_warehouse_scenario(scenario: dict) -> BenchmarkResult:
    """Run scenario using warehouse SQL approach."""

    # Ensure kernel is running with warehouse connection
    subprocess.run(["uv", "run", "scripts/cli.py", "start"])

    # Invoke analyzing-data skill
    cmd = [
        'claude', '--print', '--model', 'haiku',
        '--output-format', 'json',
        '--plugin-dir', '.',
    ]

    prompt = f"/data:analyzing-data\n\n{scenario['prompt']}"

    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    output = json.loads(result.stdout)

    return BenchmarkResult(
        approach="warehouse",
        result_text=output.get("result", ""),
        duration_ms=output.get("duration_ms", 0),
        num_turns=output.get("num_turns", 0),
        total_cost_usd=output.get("total_cost_usd", 0),
    )
```

### Step 3: Run Observe Approach

```python
# benchmark_observe.py

def run_observe_scenario(scenario: dict, org_id: str) -> BenchmarkResult:
    """Run scenario using Observe semantic search approach."""

    # Create plugin config with Observe MCP
    plugin_dir = create_observe_plugin_config(org_id)

    cmd = [
        'claude', '--print', '--model', 'haiku',
        '--output-format', 'json',
        '--plugin-dir', str(plugin_dir),
    ]

    prompt = f"/catalog:analyzing-data-observe\n\n{scenario['prompt']}"

    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    output = json.loads(result.stdout)

    return BenchmarkResult(
        approach="observe",
        result_text=output.get("result", ""),
        duration_ms=output.get("duration_ms", 0),
        num_turns=output.get("num_turns", 0),
        total_cost_usd=output.get("total_cost_usd", 0),
    )
```

### Step 4: Validate Against Ground Truth

```python
# validate.py

def validate_result(result: BenchmarkResult, ground_truth: dict) -> ValidationResult:
    """Compare result against ground truth."""

    # Extract tables from result text
    found_tables = extract_tables_from_text(result.result_text)
    expected_tables = set(ground_truth["tables"])

    # Calculate precision/recall
    true_positives = found_tables & expected_tables
    false_positives = found_tables - expected_tables
    false_negatives = expected_tables - found_tables

    precision = len(true_positives) / len(found_tables) if found_tables else 0
    recall = len(true_positives) / len(expected_tables) if expected_tables else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    return ValidationResult(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=list(true_positives),
        false_positives=list(false_positives),
        false_negatives=list(false_negatives),
    )


def extract_tables_from_text(text: str) -> set[str]:
    """Extract table names from Claude's response.

    Handles various formats:
    - Bullet lists: "- TABLE_NAME"
    - Numbered lists: "1. TABLE_NAME"
    - Inline mentions: "the TABLE_NAME table"
    - FQDN: "DB.SCHEMA.TABLE_NAME"
    """
    patterns = [
        r'\b([A-Z][A-Z0-9_]+)\b',  # UPPER_CASE table names
        r'`([^`]+)`',              # Backtick-quoted names
    ]

    tables = set()
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Extract table name from FQDN if present
            parts = match.split('.')
            table_name = parts[-1]
            if len(table_name) > 3:  # Filter out short strings
                tables.add(table_name)

    return tables
```

### Step 5: Full Benchmark Runner

```python
# full_benchmark.py

def run_full_benchmark(org_id: str, warehouse_config_path: str):
    """Run complete benchmark comparing warehouse vs observe."""

    # Load ground truth
    with open("ground_truth.json") as f:
        ground_truth = json.load(f)

    # Define scenarios
    scenarios = [
        {"name": "find_customer_tables", "prompt": "Find all tables related to customers"},
        {"name": "list_reporting_tables", "prompt": "List all tables in the REPORTING schema"},
        {"name": "cross_warehouse", "prompt": "What tables do we have across Snowflake, Databricks, and BigQuery?"},
        {"name": "table_metadata", "prompt": "Who owns the CUSTOMER_AIRFLOW_VERSIONS table?"},
        {"name": "column_discovery", "prompt": "Find tables with an 'email' column"},
    ]

    results = []

    for scenario in scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario: {scenario['name']}")
        print(f"{'='*60}")

        # Run warehouse approach
        print("\n  Running WAREHOUSE approach...")
        warehouse_result = run_warehouse_scenario(scenario)
        warehouse_validation = validate_result(
            warehouse_result,
            ground_truth[scenario['name']]
        )

        # Run observe approach
        print("  Running OBSERVE approach...")
        observe_result = run_observe_scenario(scenario, org_id)
        observe_validation = validate_result(
            observe_result,
            ground_truth[scenario['name']]
        )

        # Print comparison
        print(f"\n  {'Metric':<20} {'Warehouse':<15} {'Observe':<15}")
        print(f"  {'-'*50}")
        print(f"  {'Time (ms)':<20} {warehouse_result.duration_ms:<15.0f} {observe_result.duration_ms:<15.0f}")
        print(f"  {'Turns':<20} {warehouse_result.num_turns:<15} {observe_result.num_turns:<15}")
        print(f"  {'Cost ($)':<20} {warehouse_result.total_cost_usd:<15.4f} {observe_result.total_cost_usd:<15.4f}")
        print(f"  {'Precision':<20} {warehouse_validation.precision:<15.2%} {observe_validation.precision:<15.2%}")
        print(f"  {'Recall':<20} {warehouse_validation.recall:<15.2%} {observe_validation.recall:<15.2%}")
        print(f"  {'F1 Score':<20} {warehouse_validation.f1:<15.2%} {observe_validation.f1:<15.2%}")

        results.append({
            'scenario': scenario['name'],
            'warehouse': {
                'duration_ms': warehouse_result.duration_ms,
                'turns': warehouse_result.num_turns,
                'cost': warehouse_result.total_cost_usd,
                'precision': warehouse_validation.precision,
                'recall': warehouse_validation.recall,
                'f1': warehouse_validation.f1,
            },
            'observe': {
                'duration_ms': observe_result.duration_ms,
                'turns': observe_result.num_turns,
                'cost': observe_result.total_cost_usd,
                'precision': observe_validation.precision,
                'recall': observe_validation.recall,
                'f1': observe_validation.f1,
            },
        })

    # Save results
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)

    return results
```

---

## Expected Outcomes

Based on analysis, here's what we'd expect:

| Scenario | Warehouse Wins | Observe Wins | Why |
|----------|----------------|--------------|-----|
| **Find tables by keyword** | Maybe | Maybe | Depends on whether Observe has good embeddings |
| **List tables in schema** | ✅ | | SQL is exact, Observe may miss some |
| **Cross-warehouse search** | | ✅ | Single API vs multiple connections |
| **Table metadata** | | ✅ | Richer metadata in catalog |
| **Column discovery** | ✅ | | Observe doesn't embed columns yet |

### When Warehouse is Better

1. **Exact schema queries** - SQL gives precise results
2. **Column-level search** - information_schema has columns
3. **Data freshness** - Direct query = latest data
4. **Ad-hoc exploration** - Can run any SQL

### When Observe is Better

1. **Cross-warehouse** - Single catalog spans all warehouses
2. **Fuzzy/semantic search** - "customer data" finds related tables
3. **Metadata richness** - Owners, deployments, lineage, tags
4. **Performance** - Pre-indexed, no SQL parsing overhead
5. **No credentials needed** - Works with just auth token

---

## Missing Pieces to Implement

1. **Ground truth generator** - Script to query warehouse and save expected results
2. **Table extraction** - Parse Claude's natural language response to extract table names
3. **Validation metrics** - Precision, recall, F1 calculation
4. **Warehouse skill verification** - Ensure kernel actually runs SQL (not Observe fallback)

---

## Summary

The current benchmark does **NOT** compare warehouse vs observe - both approaches use the Observe API.

To properly benchmark:

1. **Configure warehouse credentials** (`~/.astro/agents/warehouse.yml`)
2. **Generate ground truth** from direct SQL queries
3. **Verify warehouse approach** actually runs SQL (not falls back to Observe)
4. **Add validation metrics** (precision, recall, F1)
5. **Compare both speed AND accuracy**

This will give you a true apples-to-apples comparison of the two approaches.
