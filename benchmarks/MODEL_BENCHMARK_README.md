# Claude Model Performance Benchmark

Compares Opus, Sonnet, and Haiku performance on asset discovery tasks using the Observe MCP.

## What This Measures

For each model across realistic user prompts, we measure:

- **⏱️ Time**: End-to-end execution time (milliseconds)
- **🔄 Turns**: Number of back-and-forth interactions with Claude
- **🎯 Tokens**: Input/output token usage + cache statistics
- **💰 Cost**: Actual USD cost based on current pricing
- **✅ Completion**: Whether the task was successfully completed
- **🔧 Tool Usage**: Which MCP tools were called and in what order

## Test Scenarios

### Simple Tasks
1. **simple_keyword_search**: "Find all tables related to customers"
2. **filtered_search**: "Show me Snowflake tables containing 'revenue'"

### Complex Tasks
3. **cross_warehouse_discovery**: Search across Snowflake, Databricks, BigQuery
4. **lineage_discovery**: "Find Airflow DAGs that write to customer tables"
5. **detailed_asset_inspection**: Multi-step inspection with follow-up questions
6. **exploration_with_filters**: List filters, then search with them
7. **complex_multi_step**: Multi-stage discovery workflow

## Running the Benchmark

### Prerequisites

```bash
# Install dependencies
pip install anthropic

# Set API key
export ANTHROPIC_API_KEY=your-key-here
```

### Quick Start

```bash
# Run with all models (default: Opus, Sonnet, Haiku)
python model_performance_benchmark.py --api-key $ANTHROPIC_API_KEY

# Test specific models only
python model_performance_benchmark.py \
  --api-key $ANTHROPIC_API_KEY \
  --models claude-sonnet-4-20250514 claude-3-5-haiku-20241022

# Custom output file
python model_performance_benchmark.py \
  --api-key $ANTHROPIC_API_KEY \
  --output my_benchmark.json
```

### With Real MCP Server

To use real Observe MCP calls instead of mocks:

```bash
# Authenticate first
astro login

# Run with your org ID
python model_performance_benchmark.py \
  --api-key $ANTHROPIC_API_KEY \
  --org-id clqe2l32s023l01om0yi2nx2v
```

## Example Output

```
================================================================================
Testing Model: claude-sonnet-4-20250514
================================================================================

📝 simple_keyword_search: Basic search for tables by keyword
   Prompt: Find all tables related to customers in our data warehouse...
   ✓ Completed in 1243ms
     Turns: 2
     Tokens: 1523 in, 487 out
     Cost: $0.011865
     Tools used: ['search_assets']

📝 complex_multi_step: Multi-step discovery workflow
   Prompt: Find all tables in the production namespace, then for the largest...
   ✓ Completed in 3421ms
     Turns: 4
     Tokens: 3892 in, 1245 out
     Cost: $0.030237
     Tools used: ['search_assets', 'get_asset', 'search_assets']

================================================================================
BENCHMARK SUMMARY
================================================================================

📊 Performance Comparison:
--------------------------------------------------------------------------------
Model                          Avg Time     Avg Turns    Avg Cost     Success Rate
--------------------------------------------------------------------------------
opus-4                             3245ms          3.2  $0.045621          100%
sonnet-4                           2134ms          2.8  $0.018543          100%
3-5-haiku                          1821ms          2.9  $0.004321          100%

💰 Total Cost by Model:
--------------------------------------------------------------------------------
opus-4                         $0.319347
sonnet-4                       $0.129801
3-5-haiku                      $0.030247

🎯 Token Usage by Model:
--------------------------------------------------------------------------------
opus-4                         In:   24,531 tokens  Out:    8,234 tokens
sonnet-4                       In:   23,892 tokens  Out:    7,891 tokens
3-5-haiku                      In:   24,123 tokens  Out:    8,021 tokens

💾 Results saved to: model_benchmark_results.json
```

## Interpreting Results

### Time
- **Haiku** is typically fastest (1.5-2x faster than Sonnet)
- **Sonnet** balances speed and capability
- **Opus** is slowest but may provide better reasoning

### Turns
- Fewer turns = more efficient (less back-and-forth)
- More turns may indicate:
  - Model asking clarifying questions
  - Making incremental tool calls vs. batch calls
  - Deeper analysis

### Cost
- **Haiku**: Cheapest (5-10x less than Sonnet, 10-15x less than Opus)
- **Sonnet**: Middle ground
- **Opus**: Most expensive but highest capability

### Quality Metrics
Check the JSON output for:
- `completed`: Did the task finish successfully?
- `used_expected_tools`: Did it call the right tools?
- `final_response`: Quality of the answer

## Cost Analysis

Based on current pricing (Jan 2025):

| Model | Input $/1M | Output $/1M | Typical Task Cost |
|-------|-----------|-------------|-------------------|
| **Opus 4** | $15.00 | $75.00 | $0.03 - $0.05 |
| **Sonnet 4** | $3.00 | $15.00 | $0.01 - $0.02 |
| **Haiku 3.5** | $0.80 | $4.00 | $0.003 - $0.005 |

For production usage at scale:
- **1,000 asset searches/day**:
  - Haiku: ~$4/day
  - Sonnet: ~$15/day
  - Opus: ~$40/day

## Analyzing Results

```python
import json
import pandas as pd
import matplotlib.pyplot as plt

# Load results
with open('model_benchmark_results.json') as f:
    results = json.load(f)

df = pd.DataFrame(results)

# Compare models
summary = df.groupby('model').agg({
    'execution_time_ms': 'mean',
    'total_turns': 'mean',
    'cost_usd': 'sum',
    'completed': 'mean',
}).round(2)

print(summary)

# Plot time vs cost
plt.figure(figsize=(10, 6))
for model in df['model'].unique():
    model_data = df[df['model'] == model]
    plt.scatter(
        model_data['execution_time_ms'],
        model_data['cost_usd'],
        label=model,
        s=100,
        alpha=0.6
    )

plt.xlabel('Execution Time (ms)')
plt.ylabel('Cost (USD)')
plt.title('Model Performance: Time vs Cost')
plt.legend()
plt.grid(True, alpha=0.3)
plt.savefig('model_comparison.png')
```

## Adding Custom Scenarios

Add to `PROMPTS` list in the script:

```python
SearchPrompt(
    name="my_scenario",
    description="What this tests",
    prompt="Your user prompt here",
    expected_tool_calls=["search_assets", "get_asset"],
),
```

## Recommendations

Based on typical patterns:

### Use Haiku When:
- ✅ Simple keyword searches
- ✅ Listing/filtering assets
- ✅ High-volume, cost-sensitive operations
- ✅ Quick lookups with clear queries

### Use Sonnet When:
- ✅ Complex multi-step workflows
- ✅ Nuanced search queries
- ✅ Analysis requiring context
- ✅ Default choice for most use cases

### Use Opus When:
- ✅ Ambiguous or complex requirements
- ✅ Multi-warehouse reasoning
- ✅ Critical accuracy requirements
- ✅ Budget is not a constraint

## Limitations

- **Mock responses**: Default uses mock tool responses (fast but not realistic)
- **No real latency**: Doesn't include network/API latency to Observe API
- **Sequential execution**: Runs scenarios one at a time (not concurrent)
- **Fixed max turns**: Stops after 10 turns to prevent runaway costs

## Future Enhancements

- [ ] Add concurrent execution for stress testing
- [ ] Integrate with real Observe MCP server
- [ ] Measure response quality with rubrics
- [ ] Add prompt caching analysis
- [ ] Test with production-scale asset catalogs
- [ ] Compare batch vs. streaming modes
- [ ] Add user satisfaction scoring
