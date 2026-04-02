---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, validating configurations, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint Implementation

You are helping a user work with Blueprint, a system for composing Airflow DAGs from YAML using reusable Python templates. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `airflow-blueprint` on PyPI
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+, Blueprint 0.2.0+

## Before Starting

Confirm with the user:
1. **Airflow version** ≥2.5
2. **Python version** ≥3.10
3. **Use case**: Blueprint is for standardized, validated templates. If user needs full Airflow flexibility, suggest writing DAGs directly or using DAG Factory instead.

---

## Determine What the User Needs

| User Request | Action |
|--------------|--------|
| "Create a blueprint" / "Define a template" | Go to **Creating Blueprints** |
| "Create a DAG from YAML" / "Compose steps" | Go to **Composing DAGs in YAML** |
| "Customize DAG args" / "Add tags to DAG" | Go to **Customizing DAG-Level Configuration** |
| "Override config at runtime" / "Trigger with params" | Go to **Runtime Parameter Overrides** |
| "Post-process DAGs" / "Add callback" | Go to **Post-Build Callbacks** |
| "Validate my YAML" / "Lint blueprint" | Go to **Validation Commands** |
| "Set up blueprint in my project" | Go to **Project Setup** |
| "Version my blueprint" | Go to **Versioning** |
| "Generate schema" / "Astro IDE setup" | Go to **Schema Generation** |
| Blueprint errors / troubleshooting | Go to **Troubleshooting** |

---

## Project Setup

If the user is starting fresh, guide them through setup:

### 1. Install the Package

```bash
# Add to requirements.txt
airflow-blueprint>=0.2.0

# Or install directly
pip install airflow-blueprint
```

### 2. Create the Loader

Create `dags/loader.py`:

```python
from blueprint import build_all

build_all()
```

DAG-level configuration (schedule, description, tags, default_args, etc.) is handled via YAML fields and `BlueprintDagArgs` templates — see **Customizing DAG-Level Configuration**.

### 3. Verify Installation

```bash
uvx --from airflow-blueprint blueprint list
```

If no blueprints found, user needs to create blueprint classes first.

---

## Creating Blueprints

When user wants to create a new blueprint template:

### Blueprint Structure

```python
# dags/templates/my_blueprints.py
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from blueprint import Blueprint, BaseModel, Field

class MyConfig(BaseModel):
    # Required field with description (used in CLI output and JSON schema)
    source_table: str = Field(description="Source table name")
    # Optional field with default and validation
    batch_size: int = Field(default=1000, ge=1)

class MyBlueprint(Blueprint[MyConfig]):
    """Docstring becomes blueprint description."""

    def render(self, config: MyConfig) -> TaskGroup:
        with TaskGroup(group_id=self.step_id) as group:
            BashOperator(
                task_id="my_task",
                bash_command=f"echo '{config.source_table}'"
            )
        return group
```

### Key Rules

| Element | Requirement |
|---------|-------------|
| Config class | Must inherit from `BaseModel` |
| Blueprint class | Must inherit from `Blueprint[ConfigClass]` |
| `render()` method | Must return `TaskGroup` or `BaseOperator` |
| Task IDs | Use `self.step_id` for the group/task ID |

### Recommend Strict Validation

Suggest adding `extra="forbid"` to catch YAML typos:

```python
from pydantic import ConfigDict

class MyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # fields...
```

---

## Composing DAGs in YAML

When user wants to create a DAG from blueprints:

### YAML Structure

```yaml
# dags/my_pipeline.dag.yaml
dag_id: my_pipeline
schedule: "@daily"
description: "My data pipeline"

steps:
  step_one:
    blueprint: my_blueprint
    source_table: raw.customers
    batch_size: 500

  step_two:
    blueprint: another_blueprint
    depends_on: [step_one]
    target: analytics.output
```

By default, only `schedule` and `description` are supported as DAG-level fields (via the built-in `DefaultDagArgs`). For other fields like `tags`, `default_args`, `catchup`, etc., see **Customizing DAG-Level Configuration**.

### Reserved Keys in Steps

| Key | Purpose |
|-----|---------|
| `blueprint` | Template name (required) |
| `depends_on` | List of upstream step names |
| `version` | Pin to specific blueprint version |

Everything else passes to the blueprint's config.

### Jinja2 Support

YAML supports Jinja2 templating with access to environment variables, Airflow variables/connections, and runtime context:

```yaml
dag_id: "{{ env.get('ENV', 'dev') }}_pipeline"
schedule: "{{ var.value.schedule | default('@daily') }}"

steps:
  extract:
    blueprint: extract
    output_path: "/data/{{ context.ds_nodash }}/output.csv"
    run_id: "{{ context.dag_run.run_id }}"
```

Available template variables:
- `env` — environment variables
- `var` — Airflow Variables
- `conn` — Airflow Connections
- `context` — proxy that generates Airflow template expressions for runtime macros (e.g. `context.ds_nodash`, `context.dag_run.conf`, `context.task_instance.xcom_pull(...)`)

---

## Customizing DAG-Level Configuration

By default, Blueprint supports `schedule` and `description` as DAG-level YAML fields. To use other DAG constructor arguments (tags, default_args, catchup, etc.), define a `BlueprintDagArgs` subclass.

### When to Use

- User wants `tags`, `default_args`, `catchup`, `start_date`, or any other DAG kwargs in YAML
- User wants to derive DAG properties from config (e.g. team name → owner, tier → retries)

### Defining a BlueprintDagArgs Subclass

```python
# dags/templates/my_dag_args.py
from pydantic import BaseModel
from blueprint import BlueprintDagArgs

class MyDagArgsConfig(BaseModel):
    schedule: str | None = None
    description: str | None = None
    tags: list[str] = []
    owner: str = "data-team"
    retries: int = 2

class MyDagArgs(BlueprintDagArgs[MyDagArgsConfig]):
    def render(self, config: MyDagArgsConfig) -> dict[str, Any]:
        return {
            "schedule": config.schedule,
            "description": config.description,
            "tags": config.tags,
            "default_args": {
                "owner": config.owner,
                "retries": config.retries,
            },
        }
```

Then in YAML, the extra fields are validated by the config model:

```yaml
dag_id: my_pipeline
schedule: "@daily"
tags: [etl, production]
owner: data-team
retries: 3

steps:
  extract:
    blueprint: extract
    source_table: raw.data
```

### Rules

- Only **one** `BlueprintDagArgs` subclass per project (raises `MultipleDagArgsError` if more than one exists)
- The `render()` method returns a dict of kwargs passed to the Airflow `DAG()` constructor
- If no custom subclass exists, the built-in `DefaultDagArgs` is used (supports only `schedule` and `description`)

---

## Runtime Parameter Overrides

Blueprint config fields can be overridden at DAG trigger time using Airflow params. This enables users to customize behavior when manually triggering DAGs from the Airflow UI.

### Using `self.param()` in Template Fields

Use `self.param("field")` in operator template fields to make a config field overridable at runtime:

```python
class ExtractConfig(BaseModel):
    query: str = Field(description="SQL query to run")
    batch_size: int = Field(default=1000, ge=1)

class Extract(Blueprint[ExtractConfig]):
    def render(self, config: ExtractConfig) -> TaskGroup:
        with TaskGroup(group_id=self.step_id) as group:
            BashOperator(
                task_id="run_query",
                bash_command=f"run-etl --query {self.param('query')} --batch {self.param('batch_size')}"
            )
        return group
```

### Using `self.resolve_config()` in Python Callables

For `@task` or `PythonOperator` callables, use `self.resolve_config()` to merge runtime params into config:

```python
class Extract(Blueprint[ExtractConfig]):
    def render(self, config: ExtractConfig) -> TaskGroup:
        bp = self  # capture reference for closure

        @task(task_id="run_query")
        def run_query(**context):
            resolved = bp.resolve_config(config, context)
            # resolved.query has the runtime override if one was provided
            execute(resolved.query, resolved.batch_size)

        with TaskGroup(group_id=self.step_id) as group:
            run_query()
        return group
```

### How It Works

- Params are **auto-generated** from Pydantic config models and namespaced per step (e.g. `step_name__field`)
- YAML values become param defaults; Pydantic metadata (description, constraints, enum values) flows through to the Airflow trigger form
- Invalid overrides raise `ValidationError` at execution time

---

## Post-Build Callbacks

Use `on_dag_built` to post-process DAGs after they are constructed. This is useful for adding tags, access controls, audit metadata, or any cross-cutting concern.

```python
from pathlib import Path
from blueprint import build_all

def add_audit_tags(dag, yaml_path: Path) -> None:
    dag.tags.append("managed-by-blueprint")
    dag.tags.append(f"source:{yaml_path.name}")

build_all(on_dag_built=add_audit_tags)
```

The callback receives:
- `dag` — the constructed Airflow `DAG` object (mutable)
- `yaml_path` — the `Path` to the YAML file that defined the DAG

---

## Validation Commands

Run CLI commands with uvx:

```bash
uvx --from airflow-blueprint blueprint <command>
```

| Command | When to Use |
|---------|-------------|
| `blueprint list` | Show available blueprints |
| `blueprint describe <name>` | Show config schema for a blueprint |
| `blueprint describe <name> -v N` | Show schema for specific version |
| `blueprint lint` | Validate all `*.dag.yaml` files |
| `blueprint lint <path>` | Validate specific file |
| `blueprint schema <name>` | Generate JSON schema |
| `blueprint new` | Interactive DAG YAML creation |

### Validation Workflow

```bash
# Check all YAML files
blueprint lint

# Expected output for valid files:
# PASS customer_pipeline.dag.yaml (dag_id=customer_pipeline)
```

---

## Versioning

When user needs to version blueprints for backwards compatibility:

### Version Naming Convention

- v1: `MyBlueprint` (no suffix)
- v2: `MyBlueprintV2`
- v3: `MyBlueprintV3`

```python
# v1 - original
class ExtractConfig(BaseModel):
    source_table: str

class Extract(Blueprint[ExtractConfig]):
    def render(self, config): ...

# v2 - breaking changes, new class
class ExtractV2Config(BaseModel):
    sources: list[dict]  # Different schema

class ExtractV2(Blueprint[ExtractV2Config]):
    def render(self, config): ...
```

### Explicit Name and Version

As an alternative to the class name convention, blueprints can set `name` and `version` directly:

```python
class MyCustomExtractor(Blueprint[ExtractV3Config]):
    name = "extract"
    version = 3

    def render(self, config): ...
```

This is useful when the class name doesn't follow the `NameV{N}` convention or when you want clearer control.

### Using Versions in YAML

```yaml
steps:
  # Pin to v1
  legacy_extract:
    blueprint: extract
    version: 1
    source_table: raw.data

  # Use latest (v2)
  new_extract:
    blueprint: extract
    sources: [{table: orders}]
```

---

## Schema Generation

Generate JSON schemas for editor autocompletion or external tooling:

```bash
# Generate schema for a blueprint
blueprint schema extract > extract.schema.json
```

### Astro Project Auto-Detection

After creating or modifying a blueprint, **automatically check** if the project is an Astro project by looking for a `.astro/` directory (created by `astro dev init`).

If the project is an Astro project, **automatically regenerate schemas** without prompting:

```bash
mkdir -p blueprint/generated-schemas
# For each name from `blueprint list`: blueprint schema NAME > blueprint/generated-schemas/NAME.schema.json
```

The Astro IDE reads `blueprint/generated-schemas/` to render configuration forms. Keeping schemas in sync ensures the visual builder always reflects the latest blueprint configs.

If you cannot determine whether the project is an Astro project, ask the user once and remember for the rest of the session.

---

## Troubleshooting

### "Blueprint not found"

**Cause**: Blueprint class not in Python path.

**Fix**: Check template directory or use `--template-dir`:
```bash
blueprint list --template-dir dags/templates/
```

### "Extra inputs are not permitted"

**Cause**: YAML field name typo with `extra="forbid"` enabled.

**Fix**: Run `blueprint describe <name>` to see valid field names.

### DAG not appearing in Airflow

**Cause**: Missing or broken loader.

**Fix**: Ensure `dags/loader.py` exists and calls `build_all()`:
```python
from blueprint import build_all
build_all()
```

### Validation errors shown as Airflow import errors

As of v0.2.0, Pydantic validation errors are surfaced as Airflow import errors with actionable messages instead of being silently swallowed. The error message includes details on missing fields, unexpected fields, and type mismatches, along with guidance to run `blueprint lint` or `blueprint describe`.

### "Cyclic dependency detected"

**Cause**: Circular `depends_on` references.

**Fix**: Review step dependencies and remove cycles.

### "MultipleDagArgsError"

**Cause**: More than one `BlueprintDagArgs` subclass discovered in the project.

**Fix**: Only one `BlueprintDagArgs` subclass is allowed. Remove or merge duplicates.

### Debugging in Airflow UI

Every Blueprint task has extra fields in **Rendered Template**:
- `blueprint_step_config` - resolved YAML config
- `blueprint_step_code` - Python source of blueprint

---

## Verification Checklist

Before finishing, verify with user:

- [ ] `blueprint list` shows their templates
- [ ] `blueprint lint` passes for all YAML files
- [ ] `dags/loader.py` exists with `build_all()`
- [ ] DAG appears in Airflow UI without parse errors

---

## Reference

- GitHub: https://github.com/astronomer/blueprint
- PyPI: https://pypi.org/project/airflow-blueprint/

### Astro IDE

- Astro IDE Blueprint docs: https://docs.astronomer.io/astro/ide-blueprint
