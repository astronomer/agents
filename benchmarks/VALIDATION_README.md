# Benchmark Ground Truth Validation

This directory now includes ground truth validation to measure not just performance, but also **result quality** (accuracy, precision, recall).

## Overview

**Problem Solved**: The original benchmarks only measured speed and cost, but not whether answers were correct. With ground truth validation, we can now answer questions like:
- "Haiku is 2x faster but only finds 80% of tables - is that acceptable?"
- "Sonnet costs more but has 95% accuracy vs Haiku's 85%"
- "Which model has fewer false positives?"

## Architecture

```
ground_truth_template.json          # Template showing what data to collect
ground_truth_data.json              # Actual ground truth (populated from catalog)
ground_truth_validator.py           # Validation logic
claude_code_benchmark.py            # Updated to use validation
collect_ground_truth_interactive.py # Helper to collect data
```

## Workflow

### Step 1: Collect Ground Truth Data

**Option A: Automatic (when auth is working)**
```bash
# Restart Claude Code session first to reload auth tokens
exit  # Exit current session
claude  # Start fresh session

# Then run collection
cd astro-agents/benchmarks
python collect_ground_truth_interactive.py
```

**Option B: Manual Collection**

If automatic collection doesn't work, restart your Claude Code session and ask:
```
I'm in the astro-agents/benchmarks directory. Please collect ground truth data
for the benchmarks by querying the catalog and populating ground_truth_data.json.
```

Claude will:
1. Run `search_assets()` for each scenario
2. Extract table/DAG names from results
3. Save to `ground_truth_data.json`

### Step 2: Run Benchmarks with Validation

```bash
cd astro-agents/benchmarks

# Run with validation
python claude_code_benchmark.py \
    --models haiku sonnet \
    --ground-truth ground_truth_data.json \
    --output results_with_validation.json
```

### Step 3: Review Results

The output now includes both **performance** and **quality** metrics:

#### Performance Metrics (existing)
- Duration (ms)
- Number of turns
- Cost (USD)
- Token usage

#### Quality Metrics (new)
- **Accuracy**: Overall correctness score (0-1)
- **Precision**: % of returned items that are correct
- **Recall**: % of expected items that were found
- **F1 Score**: Harmonic mean of precision and recall
- **True Positives**: Correct items found
- **False Positives**: Incorrect items returned
- **False Negatives**: Expected items missed

## Example Output

```
================================================================================
BENCHMARK SUMMARY - Claude Code Real Execution
================================================================================

📊 Performance Comparison:
--------------------------------------------------------------------------------
Model           Avg Time     Avg Turns    Avg Cost     Success Rate
--------------------------------------------------------------------------------
haiku                3842ms          2.0  $0.023456          100%
sonnet               8921ms          2.4  $0.089234          100%

================================================================================
QUALITY METRICS - Ground Truth Validation
================================================================================

🎯 Accuracy by Model:
--------------------------------------------------------------------------------
Model           Accuracy     Precision    Recall       F1 Score
--------------------------------------------------------------------------------
haiku               85.2%        89.3%        82.1%      0.855
sonnet              94.7%        96.2%        93.4%      0.948

📋 Detailed Results by Scenario:

simple_keyword_search:
  haiku:
    Accuracy: 83.3% | Precision: 90.0% | Recall: 81.8%
    True Positives: 9 | False Positives: 1 | False Negatives: 2
    ⚠️  Missed: customer_segments, customer_ltv
  sonnet:
    Accuracy: 95.5% | Precision: 100.0% | Recall: 95.5%
    True Positives: 11 | False Positives: 0 | False Negatives: 1
    ⚠️  Missed: customer_ltv
```

## Validation Logic

### Table Discovery Scenarios

The validator:
1. Extracts table names from Claude's response text using patterns:
   - URI format: `snowflake://account/db/schema/table`
   - Quoted names: `"table_name"`
   - Qualified names: `database.schema.table`
   - Snake_case identifiers

2. Normalizes names (lowercases, removes schema prefixes)

3. Compares against expected tables:
   ```python
   true_positives = actual ∩ expected    # Correct
   false_positives = actual - expected   # Incorrect additions
   false_negatives = expected - actual   # Missed tables
   ```

4. Calculates metrics:
   - Precision = TP / (TP + FP)  # How many returned were right?
   - Recall = TP / (TP + FN)     # How many expected did we find?
   - F1 = 2 × (P × R) / (P + R)  # Balance

### DAG Discovery Scenarios

Similar logic but looks for DAG naming patterns:
- `dag://namespace/dag_id`
- Identifiers with `_dag` suffix
- Quoted DAG names

### Detailed Inspection Scenarios

Checks if response contains required metadata fields:
- Owner information
- Last update timestamp
- Deployment details

## Ground Truth Data Format

```json
{
  "metadata": {
    "created_at": "2026-01-29",
    "organization_id": "clqe2l32s023l01om0yi2nx2v",
    "queries_run_at": "2026-01-29T10:30:00"
  },
  "scenarios": {
    "simple_keyword_search": {
      "prompt": "Find all tables related to customers in our data warehouse",
      "expected_results": {
        "total_tables": 12,
        "tables": [
          "customers",
          "customer_orders",
          "customer_segments",
          ...
        ]
      },
      "catalog_query": {
        "search": "customer",
        "asset_types": ["snowflakeTable", "databricksTable", "bigQueryTable"]
      }
    }
  }
}
```

## Interpreting Results

### Good Results
- ✅ High accuracy (>90%)
- ✅ High precision (>95%) - Few false positives
- ✅ High recall (>90%) - Found most expected items
- ✅ F1 score >0.90

### Warning Signs
- ⚠️ Low recall (<80%) - Missing many tables
- ⚠️ Low precision (<85%) - Returning incorrect tables
- ⚠️ High false positive rate - Adding tables that don't exist
- ⚠️ Count mismatch - Very different from expected count

### Trade-offs
- **Haiku**: Usually faster and cheaper, but may have lower accuracy
- **Sonnet**: Slower and more expensive, but typically higher quality
- **Opus**: Most expensive, highest quality, best for critical scenarios

## Updating Ground Truth

Ground truth should be refreshed when:
- 📦 New tables are added to the warehouse
- 🗑️ Tables are dropped or renamed
- 🔄 DAG structure changes
- 🏗️ Major schema refactoring

To update:
```bash
# Re-collect ground truth
python collect_ground_truth_interactive.py

# Or ask Claude to update specific scenarios
```

## Troubleshooting

### Authentication Issues

If MCP queries fail with auth errors:
1. Run `astro login`
2. **Restart Claude Code session** (exit and start fresh)
3. MCP servers will pick up new auth tokens
4. Try collection again

### Validation Fails

If validation throws errors:
- Check ground_truth_data.json exists
- Verify JSON is valid
- Ensure expected_results are populated (not null)

### Low Quality Scores

If results have low accuracy:
- Check if prompts are clear enough
- Verify ground truth is correct (catalog may have changed)
- Consider if model hallucinated table names
- Review false positives/negatives for patterns
