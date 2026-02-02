# Benchmarks

Compares two data discovery approaches: **Warehouse SQL** vs **Observe Catalog**.

## Quick Start

```bash
# Authenticate with Astro Cloud
astro login

# Run benchmark
python benchmark.py --org-id <YOUR_ORG_ID>
```

## Approaches Compared

### 1. Warehouse (SQL)
- **Skill**: `analyzing-data`
- **Method**: Direct SQL queries to `INFORMATION_SCHEMA`
- **Strengths**: Precise metadata, column-level queries, real-time data
- **Limitations**: Single database scope, requires warehouse connection

### 2. Observe (Catalog)
- **Skill**: `analyzing-data-observe`
- **Method**: Astro Observability catalog API via MCP
- **Strengths**: Cross-warehouse discovery, fast keyword search, no SQL needed
- **Limitations**: No column indexing, catalog freshness lag

## Scenarios

| Scenario | Prompt | Tests |
|----------|--------|-------|
| `find_tables_by_keyword` | "Find all tables with 'customer' in the name" | Keyword search |
| `list_tables_simple` | "List 20 tables from the database" | Basic listing |
| `find_schemas` | "What schemas exist in the database?" | Schema discovery |
| `table_count` | "How many tables are in the database?" | Counting |
| `find_tables_with_column` | "Find tables that have a column named 'email'" | Column search |

**Note**: Both approaches receive identical prompts - the skill determines the method.

## Usage

```bash
# Run all scenarios
python benchmark.py --org-id <ORG_ID>

# Run specific scenarios
python benchmark.py --org-id <ORG_ID> --scenarios find_tables_by_keyword table_count

# Custom timeout (default: 120s)
python benchmark.py --org-id <ORG_ID> --timeout 180

# Custom output file
python benchmark.py --org-id <ORG_ID> --output my_results.json
```

## Metrics Collected

| Metric | Description |
|--------|-------------|
| `duration_ms` | Total execution time |
| `num_turns` | API round-trips |
| `total_cost_usd` | LLM cost |
| `success` | Pass/fail |
| `result_preview` | First 500 chars of response |

## Isolation

The benchmark uses isolated plugin configurations to ensure fair comparison:

- **Warehouse**: Temp plugin WITHOUT Observe MCP (SQL only)
- **Observe**: Temp plugin with Observe MCP only
- **Config isolation**: `CLAUDE_CONFIG_DIR` prevents loading global plugins
