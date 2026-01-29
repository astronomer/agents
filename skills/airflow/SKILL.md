---
name: airflow
description: Manages Apache Airflow operations including listing, testing, running, and debugging DAGs, viewing task logs, checking connections and variables, and monitoring system health. Use when working with Airflow DAGs, pipelines, workflows, or tasks, or when the user mentions testing dags, running pipelines, debugging workflows, dag failures, task errors, dag status, pipeline status, list dags, show connections, check variables, or airflow health.
---

# Airflow Operations

Use `airflow-cli` commands to query, manage, and troubleshoot Airflow workflows.

## Instance Configuration

Manage multiple Airflow instances with persistent configuration:

```bash
# Add instances (auth is optional for open instances)
airflow-cli instance add local --url http://localhost:8080
airflow-cli instance add staging --url https://staging.example.com --username admin --password secret
airflow-cli instance add prod --url https://prod.example.com --token '${AIRFLOW_PROD_TOKEN}'

# List and switch instances
airflow-cli instance list      # Shows all instances in a table
airflow-cli instance use prod  # Switch to prod instance
airflow-cli instance current   # Show current instance
airflow-cli instance delete old-instance

# Override instance for a single command
airflow-cli --instance staging dags list
```

Config file: `~/.airflow-cli/config.yaml` (override with `--config` or `AIRFLOW_CLI_CONFIG`)

Or use environment variables:

```bash
export AIRFLOW_API_URL=http://localhost:8080
export AIRFLOW_USERNAME=admin
export AIRFLOW_PASSWORD=admin
```

Or CLI flags: `airflow-cli --airflow-url http://localhost:8080 --username admin --password admin <command>`

## Quick Reference

| Command | Description |
|---------|-------------|
| `airflow-cli health` | System health check |
| `airflow-cli dags list` | List all DAGs |
| `airflow-cli dags get <dag_id>` | Get DAG details |
| `airflow-cli dags explore <dag_id>` | Full DAG investigation |
| `airflow-cli dags source <dag_id>` | Get DAG source code |
| `airflow-cli dags pause <dag_id>` | Pause DAG scheduling |
| `airflow-cli dags unpause <dag_id>` | Resume DAG scheduling |
| `airflow-cli dags errors` | List import errors |
| `airflow-cli dags warnings` | List DAG warnings |
| `airflow-cli dags stats` | DAG run statistics |
| `airflow-cli runs list` | List DAG runs |
| `airflow-cli runs get <dag_id> <run_id>` | Get run details |
| `airflow-cli runs trigger <dag_id>` | Trigger a DAG run |
| `airflow-cli runs trigger-wait <dag_id>` | Trigger and wait for completion |
| `airflow-cli runs diagnose <dag_id> <run_id>` | Diagnose failed run |
| `airflow-cli tasks list <dag_id>` | List tasks in DAG |
| `airflow-cli tasks get <dag_id> <task_id>` | Get task definition |
| `airflow-cli tasks instance <dag_id> <run_id> <task_id>` | Get task instance |
| `airflow-cli tasks logs <dag_id> <run_id> <task_id>` | Get task logs |
| `airflow-cli config version` | Airflow version |
| `airflow-cli config show` | Full configuration |
| `airflow-cli config connections` | List connections |
| `airflow-cli config variables` | List variables |
| `airflow-cli config variable <key>` | Get specific variable |
| `airflow-cli config pools` | List pools |
| `airflow-cli config pool <name>` | Get pool details |
| `airflow-cli config plugins` | List plugins |
| `airflow-cli config providers` | List providers |
| `airflow-cli config assets` | List assets/datasets |

## User Intent Patterns

### DAG Operations
- "What DAGs exist?" / "List all DAGs" -> `airflow-cli dags list`
- "Tell me about DAG X" / "What is DAG Y?" -> `airflow-cli dags explore <dag_id>`
- "What's the schedule for DAG X?" -> `airflow-cli dags get <dag_id>`
- "Show me the code for DAG X" -> `airflow-cli dags source <dag_id>`
- "Stop DAG X" / "Pause this workflow" -> `airflow-cli dags pause <dag_id>`
- "Resume DAG X" -> `airflow-cli dags unpause <dag_id>`
- "Are there any DAG errors?" -> `airflow-cli dags errors`

### Run Operations
- "What runs have executed?" -> `airflow-cli runs list`
- "Run DAG X" / "Trigger the pipeline" -> `airflow-cli runs trigger <dag_id>`
- "Run DAG X and wait" -> `airflow-cli runs trigger-wait <dag_id>`
- "Why did this run fail?" -> `airflow-cli runs diagnose <dag_id> <run_id>`

### Task Operations
- "What tasks are in DAG X?" -> `airflow-cli tasks list <dag_id>`
- "Get task logs" / "Why did task fail?" -> `airflow-cli tasks logs <dag_id> <run_id> <task_id>`

### System Operations
- "What version of Airflow?" -> `airflow-cli config version`
- "What connections exist?" -> `airflow-cli config connections`
- "Are pools full?" -> `airflow-cli config pools`
- "Is Airflow healthy?" -> `airflow-cli health`

## Common Workflows

### Investigate a Failed Run

```bash
# 1. List recent runs to find failure
airflow-cli runs list --dag-id my_dag

# 2. Diagnose the specific run
airflow-cli runs diagnose my_dag manual__2024-01-15T10:00:00+00:00

# 3. Get logs for failed task (from diagnose output)
airflow-cli tasks logs my_dag manual__2024-01-15T10:00:00+00:00 extract_data
```

### Morning Health Check

```bash
# 1. Overall system health
airflow-cli health

# 2. Check for broken DAGs
airflow-cli dags errors

# 3. Check pool utilization
airflow-cli config pools
```

### Understand a DAG

```bash
# Get comprehensive overview (metadata + tasks + source)
airflow-cli dags explore my_dag
```

### Check Why DAG Isn't Running

```bash
# Check if paused
airflow-cli dags get my_dag

# Check for import errors
airflow-cli dags errors

# Check recent runs
airflow-cli runs list --dag-id my_dag
```

### Trigger and Monitor

```bash
# Option 1: Trigger and wait (blocking)
airflow-cli runs trigger-wait my_dag --timeout 1800

# Option 2: Trigger and check later
airflow-cli runs trigger my_dag
airflow-cli runs get my_dag <run_id>
```

## Output Format

All commands output JSON (except `instance` commands which use human-readable tables):

```bash
airflow-cli dags list
# {
#   "total_dags": 5,
#   "returned_count": 5,
#   "dags": [...]
# }
```

Use `jq` for filtering:

```bash
# Find failed runs
airflow-cli runs list | jq '.dag_runs[] | select(.state == "failed")'

# Get DAG IDs only
airflow-cli dags list | jq '.dags[].dag_id'

# Find paused DAGs
airflow-cli dags list | jq '[.dags[] | select(.is_paused == true)]'
```

## Task Logs Options

```bash
# Get logs for specific retry attempt
airflow-cli tasks logs my_dag run_id task_id --try 2

# Get logs for mapped task index
airflow-cli tasks logs my_dag run_id task_id --map-index 5
```

## Related Skills

- `testing-dags` - Test DAGs with debugging and fixing cycles
- `debugging-dags` - Comprehensive DAG failure diagnosis and root cause analysis
- `authoring-dags` - Creating and editing DAG files with best practices
- `managing-astro-local-env` - Starting/stopping local Airflow environment
