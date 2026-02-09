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

- [Avoid Top-Level Code](#avoid-top-level-code)
- [TaskFlow API](#use-taskflow-api)
- [Credentials Management](#never-hard-code-credentials)
- [Provider Operators](#use-provider-operators)
- [Idempotency](#ensure-idempotency)
- [Data Intervals](#use-data-intervals)
- [Task Groups](#organize-with-task-groups)
- [Dynamic Task Mapping](#use-dynamic-task-mapping)
- [Large Data / XCom](#handle-large-data-xcom-limits)
- [Retries and Scaling](#configure-retries-and-scaling)
- [Deferrable Operators](#use-deferrable-operators)
- [Setup/Teardown](#use-setupteardown)
- [Data Quality Checks](#include-data-quality-checks)
- [Anti-Patterns](#anti-patterns)
- [Assets (Airflow 3.x)](#assets-airflow-3x)

---

## Avoid Top-Level Code

DAG files are parsed every ~30 seconds. Code outside tasks runs on every parse.

```python
# WRONG - Runs on every parse (every 30 seconds!)
hook = PostgresHook("conn")
results = hook.get_records("SELECT * FROM table")  # Executes repeatedly!

@dag(...)
def my_dag():
    @task
    def process(data):
        return data
    process(results)

# CORRECT - Only runs when task executes
@dag(...)
def my_dag():
    @task
    def get_data():
        hook = PostgresHook("conn")
        return hook.get_records("SELECT * FROM table")

    @task
    def process(data):
        return data

    process(get_data())
```

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

## Use Dynamic Task Mapping

Process variable numbers of items in parallel instead of loops:

```python
# WRONG - Sequential, one failure fails all
@task
def process_all():
    for f in ["a.csv", "b.csv", "c.csv"]:
        process(f)

# CORRECT - Parallel execution
@task
def get_files():
    return ["a.csv", "b.csv", "c.csv"]

@task
def process_file(filename): ...

process_file.expand(filename=get_files())

# With constant parameters
process_file.partial(output_dir="/out").expand(filename=get_files())
```

---

## Handle Large Data (XCom Limits)

Airflow does not define a single universal "max XCom size". XComs are designed for **small** values only (do not pass large payloads like dataframes). For large data, write to external/object storage and pass a reference (URI/path) via XCom. See: `https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/xcoms.html`.

```python
# WRONG - May exceed XCom limits
@task
def get_data():
    return huge_dataframe.to_dict()  # Could be huge!

# CORRECT - Return path, not data
@task
def extract(**context):
    path = f"s3://bucket/{context['ds']}/data.parquet"
    data.to_parquet(path)
    return path  # Small string

@task
def transform(path: str):
    data = pd.read_parquet(path)
    ...
```

For automatic offloading, use the Object Storage XCom backend (provider `common-io`): values larger than a configured threshold are stored in object storage, while smaller values remain in the metadata DB. The threshold is **configurable** (docs examples often use `1048576` bytes = 1 MiB).
```bash
AIRFLOW__CORE__XCOM_BACKEND=airflow.providers.common.io.xcom.backend.XComObjectStorageBackend
AIRFLOW__COMMON_IO__XCOM_OBJECTSTORAGE_PATH=s3://conn_id@bucket/xcom
AIRFLOW__COMMON_IO__XCOM_OBJECTSTORAGE_THRESHOLD=1048576
AIRFLOW__COMMON_IO__XCOM_OBJECTSTORAGE_COMPRESSION=gzip
```

---

## Configure Retries and Scaling

```python
from datetime import timedelta

@dag(
    max_active_runs=1,       # Concurrent DAG runs
    max_active_tasks=10,     # Concurrent tasks per run
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
    },
)
def my_dag(): ...

# Use pools for resource-constrained operations
@task(pool="db_pool", retries=5)
def query_database(): ...
```

Environment defaults:
```bash
AIRFLOW__CORE__DEFAULT_TASK_RETRIES=2
AIRFLOW__CORE__PARALLELISM=32
```

---

## Use Deferrable Operators

Free worker slots during long waits:

```python
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

S3KeySensor(
    task_id="wait_for_file",
    bucket_key="data/{{ ds }}/input.csv",
    deferrable=True,  # Frees worker while waiting
)
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

### DON'T: Use `datetime.now()` in Tasks

```python
# WRONG - Not idempotent
today = datetime.today()

# CORRECT - Use execution context
@task
def process(**context):
    logical_date = context["logical_date"]
    start = context["data_interval_start"]
```

---

## Assets (Airflow 3.x)

Data-driven scheduling between DAGs:

```python
from airflow.sdk import dag, task, Asset

# Producer
@dag(schedule="@hourly")
def extract():
    @task(outlets=[Asset("orders_raw")])
    def pull(): ...

# Consumer - triggered when asset updates
@dag(schedule=[Asset("orders_raw")])
def transform():
    @task
    def process(): ...
```
