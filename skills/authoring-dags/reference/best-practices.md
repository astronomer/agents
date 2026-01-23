# DAG Authoring Best Practices

## Import Compatibility

**Airflow 2.x:**
```python
from airflow.decorators import dag, task, task_group, setup, teardown
from airflow.models import Variable
from airflow.hooks.base import BaseHook
```

**Airflow 3.x (Task SDK):**
```python
from airflow.sdk import dag, task, task_group, setup, teardown, Variable, Connection
```

The examples below use Airflow 2 imports for compatibility. On Airflow 3, these still work but are deprecated (AIR31x warnings). For new Airflow 3 projects, prefer `airflow.sdk` imports.

---

## Table of Contents

- [TaskFlow API](#use-taskflow-api)
- [Credentials Management](#never-hard-code-credentials)
- [Provider Operators](#use-provider-operators)
- [Idempotency](#ensure-idempotency)
- [Data Intervals](#use-data-intervals)
- [Task Groups](#organize-with-task-groups)
- [Setup/Teardown](#use-setupteardown)
- [Data Quality Checks](#include-data-quality-checks)
- [Anti-Patterns](#anti-patterns)

---

## Use TaskFlow API

```python
from airflow.decorators import dag, task  # AF3: from airflow.sdk import dag, task
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

---

## Never Hard-Code Credentials

```python
# WRONG
conn_string = "postgresql://user:password@host:5432/db"

# CORRECT - Use connections
from airflow.hooks.base import BaseHook  # AF3: from airflow.sdk import Connection
conn = BaseHook.get_connection("my_postgres_conn")

# CORRECT - Use variables
from airflow.models import Variable  # AF3: from airflow.sdk import Variable
api_key = Variable.get("my_api_key")

# CORRECT - Templating
sql = "SELECT * FROM {{ var.value.table_name }}"
```

---

## Use Provider Operators

```python
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
```

---

## Ensure Idempotency

```python
@task
def load_data(data_interval_start, data_interval_end):
    # Delete before insert
    delete_existing(data_interval_start, data_interval_end)
    insert_new(data_interval_start, data_interval_end)
```

---

## Use Data Intervals

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

---

## Organize with Task Groups

```python
from airflow.decorators import task_group, task  # AF3: from airflow.sdk import task_group, task

@task_group
def extract_sources():
    @task
    def from_postgres(): ...

    @task
    def from_api(): ...

    return from_postgres(), from_api()
```

---

## Use Setup/Teardown

```python
from airflow.decorators import dag, task, setup, teardown  # AF3: from airflow.sdk import ...

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

---

## Include Data Quality Checks

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

# CORRECT - Use task groups instead
from airflow.decorators import task_group  # AF3: from airflow.sdk import task_group
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
