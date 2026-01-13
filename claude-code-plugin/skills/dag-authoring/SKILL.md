---
name: dag-authoring
description: Workflow and best practices for writing Apache Airflow DAGs. Use when the user wants to create a new DAG, write pipeline code, debug DAG issues, or asks about DAG patterns and conventions. This skill integrates with the Airflow MCP for validation and testing.
---

# DAG Authoring Skill

This skill guides you through creating, validating, and testing Airflow DAGs using the Airflow MCP tools for feedback at every step.

## Workflow Overview

```
┌─────────────────────────────────────┐
│ 1. DISCOVER                         │
│    Understand codebase & environment│
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 2. PLAN                             │
│    Propose structure, get approval  │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 3. IMPLEMENT                        │
│    Write DAG following patterns     │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 4. VALIDATE                         │
│    Check import errors, warnings    │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 5. TEST (with user consent)         │
│    Trigger, monitor, check logs     │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 6. ITERATE                          │
│    Fix issues, re-validate          │
└─────────────────────────────────────┘
```

---

## Phase 1: Discover

Before writing code, understand the context.

### Explore the Codebase

Use file tools to find existing patterns:
- `Glob` for `**/dags/**/*.py` to find existing DAGs
- `Read` similar DAGs to understand conventions
- Check `requirements.txt` for available packages

### Query the Airflow Environment

Use MCP tools to understand what's available:

| Tool | Purpose |
|------|---------|
| `list_connections` | What external systems are configured |
| `list_variables` | What configuration values exist |
| `list_providers` | What operator packages are installed |
| `get_airflow_version` | Version constraints and features |
| `list_dags` | Existing DAGs and naming conventions |
| `list_pools` | Resource pools for concurrency |

**Example discovery questions:**
- "Is there a Snowflake connection?" → `list_connections`
- "What Airflow version?" → `get_airflow_version`
- "Are S3 operators available?" → `list_providers`

---

## Phase 2: Plan

Based on discovery, propose:

1. **DAG structure** - Tasks, dependencies, schedule
2. **Operators to use** - Based on available providers
3. **Connections needed** - Existing or to be created
4. **Variables needed** - Existing or to be created
5. **Packages needed** - Additions to requirements.txt

**Get user approval before implementing.**

---

## Phase 3: Implement

Write the DAG following best practices (see below). Key steps:

1. Create DAG file in appropriate location
2. Update `requirements.txt` if needed
3. Save the file

---

## Phase 4: Validate

**Use the Airflow MCP as a feedback loop.**

### Step 1: Check Import Errors

After saving, wait a few seconds for Airflow to parse:

```
list_import_errors
```

- If your file appears → **fix and retry**
- If no errors → **continue**

Common causes: missing imports, syntax errors, missing packages.

### Step 2: Verify DAG Exists

```
get_dag_details(dag_id="your_dag_id")
```

Check: DAG exists, schedule correct, tags set, paused status.

### Step 3: Check Warnings

```
list_dag_warnings
```

Look for deprecation warnings or configuration issues.

### Step 4: Explore DAG Structure

```
explore_dag(dag_id="your_dag_id")
```

Returns in one call: metadata, tasks, dependencies, source code.

---

## Phase 5: Test

**CRITICAL: Always ask user permission before triggering.**

DAGs can: write to production, send emails, incur costs.

### Ask First

> "The DAG validated successfully. Would you like me to trigger a test run?"

### If Approved

**Trigger and wait:**
```
trigger_dag_and_wait(dag_id="your_dag_id", conf={}, timeout=300)
```

**Or trigger and monitor separately:**
```
trigger_dag(dag_id="your_dag_id")
get_dag_run(dag_id, dag_run_id)
```

### If Something Fails

```
get_task_logs(dag_id, dag_run_id, task_id)
```

Or comprehensive diagnosis:
```
diagnose_dag_run(dag_id, dag_run_id)
```

---

## Phase 6: Iterate

If issues found:
1. Fix the code
2. Re-validate (Phase 4)
3. Re-test with permission (Phase 5)

---

## MCP Tools Quick Reference

| Phase | Tool | Purpose |
|-------|------|---------|
| Discover | `list_connections` | Available connections |
| Discover | `list_variables` | Configuration values |
| Discover | `list_providers` | Installed operators |
| Discover | `get_airflow_version` | Version info |
| Validate | `list_import_errors` | Parse errors (check first!) |
| Validate | `get_dag_details` | Verify DAG config |
| Validate | `list_dag_warnings` | Configuration warnings |
| Validate | `explore_dag` | Full DAG inspection |
| Test | `trigger_dag` | Start a run |
| Test | `trigger_dag_and_wait` | Run and wait |
| Test | `get_dag_run` | Check run status |
| Test | `get_task_logs` | Debug failures |
| Test | `diagnose_dag_run` | Troubleshooting |

---

## Best Practices

### Use TaskFlow API

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id='my_pipeline',
    start_date=datetime(2025, 1, 1),
    schedule='@daily',
    catchup=False,
    default_args={'owner': 'data-team', 'retries': 2},
    tags=['etl', 'production'],
)
def my_pipeline():
    @task
    def extract():
        return {"data": [1, 2, 3]}

    @task
    def transform(data: dict):
        return [x * 2 for x in data["data"]]

    @task
    def load(transformed: list):
        print(f"Loaded {len(transformed)} records")

    load(transform(extract()))

my_pipeline()
```

### Never Hard-Code Credentials

```python
# WRONG
conn_string = "postgresql://user:password@host:5432/db"

# CORRECT - Use connections
from airflow.hooks.base import BaseHook
conn = BaseHook.get_connection("my_postgres_conn")

# CORRECT - Use variables
from airflow.models import Variable
api_key = Variable.get("my_api_key")

# CORRECT - Templating
sql = "SELECT * FROM {{ var.value.table_name }}"
```

### Use Provider Operators

```python
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
```

### Ensure Idempotency

```python
@task
def load_data(data_interval_start, data_interval_end):
    # Delete before insert
    delete_existing(data_interval_start, data_interval_end)
    insert_new(data_interval_start, data_interval_end)
```

### Use Data Intervals

```python
@task
def process(data_interval_start, data_interval_end):
    print(f"Processing {data_interval_start} to {data_interval_end}")

# In SQL
sql = """
    SELECT * FROM events
    WHERE event_time >= '{{ data_interval_start }}'
      AND event_time < '{{ data_interval_end }}'
"""
```

### Organize with Task Groups

```python
from airflow.decorators import task_group

@task_group
def extract_sources():
    @task
    def from_postgres(): ...

    @task
    def from_api(): ...

    return from_postgres(), from_api()
```

### Use Setup/Teardown

```python
from airflow.decorators import setup, teardown

@setup
def create_temp_table(): ...

@teardown
def drop_temp_table(): ...

@task
def process(): ...

create = create_temp_table()
process_task = process()
cleanup = drop_temp_table()

create >> process_task >> cleanup
cleanup.as_teardown(setups=[create])
```

### Include Data Quality Checks

```python
from airflow.providers.common.sql.operators.sql import (
    SQLColumnCheckOperator,
    SQLTableCheckOperator,
)

SQLColumnCheckOperator(
    task_id="check_columns",
    table="my_table",
    column_mapping={
        "id": {"null_check": {"equal_to": 0}},
    },
)

SQLTableCheckOperator(
    task_id="check_table",
    table="my_table",
    checks={"row_count": {"check_statement": "COUNT(*) > 0"}},
)
```

---

## Anti-Patterns

### DON'T: Access Metadata DB Directly

```python
# WRONG - Fails in Airflow 3
from airflow.settings import Session
session.query(DagModel).all()
```

### DON'T: Use Deprecated Imports

```python
# WRONG
from airflow.operators.dummy_operator import DummyOperator

# CORRECT
from airflow.providers.standard.operators.empty import EmptyOperator
```

### DON'T: Use SubDAGs

```python
# WRONG
from airflow.operators.subdag import SubDagOperator

# CORRECT
from airflow.decorators import task_group
```

### DON'T: Use Deprecated Context Keys

```python
# WRONG
execution_date = context["execution_date"]

# CORRECT
logical_date = context["dag_run"].logical_date
data_start = context["data_interval_start"]
```

### DON'T: Hard-Code File Paths

```python
# WRONG
open("include/data.csv")

# CORRECT - Files in dags/
import os
dag_dir = os.path.dirname(__file__)
open(os.path.join(dag_dir, "data.csv"))

# CORRECT - Files in include/
open(f"{os.getenv('AIRFLOW_HOME')}/include/data.csv")
```
