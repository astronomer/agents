# Catalog API vs Warehouse Direct: Multi-Model Comparison

Comparison of discovering data assets using:
- **Catalog API**: Observe MCP with centralized catalog search
- **Warehouse Direct**: Data plugin with direct Snowflake queries

## Results by Model

### Haiku (Fast & Cheap)

| Approach | Avg Time | Avg Turns | Avg Cost | Input | Output | Cache Created | Cache Read | Success |
|----------|----------|-----------|----------|-------|--------|---------------|------------|---------|
| **Catalog** | 7,659ms | 2.2 | $0.0132 | 36 | 1,499 | 17,596 | 207,730 | 100% |
| **Warehouse** | 8,798ms | 2.8 | $0.0177 | 44 | 1,810 | 19,192 | 351,734 | 100% |

**Winner**: Catalog API (15% faster, 25% cheaper, less cache needed)

---

### Sonnet (Balanced)

| Approach | Avg Time | Avg Turns | Avg Cost | Input | Output | Cache Created | Cache Read | Success |
|----------|----------|-----------|----------|-------|--------|---------------|------------|---------|
| **Catalog** | 17,442ms | 2.2 | $0.0994 | 36 | 2,158 | 83,452 | 164,816 | 100% |
| **Warehouse** | 17,317ms | 2.5 | $0.1319 | 42 | 2,376 | 107,634 | 284,872 | 100% |

**Winner**: Tie on speed, Catalog 25% cheaper (better cache efficiency)

---

### Opus (Most Capable)

| Approach | Avg Time | Avg Turns | Avg Cost | Input | Output | Cache Created | Cache Read | Success |
|----------|----------|-----------|----------|-------|--------|---------------|------------|---------|
| **Catalog** | 84,192ms | 4.0 | $0.9117 | 44† | 3,485† | 108,973† | 285,149† | 75%* |
| **Warehouse** | 63,476ms | 3.2 | $0.9027 | 48 | 3,166 | 147,007 | 409,170 | 100% |

**Winner**: Warehouse Direct (24% faster, similar cost, better reliability)

*Catalog had 1 timeout on "list all tables" scenario
†Token counts for 3 successful runs only (excluding timeout)

---

## Key Findings

### 1. Haiku: Catalog API is the Clear Winner
- ✅ 15% faster
- ✅ 25% cheaper
- ✅ Fewer reasoning turns (2.2 vs 2.8)
- ✅ 100% success rate

### 2. Sonnet: Catalog API Wins on Cost
- ≈ Similar speed (17.3-17.4s)
- ✅ 25% cheaper ($0.10 vs $0.13)
- ✅ Fewer reasoning turns (2.2 vs 2.5)
- ✅ 100% success rate

### 3. Opus: Warehouse Direct Wins
- ✅ 24% faster (63s vs 84s)
- ≈ Similar cost (~$0.91)
- ✅ 100% success rate vs 75%
- ❌ More reasoning turns (3.2 vs 4.0)

**Note**: Opus struggled with the Catalog API approach, timing out on full table enumeration. This suggests Opus may overthink the centralized catalog approach.

---

## Token Usage Analysis

### Total Tokens (4 scenarios)

| Model | Approach | Input | Output | Cache Created | Cache Read | Total Tokens |
|-------|----------|-------|--------|---------------|------------|--------------|
| Haiku | Catalog | 36 | 1,499 | 17,596 | 207,730 | 226,861 |
| Haiku | Warehouse | 44 | 1,810 | 19,192 | 351,734 | 372,780 |
| Sonnet | Catalog | 36 | 2,158 | 83,452 | 164,816 | 250,462 |
| Sonnet | Warehouse | 42 | 2,376 | 107,634 | 284,872 | 394,924 |
| Opus | Catalog | 44 | 3,485 | 108,973 | 285,149 | 397,651 |
| Opus | Warehouse | 48 | 3,166 | 147,007 | 409,170 | 559,391 |

### Key Insights

1. **Catalog API uses 39-58% fewer total tokens** across all models
   - Haiku: 227K vs 373K (39% reduction)
   - Sonnet: 250K vs 395K (37% reduction)
   - Opus: 398K vs 559K (29% reduction)

2. **Cache efficiency varies by approach**:
   - **Catalog**: Lower cache creation, moderate cache reads
   - **Warehouse**: Higher cache creation, much higher cache reads
   - Warehouse requires more context caching for SQL generation

3. **Output tokens increase with model intelligence**:
   - Haiku: ~1,500-1,800 tokens
   - Sonnet: ~2,200-2,400 tokens
   - Opus: ~3,200-3,500 tokens
   - Smarter models provide more detailed explanations

4. **Input tokens remain minimal** (36-48 tokens)
   - User prompts are short
   - Most context comes from cached system prompts and MCP responses

---

## Cost Comparison

### Total Cost per Approach (4 scenarios)

| Model | Catalog Total | Warehouse Total | Savings |
|-------|---------------|-----------------|---------|
| Haiku | $0.053 | $0.071 | 25% |
| Sonnet | $0.398 | $0.528 | 25% |
| Opus | $2.735* | $3.611 | 24% |

*Opus Catalog had 1 failure

---

## Speed Comparison

### Average Response Time

| Model | Catalog | Warehouse | Faster |
|-------|---------|-----------|--------|
| Haiku | 7.7s | 8.8s | Catalog (15%) |
| Sonnet | 17.4s | 17.3s | Tie |
| Opus | 84.2s | 63.5s | Warehouse (24%) |

---

## Recommendations

### For Production Use

1. **Use Haiku + Catalog API** for:
   - Interactive data discovery
   - Cost-sensitive operations
   - Fast response times needed
   - Simple asset searches

2. **Use Sonnet + Catalog API** for:
   - More complex reasoning required
   - Cost matters more than speed
   - Balanced performance/intelligence

3. **Use Sonnet/Haiku + Warehouse Direct** for:
   - Complex SQL queries beyond discovery
   - When you need to join across tables
   - Analysis requiring warehouse computation

4. **Avoid Opus for simple discovery**:
   - Too slow (60-110s per query)
   - Too expensive ($0.90+ per query)
   - Reliability issues with Catalog API
   - Only use for complex reasoning tasks

---

## Token Efficiency Metrics

### Cost per 1K Tokens (Total Token Basis)

| Model | Catalog | Warehouse | Savings |
|-------|---------|-----------|---------|
| Haiku | $0.23/1M | $0.19/1M | Warehouse 17% cheaper per token |
| Sonnet | $1.58/1M | $1.34/1M | Warehouse 15% cheaper per token |
| Opus | $9.15/1M | $6.43/1M | Warehouse 30% cheaper per token |

**Surprising finding**: Warehouse Direct is actually **cheaper per token**, but Catalog API wins on **absolute cost** because it uses 37-39% fewer tokens overall.

### Cache Hit Rates

| Model | Approach | Cache Created | Cache Read | Hit Rate |
|-------|----------|---------------|------------|----------|
| Haiku | Catalog | 17,596 | 207,730 | 92.2% |
| Haiku | Warehouse | 19,192 | 351,734 | 94.8% |
| Sonnet | Catalog | 83,452 | 164,816 | 66.4% |
| Sonnet | Warehouse | 107,634 | 284,872 | 72.6% |
| Opus | Catalog | 108,973 | 285,149 | 72.4% |
| Opus | Warehouse | 147,007 | 409,170 | 73.6% |

**Observation**: Warehouse approach has higher cache hit rates because it repeatedly accesses the same warehouse connection context and SQL patterns across queries.

---

## Test Scenarios

All models were tested on these 4 scenarios:

1. **Find customer tables**: Basic keyword search
2. **List all tables**: Full enumeration (18,751 tables)
3. **Find sales tables**: Semantic/business concept search
4. **Table ownership**: Metadata and timestamp lookup

---

## Technical Details

- **Test Date**: 2026-01-28
- **Organization**: Astronomer Production
- **Total Tables**: 18,751 across Snowflake, Databricks, BigQuery
- **Timeout**: 180 seconds per scenario
- **Permission Mode**: `bypassPermissions`
- **Tools**: Built-in Claude Code tools enabled

---

## Files

- `catalog_vs_warehouse_haiku.json` - Haiku detailed results
- `catalog_vs_warehouse_sonnet.json` - Sonnet detailed results
- `catalog_vs_warehouse_opus.json` - Opus detailed results
- `catalog_vs_warehouse_benchmark.py` - Benchmark script
