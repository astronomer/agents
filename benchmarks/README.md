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

Realistic business questions that test the full workflow (discover → understand schema → query → answer).

### Customer Analytics
| Scenario | Prompt |
|----------|--------|
| `customers_using_airflow3` | "How many customers are currently using Airflow 3?" |
| `top_customers_by_dag_runs` | "Which 10 customers have the most DAG runs this month?" |
| `customers_in_trial` | "How many organizations are currently in trial status?" |

### Usage & Adoption
| Scenario | Prompt |
|----------|--------|
| `deployments_by_cloud` | "How many active deployments do we have by cloud provider?" |
| `inactive_customers` | "Which customers haven't had any DAG runs in the last 30 days?" |
| `avg_deployments_per_customer` | "What's the average number of deployments per customer?" |

### Product Health
| Scenario | Prompt |
|----------|--------|
| `failed_dag_runs_by_customer` | "Which 5 customers have the most failed DAG runs this week?" |
| `alerts_configured` | "How many deployments have alerts configured?" |

### Discovery
| Scenario | Prompt |
|----------|--------|
| `find_customer_tables` | "What tables contain customer data? List them with descriptions." |
| `find_org_id_tables` | "Find all tables that have an ORG_ID column." |

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
