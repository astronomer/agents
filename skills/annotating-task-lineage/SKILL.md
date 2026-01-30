---
name: annotating-task-lineage
description: Annotate Airflow tasks with data lineage using inlets and outlets. Use when the user wants to add lineage metadata to tasks, specify input/output datasets, use Table/File entities, or enable lineage tracking for operators without built-in OpenLineage extraction.
---

# Annotating Task Lineage with Inlets & Outlets

This skill guides you through adding manual lineage annotations to Airflow tasks using `inlets` and `outlets`.

## When to Use This Approach

| Scenario | Use Inlets/Outlets? |
|----------|---------------------|
| Operator has no built-in OpenLineage extractor | ✅ Yes |
| Simple table-level lineage is sufficient | ✅ Yes |
| Quick lineage setup without custom code | ✅ Yes |
| Need column-level lineage | ❌ Use custom extractor instead |
| Complex extraction logic needed | ❌ Use custom extractor instead |

> **Note:** If an OpenLineage extractor exists for the operator, it will override inlets/outlets. Use this approach for operators without extractors.

---

## Entity Types

Airflow provides these lineage entity classes in `airflow.lineage.entities`:

| Entity | Purpose | Example |
|--------|---------|---------|
| `Table` | Database tables | `Table(cluster="warehouse", database="raw", name="orders")` |
| `File` | Files (S3, GCS, local) | `File(url="s3://bucket/path/file.parquet")` |
| `Column` | Specific columns | `Column(name="user_id", data_type="VARCHAR")` |
| `User` | User entities | `User(email="owner@example.com")` |

---

## Basic Usage

### Setting Inlets and Outlets on Operators

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.lineage.entities import Table, File
import pendulum

# Define your lineage entities
source_table = Table(
    cluster="snowflake",
    database="raw",
    name="orders",
)
target_table = Table(
    cluster="snowflake",
    database="staging",
    name="orders_clean",
)
output_file = File(url="s3://my-bucket/exports/orders.parquet")

with DAG(
    dag_id="etl_with_lineage",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    schedule="@daily",
) as dag:

    transform = BashOperator(
        task_id="transform_orders",
        bash_command="echo 'transforming...'",
        inlets=[source_table],           # What this task reads
        outlets=[target_table],           # What this task writes
    )

    export = BashOperator(
        task_id="export_to_s3",
        bash_command="echo 'exporting...'",
        inlets=[target_table],            # Reads from previous output
        outlets=[output_file],            # Writes to S3
    )

    transform >> export
```

### Multiple Inputs and Outputs

Tasks often read from multiple sources and write to multiple destinations:

```python
from airflow.lineage.entities import Table

# Multiple source tables
customers = Table(cluster="postgres", database="crm", name="customers")
orders = Table(cluster="postgres", database="sales", name="orders")
products = Table(cluster="postgres", database="inventory", name="products")

# Multiple output tables
daily_summary = Table(cluster="snowflake", database="analytics", name="daily_summary")
customer_metrics = Table(cluster="snowflake", database="analytics", name="customer_metrics")

aggregate_task = PythonOperator(
    task_id="build_daily_aggregates",
    python_callable=build_aggregates,
    inlets=[customers, orders, products],      # All inputs
    outlets=[daily_summary, customer_metrics], # All outputs
)
```

---

## Setting Lineage in Custom Operators

When building custom operators, set lineage within the `execute` method:

```python
from airflow.models import BaseOperator
from airflow.lineage.entities import Table


class MyCustomOperator(BaseOperator):
    def __init__(self, source_table: str, target_table: str, **kwargs):
        super().__init__(**kwargs)
        self.source_table = source_table
        self.target_table = target_table

    def execute(self, context):
        # Set lineage dynamically based on operator parameters
        self.inlets = [
            Table(cluster="warehouse", database="raw", name=self.source_table)
        ]
        self.outlets = [
            Table(cluster="warehouse", database="staging", name=self.target_table)
        ]

        # ... perform the actual work ...
        self.log.info(f"Processing {self.source_table} -> {self.target_table}")
```

---

## File Lineage Examples

### S3 Files

```python
from airflow.lineage.entities import File

input_file = File(url="s3://data-lake/raw/events/2024-01-01.json")
output_file = File(url="s3://data-lake/processed/events/2024-01-01.parquet")

process_task = BashOperator(
    task_id="process_events",
    bash_command="...",
    inlets=[input_file],
    outlets=[output_file],
)
```

### GCS Files

```python
from airflow.lineage.entities import File

gcs_input = File(url="gs://my-bucket/input/data.csv")
gcs_output = File(url="gs://my-bucket/output/data.parquet")
```

### Local Files

```python
from airflow.lineage.entities import File

local_file = File(url="file:///opt/airflow/data/export.csv")
```

---

## Precedence Rules

OpenLineage uses this precedence for lineage extraction:

1. **Custom Extractors** (highest) - User-registered extractors
2. **OpenLineage Methods** - `get_openlineage_facets_on_*` in operator
3. **Inlets/Outlets** (lowest) - Falls back to these if no extractor exists

> If an extractor exists for your operator, it overrides inlets/outlets. Use inlets/outlets for operators without extractors.

---

## Best Practices

### Use Consistent Naming

Define a helper function for consistent entity creation:

```python
from airflow.lineage.entities import Table


def warehouse_table(schema: str, name: str) -> Table:
    """Create a Table entity with standard warehouse settings."""
    return Table(
        cluster="snowflake.mycompany.com",
        database=schema,
        name=name,
    )


# Usage
source = warehouse_table("raw", "orders")
target = warehouse_table("staging", "orders_clean")
```

### Document Your Lineage

Add comments explaining the data flow:

```python
transform = SqlOperator(
    task_id="transform_orders",
    sql="...",
    # Lineage: Reads raw orders, joins with customers, writes to staging
    inlets=[
        warehouse_table("raw", "orders"),
        warehouse_table("raw", "customers"),
    ],
    outlets=[
        warehouse_table("staging", "order_details"),
    ],
)
```

### Keep Lineage Accurate

- Update inlets/outlets when SQL queries change
- Include all tables referenced in JOINs as inlets
- Include all tables written to (including temp tables if relevant)

---

## Limitations

| Limitation | Workaround |
|------------|------------|
| Table-level only (no column lineage) | Use custom OpenLineage extractor |
| Overridden by extractors | Only use for operators without extractors |
| Static at DAG parse time | Set dynamically in `execute()` for custom operators |

---

## Related Skills

- **creating-openlineage-extractors**: For column-level lineage or complex extraction
- **tracing-upstream-lineage**: Investigate where data comes from
- **tracing-downstream-lineage**: Investigate what depends on data
