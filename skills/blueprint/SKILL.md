---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, validating configurations, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint: Template-Based DAG Authoring

Blueprint lets platform teams define reusable task group templates in Python and compose them into Airflow DAGs via YAML. Non-engineers can assemble production DAGs without writing Airflow code.

> **Package**: `airflow-blueprint` on PyPI
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+

---

## When to Use Blueprint

- Platform teams want to **standardize task patterns** across the org
- Analysts/data scientists need to **create DAGs without Airflow knowledge**
- You want **validated, type-safe configurations** for task templates
- You need **versioned templates** that don't break existing DAGs

---

## Core Concepts

| Concept | What it is |
|---------|------------|
| **Blueprint** | Python class defining a reusable task template with validated config |
| **Step** | Instance of a blueprint in a DAG YAML with specific values |
| **DAG YAML** | `*.dag.yaml` file composing steps into a workflow |
| **build_all()** | Loader function that discovers YAML and renders Airflow DAGs |

---

## 1. Define Blueprint Templates

Create blueprints in Python files (typically `dags/templates/` or `dags/`):

```python
# dags/etl_blueprints.py
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from blueprint import Blueprint, BaseModel, Field

class ExtractConfig(BaseModel):
    source_table: str = Field(description="Source table (schema.table)")
    batch_size: int = Field(default=1000, ge=1)

class Extract(Blueprint[ExtractConfig]):
    """Extract data from a source table."""

    def render(self, config: ExtractConfig) -> TaskGroup:
        with TaskGroup(group_id=self.step_id) as group:
            BashOperator(
                task_id="validate",
                bash_command=f"echo 'Validating {config.source_table}'"
            )
            BashOperator(
                task_id="extract",
                bash_command=f"echo 'Extracting {config.batch_size} rows'"
            )
        return group

class LoadConfig(BaseModel):
    target_table: str
    mode: str = Field(default="append", pattern="^(append|overwrite)$")

class Load(Blueprint[LoadConfig]):
    """Load data to a target table."""

    def render(self, config: LoadConfig) -> BashOperator:
        return BashOperator(
            task_id=self.step_id,
            bash_command=f"echo 'Loading to {config.target_table} ({config.mode})'"
        )
```

### Key Points

- `render()` returns a **TaskGroup** or single **BaseOperator**
- Config is a **Pydantic model** with validation, defaults, and descriptions
- **Field descriptions** become form labels in Astro IDE
- Use `self.step_id` for task/group IDs

### Strict Validation

Catch typos in YAML by forbidding unknown fields:

```python
from pydantic import BaseModel, ConfigDict

class ExtractConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_table: str
    batch_size: int = 1000
```

---

## 2. Compose DAGs in YAML

Create `*.dag.yaml` files in your `dags/` directory:

```yaml
# dags/customer_pipeline.dag.yaml
dag_id: customer_pipeline
schedule: "@daily"
tags: [etl, customers]

steps:
  extract_customers:
    blueprint: extract
    source_table: raw.customers
    batch_size: 500

  extract_orders:
    blueprint: extract
    source_table: raw.orders

  load:
    blueprint: load
    depends_on: [extract_customers, extract_orders]
    target_table: analytics.customer_orders
    mode: overwrite
```

### Reserved Keys

| Key | Purpose |
|-----|---------|
| `blueprint` | Which blueprint template to use |
| `depends_on` | List of step names this step waits for |
| `version` | Pin to a specific blueprint version |

Everything else is passed to the blueprint's config model.

### Jinja2 Templating

YAML supports Airflow runtime context:

```yaml
dag_id: "{{ env.get('ENV', 'dev') }}_customer_etl"
schedule: "{{ var.value.etl_schedule | default('@daily') }}"

steps:
  extract:
    blueprint: extract
    source_table: "{{ var.value.source_schema }}.customers"
```

---

## 3. Load DAGs

Create a loader file that discovers YAML and renders DAGs:

```python
# dags/loader.py
from blueprint import build_all

build_all(
    dag_defaults={
        "default_args": {"owner": "data-team", "retries": 2},
    }
)
```

### DAG Defaults

Set org-wide defaults. YAML values take precedence. Dict fields are deep-merged.

```python
build_all(
    dag_defaults={
        "schedule": "@daily",
        "tags": ["managed"],
        "default_args": {
            "owner": "data-team",
            "retries": 2,
            "retry_delay_seconds": 300,
        },
    }
)
```

---

## 4. CLI Commands

Run CLI with uvx (no installation required):

```bash
uvx --from airflow-blueprint blueprint <command>
```

Or if installed in your environment:

```bash
blueprint <command>
```

### Commands

| Command | Purpose |
|---------|---------|
| `blueprint list` | List available blueprints |
| `blueprint describe <name>` | Show config schema and example YAML |
| `blueprint describe <name> -v <N>` | Describe specific version |
| `blueprint lint [path]` | Validate DAG YAML (all `*.dag.yaml` if no path) |
| `blueprint schema <name>` | Generate JSON Schema for editor support |
| `blueprint new` | Create new DAG YAML interactively |

### Validation Workflow

```bash
# Validate all DAG YAML files
blueprint lint

# Validate specific file
blueprint lint dags/customer_pipeline.dag.yaml

# Check with custom template directory
blueprint lint --template-dir dags/templates/
```

---

## 5. Versioning Blueprints

Version blueprints by creating separate classes with `V{N}` suffix:

```python
# v1 - original
class ExtractConfig(BaseModel):
    source_table: str
    batch_size: int = 1000

class Extract(Blueprint[ExtractConfig]):
    def render(self, config: ExtractConfig) -> TaskGroup:
        # v1 implementation
        ...

# v2 - breaking changes
class ExtractV2Config(BaseModel):
    sources: list[SourceDef]
    parallel: bool = True

class ExtractV2(Blueprint[ExtractV2Config]):
    def render(self, config: ExtractV2Config) -> TaskGroup:
        # v2 implementation
        ...
```

### Using Versions in YAML

```yaml
steps:
  # Pinned to v1
  extract_legacy:
    blueprint: extract
    version: 1
    source_table: raw.customers

  # Latest version (v2)
  extract_new:
    blueprint: extract
    sources:
      - schema_name: raw
        table: orders
```

---

## 6. Debugging in Airflow UI

Every task rendered by Blueprint exposes context in **Rendered Template**:

- `blueprint_step_config` - resolved YAML config for the step
- `blueprint_step_code` - full Python source of the blueprint class

---

## 7. Generate Schemas for Astro IDE

For the Astro IDE to discover blueprints, generate JSON schemas:

```bash
# Generate schema for each blueprint
blueprint schema extract > blueprint/generated-schemas/extract.schema.json
blueprint schema load > blueprint/generated-schemas/load.schema.json
```

The IDE reads `blueprint/generated-schemas/` to render configuration forms.

---

## Installation

Add to your Airflow project:

```bash
# requirements.txt
airflow-blueprint>=0.1.1
```

Or install directly:

```bash
uv add airflow-blueprint
pip install airflow-blueprint
```

---

## Project Structure

```
dags/
├── templates/           # Blueprint Python classes
│   └── etl_blueprints.py
├── loader.py            # build_all() entry point
├── customer_pipeline.dag.yaml
└── orders_pipeline.dag.yaml
blueprint/
└── generated-schemas/   # JSON schemas for Astro IDE
    ├── extract.schema.json
    └── load.schema.json
```

---

## Programmatic Building

For advanced use cases, build DAGs in Python:

```python
from blueprint import Builder, DAGConfig

config = DAGConfig(
    dag_id="dynamic_pipeline",
    schedule="@hourly",
    steps={
        "step1": {"blueprint": "extract", "source_table": "raw.data"},
        "step2": {"blueprint": "load", "depends_on": ["step1"], "target_table": "out"},
    }
)

dag = Builder().build(config)
```

---

## Blueprint vs DAG Factory

| Aspect | Blueprint | DAG Factory |
|--------|-----------|-------------|
| Abstraction | Task group templates with validation | Full Airflow API exposure |
| Validation | Pydantic type-safe configs | Raw YAML |
| Target users | Platform teams + analysts | Airflow-savvy users |
| Use case | Standardized, governed workflows | Maximum flexibility |

**Use Blueprint** when you want validated, reusable templates for teams.
**Use DAG Factory** when you need full Airflow flexibility.

---

## Related Skills

- **authoring-dags**: General DAG authoring patterns
- **testing-dags**: Testing DAGs after creation
- **cosmos-dbt-core**: Running dbt projects in Airflow
