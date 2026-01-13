---
name: dag-authoring
description: Best practices for writing Apache Airflow DAGs. Use when the user is creating new DAGs, writing pipeline code, or asks about DAG patterns, conventions, or anti-patterns.
---

# DAG Authoring Best Practices

Follow these guidelines when writing Airflow DAGs to ensure maintainability, security, and reliability.

## Core Principles

### Use TaskFlow API
Prefer the modern TaskFlow API over traditional DAG definitions:

```python
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    dag_id='my_pipeline',
    start_date=datetime(2025, 1, 1),
    schedule='@daily',
    catchup=False,
    default_args={'owner': 'airflow', 'retries': 2},
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
        print(f"Loading {len(transformed)} records")

    data = extract()
    transformed = transform(data)
    load(transformed)

my_pipeline()
```

### Never Hard-Code Credentials
Always use Airflow connections or variables for sensitive data:

```python
# WRONG - Never do this
conn_string = "postgresql://user:password@host:5432/db"

# CORRECT - Use connections
from airflow.hooks.base import BaseHook
conn = BaseHook.get_connection("my_postgres_conn")

# CORRECT - Use variables for non-connection config
from airflow.models import Variable
api_key = Variable.get("my_api_key")

# CORRECT - Use templating in operators
sql = "SELECT * FROM {{ var.value.table_name }}"
```

### Use Built-in Operators
Prefer provider operators over custom implementations:

```python
# CORRECT - Use provider operators
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryInsertJobOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

# Avoid writing custom code when an operator exists
```

### Ensure Tasks Are Idempotent
Tasks should produce the same result when run multiple times:

```python
@task
def load_data(data_interval_start, data_interval_end):
    # CORRECT - Delete before insert for idempotency
    delete_existing_data(data_interval_start, data_interval_end)
    insert_new_data(data_interval_start, data_interval_end)
```

### Break Complex Logic into Small Tasks
Keep tasks focused and reusable:

```python
# WRONG - Monolithic task
@task
def do_everything():
    data = extract_from_api()
    cleaned = clean_data(data)
    transformed = apply_business_logic(cleaned)
    validate(transformed)
    load_to_warehouse(transformed)

# CORRECT - Small, focused tasks
@task
def extract(): ...

@task
def clean(data): ...

@task
def transform(data): ...

@task
def validate(data): ...

@task
def load(data): ...
```

## Configuration Best Practices

### Keep Config Outside Code
Use Airflow variables and connections, not hardcoded values:

```python
# Configuration in variables, not code
DATASET = Variable.get("bigquery_dataset")
TABLE = Variable.get("target_table")

# Or use params for DAG-level config
@dag(
    params={
        "dataset": Param(default="production", type="string"),
        "batch_size": Param(default=1000, type="integer"),
    }
)
```

### Always Specify Dependencies in requirements.txt
Ensure ALL packages are declared:

```text
# requirements.txt
apache-airflow-providers-snowflake>=5.0.0
apache-airflow-providers-google>=10.0.0
pandas>=2.0.0
requests>=2.28.0
```

### Use Explicit Scheduling
Don't rely on defaults - be explicit:

```python
@dag(
    schedule='@daily',      # Explicit schedule
    catchup=False,          # Explicit catchup behavior
    start_date=datetime(2025, 1, 1),  # Explicit start date
    tags=['production', 'etl'],
)
```

## Data Intervals and Templating

### Use Data Intervals Correctly
Understand the difference between logical_date, data_interval_start, and data_interval_end:

```python
@task
def process_data(data_interval_start, data_interval_end):
    """Process data for the interval."""
    print(f"Processing data from {data_interval_start} to {data_interval_end}")

# In SQL with templating
sql = """
    SELECT * FROM events
    WHERE event_time >= '{{ data_interval_start }}'
    AND event_time < '{{ data_interval_end }}'
"""
```

### Template Variables Reference
Common template variables:
- `{{ data_interval_start }}` - Start of the data interval
- `{{ data_interval_end }}` - End of the data interval
- `{{ ds }}` - Logical date as YYYY-MM-DD
- `{{ var.value.my_var }}` - Airflow variable
- `{{ var.json.my_json.key }}` - JSON variable access
- `{{ conn.my_conn.host }}` - Connection attribute

## Task Organization

### Use Task Groups for Logical Grouping

```python
from airflow.decorators import task_group

@task_group
def extract_sources():
    @task
    def extract_postgres(): ...

    @task
    def extract_api(): ...

    return extract_postgres(), extract_api()

@task_group
def quality_checks(data):
    @task
    def check_nulls(data): ...

    @task
    def check_duplicates(data): ...

    check_nulls(data)
    check_duplicates(data)
```

### Use Setup/Teardown for Resource Management

```python
from airflow.decorators import task, setup, teardown

@setup
def create_temp_table():
    """Create temporary staging table."""
    ...

@teardown
def drop_temp_table():
    """Clean up temporary table."""
    ...

@task
def process_data():
    """Main processing using temp table."""
    ...

# Wire them up
create = create_temp_table()
process = process_data()
cleanup = drop_temp_table()

create >> process >> cleanup
cleanup.as_teardown(setups=[create])
```

## Data Quality

### Include Data Quality Checks

```python
from airflow.providers.common.sql.operators.sql import (
    SQLColumnCheckOperator,
    SQLTableCheckOperator,
)

# Column-level checks
column_checks = SQLColumnCheckOperator(
    task_id="check_columns",
    table="my_table",
    column_mapping={
        "id": {"null_check": {"equal_to": 0}},
        "email": {"unique_check": {"equal_to": 0}},
    },
)

# Table-level checks
table_checks = SQLTableCheckOperator(
    task_id="check_table",
    table="my_table",
    checks={
        "row_count": {"check_statement": "COUNT(*) > 0"},
        "recent_data": {"check_statement": "MAX(updated_at) > CURRENT_DATE - 1"},
    },
)
```

## Anti-Patterns to Avoid

### DON'T: Access Metadata DB Directly
```python
# WRONG - Don't do this
from airflow.settings import Session
with Session() as session:
    session.query(DagModel).all()  # Will fail in Airflow 3

# CORRECT - Use the REST API or Airflow client
```

### DON'T: Use Deprecated Imports
```python
# WRONG - Deprecated
from airflow.operators.dummy_operator import DummyOperator

# CORRECT - Use standard provider
from airflow.providers.standard.operators.empty import EmptyOperator
```

### DON'T: Use SubDAGs
```python
# WRONG - SubDAGs are removed
from airflow.operators.subdag import SubDagOperator

# CORRECT - Use TaskGroups instead
from airflow.decorators import task_group
```

### DON'T: Rely on XCom Pickling
```python
# WRONG - Pickling is removed in Airflow 3
return custom_python_object  # Will fail

# CORRECT - Return JSON-serializable data
return {"key": "value", "list": [1, 2, 3]}
```

### DON'T: Use Deprecated Context Keys
```python
# WRONG - Removed in Airflow 3
execution_date = context["execution_date"]

# CORRECT - Use current context keys
logical_date = context["dag_run"].logical_date
data_start = context["data_interval_start"]
```

## Example: Complete ETL Pipeline

```python
from airflow.decorators import dag, task, task_group
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.common.sql.operators.sql import SQLTableCheckOperator
from datetime import datetime

@dag(
    dag_id='sales_etl',
    start_date=datetime(2025, 1, 1),
    schedule='@daily',
    catchup=False,
    default_args={
        'owner': 'data-team',
        'retries': 2,
        'retry_delay': timedelta(minutes=5),
    },
    tags=['etl', 'sales', 'production'],
)
def sales_etl():
    """Daily ETL pipeline for sales data."""

    @task
    def extract_sales(data_interval_start, data_interval_end):
        """Extract sales data for the interval."""
        # Implementation here
        return {"records": 1000}

    @task_group
    def quality_checks():
        """Run data quality validations."""
        SQLTableCheckOperator(
            task_id="check_completeness",
            conn_id="snowflake_default",
            table="staging.sales",
            checks={"has_data": {"check_statement": "COUNT(*) > 0"}},
        )

    @task
    def transform_and_load(extraction_result):
        """Apply transformations and load to warehouse."""
        # Implementation here
        pass

    # Define flow
    extracted = extract_sales()
    quality_checks()
    transform_and_load(extracted)

sales_etl()
```

## Resources

- [Astronomer Learn](https://www.astronomer.io/docs/learn)
- [Airflow Best Practices](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html)
- [TaskFlow API Guide](https://www.astronomer.io/docs/learn/airflow-decorators)
