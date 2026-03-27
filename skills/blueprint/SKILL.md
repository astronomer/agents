---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, validating configurations, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint Implementation

You are helping a user work with Blueprint, a system for composing Airflow DAGs from YAML using reusable Python templates. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `airflow-blueprint` on PyPI
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+, Blueprint 0.1.1+

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
airflow-blueprint>=0.1.1

# Or install directly
pip install airflow-blueprint
```

### 2. Create the Loader

Create `dags/loader.py`:

```python
from blueprint import build_all

build_all(
    dag_defaults={
        "default_args": {"owner": "data-team", "retries": 2},
    }
)
```

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
tags: [etl]

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

### Reserved Keys in Steps

| Key | Purpose |
|-----|---------|
| `blueprint` | Template name (required) |
| `depends_on` | List of upstream step names |
| `version` | Pin to specific blueprint version |

Everything else passes to the blueprint's config.

### Jinja2 Support

YAML supports Airflow context:

```yaml
dag_id: "{{ env.get('ENV', 'dev') }}_pipeline"
schedule: "{{ var.value.schedule | default('@daily') }}"
```

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

### "Cyclic dependency detected"

**Cause**: Circular `depends_on` references.

**Fix**: Review step dependencies and remove cycles.

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
