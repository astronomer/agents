# Ground Truth Validation - Implementation Summary

## What Was Built

### 1. Validation Framework (`ground_truth_validator.py`)
- **Extracts entities** from Claude's text responses (tables, DAGs, metadata)
- **Calculates quality metrics**:
  - Accuracy: Overall correctness (0-1)
  - Precision: % of returned items that are correct
  - Recall: % of expected items found
  - F1 Score: Harmonic mean of precision/recall
- **Tracks errors**:
  - True positives: Correctly identified
  - False positives: Incorrectly added
  - False negatives: Missed items
- **Pattern matching** for different entity types:
  - Tables: URIs, quoted names, qualified names
  - DAGs: dag:// URIs, _dag suffix patterns
  - Metadata: Field presence checking

### 2. Updated Benchmark Script (`claude_code_benchmark.py`)
- **New --ground-truth parameter**: Pass ground truth JSON file
- **Automatic validation**: Validates results if ground truth provided
- **Enhanced output**:
  - Performance metrics (existing): speed, cost, tokens
  - Quality metrics (new): accuracy, precision, recall, F1
  - Detailed breakdown by scenario and model
- **Enriched results JSON**: Includes validation scores alongside performance

### 3. Ground Truth Templates
- **`ground_truth_template.json`**: Structure showing what to collect
- **Collection helpers**: Scripts to gather actual catalog data

### 4. Documentation
- **`VALIDATION_README.md`**: Complete guide to using validation
- **Workflow instructions**: How to collect, validate, interpret
- **Troubleshooting guide**: Common issues and fixes

## Current Status

### ✅ Complete
- Validation framework built and tested
- Benchmark integration complete
- Documentation written
- Template structure defined

### ⚠️ Blocked
- **Ground truth data collection**: Waiting on MCP authentication
- MCP server has cached expired token
- Needs Claude Code session restart to reload fresh tokens

## Next Steps

### Immediate: Collect Ground Truth

**Option 1: Restart Session (Recommended)**
```bash
# Exit this session
exit

# Start fresh session (MCPs reload auth)
claude

# Navigate and collect
cd astro-agents/benchmarks
# Ask Claude to collect ground truth
```

**Option 2: Manual Queries**

If you want to proceed without restart, you can manually query:
```bash
# Authenticate
astro login

# In a Python shell with your catalog credentials
python
>>> from your_catalog_client import search
>>> search("customer")  # etc
```

Then manually populate `ground_truth_data.json`.

### Then: Run Validated Benchmarks

Once ground truth is collected:

```bash
cd astro-agents/benchmarks

# Run benchmarks with validation
python claude_code_benchmark.py \
    --models haiku sonnet opus \
    --ground-truth ground_truth_data.json \
    --output validated_results.json

# View results
cat validated_results.json | jq '.results[] | {model, scenario, validation}'
```

## Example: Before vs After

### Before (Performance Only)
```json
{
  "model": "haiku",
  "scenario": "simple_keyword_search",
  "duration_ms": 3842,
  "total_cost_usd": 0.023,
  "result_text": "Found 10 customer tables..."
}
```

**Question**: Is this good? We don't know if those 10 tables are correct!

### After (Performance + Quality)
```json
{
  "model": "haiku",
  "scenario": "simple_keyword_search",
  "duration_ms": 3842,
  "total_cost_usd": 0.023,
  "result_text": "Found 10 customer tables...",
  "validation": {
    "accuracy": 0.833,
    "precision": 0.900,
    "recall": 0.818,
    "f1_score": 0.857,
    "true_positives_count": 9,
    "false_positives_count": 1,
    "false_negatives_count": 2,
    "notes": "Missed: customer_segments, customer_ltv"
  }
}
```

**Now we know**:
- ✅ Found 9/11 expected tables (82% recall)
- ⚠️ Added 1 incorrect table (90% precision)
- ⚠️ Missed 2 tables: customer_segments, customer_ltv
- 📊 Decision: Speed is good, but may need Sonnet for critical queries

## Key Benefits

### 1. Model Selection Guidance
```
Haiku:  Fast (3.8s) + Cheap ($0.02) + Decent Accuracy (83%)  → Use for exploration
Sonnet: Medium (8.9s) + Medium ($0.09) + High Accuracy (95%) → Use for production
Opus:   Slow (15s) + Expensive ($0.25) + Best Accuracy (98%) → Use for critical tasks
```

### 2. Regression Detection
```bash
# Benchmark today
python claude_code_benchmark.py --ground-truth ground_truth_data.json

# Ship code changes
# ...

# Benchmark after changes
python claude_code_benchmark.py --ground-truth ground_truth_data.json

# Compare results
# Did accuracy drop? Did false positives increase?
```

### 3. Catalog Quality Insights
- If validation shows many false negatives → Catalog may be incomplete
- If false positives are high → Model hallucinating or catalog has noise
- If accuracy varies by scenario → Some use cases need better prompts

## Files Created/Modified

```
astro-agents/benchmarks/
├── ground_truth_validator.py          # NEW: Validation logic
├── ground_truth_template.json         # NEW: Data structure template
├── collect_ground_truth_interactive.py # NEW: Collection helper
├── VALIDATION_README.md               # NEW: Usage guide
├── VALIDATION_SUMMARY.md              # NEW: This file
└── claude_code_benchmark.py           # MODIFIED: Added validation
```

## What Makes This Validation Unique

### Smart Entity Extraction
- Handles multiple naming formats (URIs, qualified names, simple names)
- Normalizes for comparison (case-insensitive, schema-agnostic)
- Context-aware (different patterns for tables vs DAGs)

### Comprehensive Metrics
- Not just "right or wrong" - quantifies partial correctness
- Precision/Recall separate - see different failure modes
- F1 score - single metric for ranking

### Production-Ready
- JSON output for automation
- Detailed error tracking
- Integration with existing benchmark infrastructure

## Questions Validation Can Answer

1. **"Which model should I use for production?"**
   - Compare accuracy vs cost/speed trade-offs

2. **"Did my prompt improvements help?"**
   - Run before/after benchmarks, compare F1 scores

3. **"Is the catalog complete?"**
   - High false negatives → Missing assets in catalog

4. **"Are models hallucinating?"**
   - High false positives → Model making up table names

5. **"Which scenarios need attention?"**
   - Low recall on specific scenarios → Improve prompts or model

6. **"Is caching helping quality?"**
   - Compare accuracy with cache hits vs cold starts

## Future Enhancements (Optional)

- **Semantic similarity**: Score partial matches (e.g., "customers" vs "customer_data")
- **Metadata validation**: Check if owner/timestamp values are correct
- **Lineage accuracy**: Validate DAG→Table mappings
- **Response quality**: Score explanation clarity, formatting
- **Time-based metrics**: Track accuracy degradation over time
