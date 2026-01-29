---
name: airflow
description: Manages Apache Airflow operations including listing, testing, running, and debugging DAGs, viewing task logs, checking connections and variables, and monitoring system health. Use when working with Airflow DAGs, pipelines, workflows, or tasks, or when the user mentions testing dags, running pipelines, debugging workflows, dag failures, task errors, dag status, pipeline status, list dags, show connections, check variables, or airflow health.
---

# Airflow Operations

Use `af` commands to query, manage, and troubleshoot Airflow workflows.

## Instance Configuration

Manage multiple Airflow instances with persistent configuration:

```bash
# Add instances (auth is optional for open instances)
af instance add local --url http://localhost:8080
af instance add staging --url https://staging.example.com --username admin --password secret
af instance add prod --url https://prod.example.com --token '${AIRFLOW_PROD_TOKEN}'

# List and switch instances
af instance list      # Shows all instances in a table
af instance use prod  # Switch to prod instance
af instance current   # Show current instance
af instance delete old-instance

# Override instance for a single command
af --instance staging dags list
```

Config file: `~/.af/config.yaml` (override with `--config` or `AIRFLOW_CLI_CONFIG`)

Or use environment variables:

```bash
export AIRFLOW_API_URL=http://localhost:8080
export AIRFLOW_USERNAME=admin
export AIRFLOW_PASSWORD=admin
```

Or CLI flags: `af --airflow-url http://localhost:8080 --username admin --password admin <command>`

## Quick Reference

| Command | Description |
|---------|-------------|
| `af health` | System health check |
| `af dags list` | List all DAGs |
| `af dags get <dag_id>` | Get DAG details |
| `af dags explore <dag_id>` | Full DAG investigation |
| `af dags source <dag_id>` | Get DAG source code |
| `af dags pause <dag_id>` | Pause DAG scheduling |
| `af dags unpause <dag_id>` | Resume DAG scheduling |
| `af dags errors` | List import errors |
| `af dags warnings` | List DAG warnings |
| `af dags stats` | DAG run statistics |
| `af runs list` | List DAG runs |
| `af runs get <dag_id> <run_id>` | Get run details |
| `af runs trigger <dag_id>` | Trigger a DAG run |
| `af runs trigger-wait <dag_id>` | Trigger and wait for completion |
| `af runs diagnose <dag_id> <run_id>` | Diagnose failed run |
| `af tasks list <dag_id>` | List tasks in DAG |
| `af tasks get <dag_id> <task_id>` | Get task definition |
| `af tasks instance <dag_id> <run_id> <task_id>` | Get task instance |
| `af tasks logs <dag_id> <run_id> <task_id>` | Get task logs |
| `af config version` | Airflow version |
| `af config show` | Full configuration |
| `af config connections` | List connections |
| `af config variables` | List variables |
| `af config variable <key>` | Get specific variable |
| `af config pools` | List pools |
| `af config pool <name>` | Get pool details |
| `af config plugins` | List plugins |
| `af config providers` | List providers |
| `af config assets` | List assets/datasets |

## User Intent Patterns

### DAG Operations
- "What DAGs exist?" / "List all DAGs" -> `af dags list`
- "Tell me about DAG X" / "What is DAG Y?" -> `af dags explore <dag_id>`
- "What's the schedule for DAG X?" -> `af dags get <dag_id>`
- "Show me the code for DAG X" -> `af dags source <dag_id>`
- "Stop DAG X" / "Pause this workflow" -> `af dags pause <dag_id>`
- "Resume DAG X" -> `af dags unpause <dag_id>`
- "Are there any DAG errors?" -> `af dags errors`

### Run Operations
- "What runs have executed?" -> `af runs list`
- "Run DAG X" / "Trigger the pipeline" -> `af runs trigger <dag_id>`
- "Run DAG X and wait" -> `af runs trigger-wait <dag_id>`
- "Why did this run fail?" -> `af runs diagnose <dag_id> <run_id>`

### Task Operations
- "What tasks are in DAG X?" -> `af tasks list <dag_id>`
- "Get task logs" / "Why did task fail?" -> `af tasks logs <dag_id> <run_id> <task_id>`

### System Operations
- "What version of Airflow?" -> `af config version`
- "What connections exist?" -> `af config connections`
- "Are pools full?" -> `af config pools`
- "Is Airflow healthy?" -> `af health`

## Common Workflows

### Investigate a Failed Run

```bash
# 1. List recent runs to find failure
af runs list --dag-id my_dag

# 2. Diagnose the specific run
af runs diagnose my_dag manual__2024-01-15T10:00:00+00:00

# 3. Get logs for failed task (from diagnose output)
af tasks logs my_dag manual__2024-01-15T10:00:00+00:00 extract_data
```

### Morning Health Check

```bash
# 1. Overall system health
af health

# 2. Check for broken DAGs
af dags errors

# 3. Check pool utilization
af config pools
```

### Understand a DAG

```bash
# Get comprehensive overview (metadata + tasks + source)
af dags explore my_dag
```

### Check Why DAG Isn't Running

```bash
# Check if paused
af dags get my_dag

# Check for import errors
af dags errors

# Check recent runs
af runs list --dag-id my_dag
```

### Trigger and Monitor

```bash
# Option 1: Trigger and wait (blocking)
af runs trigger-wait my_dag --timeout 1800

# Option 2: Trigger and check later
af runs trigger my_dag
af runs get my_dag <run_id>
```

## Output Format

All commands output JSON (except `instance` commands which use human-readable tables):

```bash
af dags list
# {
#   "total_dags": 5,
#   "returned_count": 5,
#   "dags": [...]
# }
```

Use `jq` for filtering:

```bash
# Find failed runs
af runs list | jq '.dag_runs[] | select(.state == "failed")'

# Get DAG IDs only
af dags list | jq '.dags[].dag_id'

# Find paused DAGs
af dags list | jq '[.dags[] | select(.is_paused == true)]'
```

## Task Logs Options

```bash
# Get logs for specific retry attempt
af tasks logs my_dag run_id task_id --try 2

# Get logs for mapped task index
af tasks logs my_dag run_id task_id --map-index 5
```

## Related Skills

- `testing-dags` - Test DAGs with debugging and fixing cycles
- `debugging-dags` - Comprehensive DAG failure diagnosis and root cause analysis
- `authoring-dags` - Creating and editing DAG files with best practices
- `managing-astro-local-env` - Starting/stopping local Airflow environment
