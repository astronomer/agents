---
name: annotating-task-lineage
description: Annotate Airflow tasks with data lineage using inlets and outlets. Use when the user wants to add lineage metadata to tasks, specify input/output datasets, or enable lineage tracking for operators without built-in OpenLineage extraction.
---

# Annotating Task Lineage with Inlets & Outlets

This skill guides you through adding manual lineage annotations to Airflow tasks using `inlets` and `outlets`.

> **Reference:** See the [OpenLineage provider developer guide](https://airflow.apache.org/docs/apache-airflow-providers-openlineage/stable/guides/developer.html) for the latest supported operators and patterns.

## When to Use This Approach

| Scenario | Use Inlets/Outlets? |
|----------|---------------------|
| Operator has OpenLineage methods (`get_openlineage_facets_on_*`) | ❌ Modify the OL method directly |
| Operator has no built-in OpenLineage extractor | ✅ Yes |
| Simple table-level lineage is sufficient | ✅ Yes |
| Quick lineage setup without custom code | ✅ Yes |
| Need column-level lineage | ❌ Use OpenLineage methods or custom extractor |
| Complex extraction logic needed | ❌ Use OpenLineage methods or custom extractor |

> **Note:** Inlets/outlets are the lowest-priority fallback. If an OpenLineage extractor or method exists for the operator, it takes precedence. Use this approach for operators without extractors.

---

## Supported Types for Inlets/Outlets

You can use **OpenLineage Dataset** objects or **Airflow Assets** for inlets and outlets:

### OpenLineage Datasets (Recommended)

```python
from openlineage.client.event_v2 import Dataset

# Database tables
source_table = Dataset(
    namespace="postgres://mydb:5432",
    name="public.orders",
)
target_table = Dataset(
    namespace="snowflake://account.snowflakecomputing.com",
    name="staging.orders_clean",
)

# Files
input_file = Dataset(
    namespace="s3://my-bucket",
    name="raw/events/2024-01-01.json",
)
```

### Airflow Assets (Airflow 3+)

```python
from airflow.sdk import Asset

# Using Airflow's native Asset type
orders_asset = Asset(uri="s3://my-bucket/data/orders")
```

---

## Basic Usage

### Setting Inlets and Outlets on Operators

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from openlineage.client.event_v2 import Dataset
import pendulum

# Define your lineage datasets
source_table = Dataset(
    namespace="snowflake://account.snowflakecomputing.com",
    name="raw.orders",
)
target_table = Dataset(
    namespace="snowflake://account.snowflakecomputing.com",
    name="staging.orders_clean",
)
output_file = Dataset(
    namespace="s3://my-bucket",
    name="exports/orders.parquet",
)

with DAG(
    dag_id="etl_with_lineage",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    schedule="@daily",
) as dag:

    transform = BashOperator(
        task_id="transform_orders",
        bash_command="echo 'transforming...'",
        inlets=[source_table],           # What this task reads
        outlets=[target_table],          # What this task writes
    )

    export = BashOperator(
        task_id="export_to_s3",
        bash_command="echo 'exporting...'",
        inlets=[target_table],           # Reads from previous output
        outlets=[output_file],           # Writes to S3
    )

    transform >> export
```

### Multiple Inputs and Outputs

Tasks often read from multiple sources and write to multiple destinations:

```python
from openlineage.client.event_v2 import Dataset

# Multiple source tables
customers = Dataset(namespace="postgres://crm:5432", name="public.customers")
orders = Dataset(namespace="postgres://sales:5432", name="public.orders")
products = Dataset(namespace="postgres://inventory:5432", name="public.products")

# Multiple output tables
daily_summary = Dataset(namespace="snowflake://account", name="analytics.daily_summary")
customer_metrics = Dataset(namespace="snowflake://account", name="analytics.customer_metrics")

aggregate_task = PythonOperator(
    task_id="build_daily_aggregates",
    python_callable=build_aggregates,
    inlets=[customers, orders, products],      # All inputs
    outlets=[daily_summary, customer_metrics], # All outputs
)
```

---

## Setting Lineage in Custom Operators

When building custom operators, you have two options:

### Option 1: Implement OpenLineage Methods (Recommended)

This is the preferred approach as it gives you full control over lineage extraction:

```python
from airflow.models import BaseOperator


class MyCustomOperator(BaseOperator):
    def __init__(self, source_table: str, target_table: str, **kwargs):
        super().__init__(**kwargs)
        self.source_table = source_table
        self.target_table = target_table

    def execute(self, context):
        # ... perform the actual work ...
        self.log.info(f"Processing {self.source_table} -> {self.target_table}")

    def get_openlineage_facets_on_complete(self, task_instance):
        """Return lineage after successful execution."""
        from openlineage.client.event_v2 import Dataset
        from airflow.providers.openlineage.extractors import OperatorLineage

        return OperatorLineage(
            inputs=[Dataset(namespace="warehouse://db", name=self.source_table)],
            outputs=[Dataset(namespace="warehouse://db", name=self.target_table)],
        )
```

### Option 2: Set Inlets/Outlets Dynamically

For simpler cases, set lineage within the `execute` method:

```python
from airflow.models import BaseOperator
from openlineage.client.event_v2 import Dataset


class MyCustomOperator(BaseOperator):
    def __init__(self, source_table: str, target_table: str, **kwargs):
        super().__init__(**kwargs)
        self.source_table = source_table
        self.target_table = target_table

    def execute(self, context):
        # Set lineage dynamically based on operator parameters
        self.inlets = [
            Dataset(namespace="warehouse://db", name=self.source_table)
        ]
        self.outlets = [
            Dataset(namespace="warehouse://db", name=self.target_table)
        ]

        # ... perform the actual work ...
        self.log.info(f"Processing {self.source_table} -> {self.target_table}")
```

---

## Dataset Namespace Conventions

Follow [OpenLineage naming conventions](https://openlineage.io/docs/spec/naming) for dataset namespaces:

| Data Source | Namespace Format | Example |
|-------------|------------------|---------|
| PostgreSQL | `postgres://host:port` | `postgres://mydb.example.com:5432` |
| Snowflake | `snowflake://account` | `snowflake://xy12345.us-east-1` |
| BigQuery | `bigquery://project` | `bigquery://my-project` |
| S3 | `s3://bucket` | `s3://data-lake-bucket` |
| GCS | `gs://bucket` | `gs://my-gcs-bucket` |
| Local files | `file://` | `file:///opt/airflow/data` |

---

## Precedence Rules

OpenLineage uses this precedence for lineage extraction:

1. **Custom Extractors** (highest) - User-registered extractors
2. **OpenLineage Methods** - `get_openlineage_facets_on_*` in operator
3. **Hook-Level Lineage** - Lineage collected from hooks via `HookLineageCollector`
4. **Inlets/Outlets** (lowest) - Falls back to these if nothing else extracts lineage

> **Note:** If an extractor or method exists but returns no datasets, OpenLineage will check hook-level lineage, then fall back to inlets/outlets.

---

## Best Practices

### Use Consistent Naming

Define a helper function for consistent dataset creation:

```python
from openlineage.client.event_v2 import Dataset


def warehouse_dataset(schema: str, table: str) -> Dataset:
    """Create a Dataset with standard warehouse settings."""
    return Dataset(
        namespace="snowflake://mycompany.snowflakecomputing.com",
        name=f"{schema}.{table}",
    )


# Usage
source = warehouse_dataset("raw", "orders")
target = warehouse_dataset("staging", "orders_clean")
```

### Document Your Lineage

Add comments explaining the data flow:

```python
transform = SqlOperator(
    task_id="transform_orders",
    sql="...",
    # Lineage: Reads raw orders, joins with customers, writes to staging
    inlets=[
        warehouse_dataset("raw", "orders"),
        warehouse_dataset("raw", "customers"),
    ],
    outlets=[
        warehouse_dataset("staging", "order_details"),
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
| Table-level only (no column lineage) | Use OpenLineage methods or custom extractor |
| Overridden by extractors/methods | Only use for operators without extractors |
| Static at DAG parse time | Set dynamically in `execute()` or use OL methods |

---

## Related Skills

- **creating-openlineage-extractors**: For column-level lineage or complex extraction
- **tracing-upstream-lineage**: Investigate where data comes from
- **tracing-downstream-lineage**: Investigate what depends on data
