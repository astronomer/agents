---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, validating configurations, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint Implementation

You are helping a user work with Blueprint, a system for composing Airflow DAGs from YAML using reusable Python templates. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `airflow-blueprint` on PyPI
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+, Blueprint 0.3.0+

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
| "Build a template from other templates" | Go to **Composing Templates** |
| "Create a DAG from YAML" / "Compose steps" | Go to **Composing DAGs in YAML** |
| "Use a blueprint in an existing Python DAG" / "Generate DAGs in a loop" | Go to **Blueprints in Python DAGs** |
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
airflow-blueprint>=0.3.0

# Or install directly
pip install airflow-blueprint
```

### 2. Create the Loader

Create `dags/loader.py`:

```python
from blueprint import build_all_dags

build_all_dags()
```

> **Use `build_all_dags`, not `build_all`.** The function was renamed in 0.3.0 so the loader's import line contains the substring `dag`, which Airflow's safe-mode DAG file processor requires — otherwise the file is silently skipped and no DAGs appear. `build_all` still works as a deprecated alias (emits `DeprecationWarning`); migrate existing loaders.

DAG-level configuration (schedule, description, tags, default_args, etc.) is handled via YAML fields and `BlueprintDagArgs` templates — see **Customizing DAG-Level Configuration**.

### 3. Verify Installation

```bash
uvx --from airflow-blueprint blueprint list
```

If no blueprints found, user needs to create blueprint classes first.

> **Provider operators in the CLI.** The `uvx --from airflow-blueprint` environment is isolated and does **not** include the Airflow provider packages your Astro Runtime project has. If your templates import provider operators (BigQuery, Snowflake, etc.), add `--with` so the CLI can import them — otherwise `list`/`lint`/`schema` fail with `ModuleNotFoundError: No module named 'airflow.providers.X'`:
>
> ```bash
> uvx --from airflow-blueprint --with apache-airflow-providers-google blueprint list --template-dir dags/templates
> ```

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
| Field types | Must be single-typed and YAML-compatible (see below) |

### Config Field Types Must Be YAML-Compatible

As of 0.3.0, config fields must be single-typed. Multi-type unions like `str | int` or `Union[A, B]` are **rejected at class-definition time** (raises `TypeError`) because they produce ambiguous YAML parsing and `anyOf` schemas. The check recurses through nested models, list items, and dict values.

- **Allowed**: scalars (`str`, `int`, `float`, `bool`), `Literal[...]`, `list[X]`, `dict[str, V]`, nested `BaseModel`, and `Optional[X]` / `X | None` (the nullable pattern).
- **Rejected**: `str | int`, `Union[A, B]`, or any union with more than one non-`None` arm. Bare `Any` and `dict[str, Any]` are rejected for the same reason — use an explicit single type for the value.

### Internal Fields Not Settable from YAML

Use `Field(default=..., init=False)` for fields used inside `render()` that should not be overridable from YAML. They are excluded from the constructor (always use their default) and omitted from JSON Schema output:

```python
class ExtractConfig(BaseModel):
    source_table: str
    _internal_batch_multiplier: int = Field(default=4, init=False)
```

### Recommend Strict Validation

Suggest adding `extra="forbid"` to catch YAML typos:

```python
from pydantic import ConfigDict

class MyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # fields...
```

---

## Composing Templates

A blueprint can instantiate and render **other blueprints** inside its `render()` method, letting you build higher-level templates from lower-level building blocks while exposing a single, flat config to YAML authors.

Inside `render()`, instantiate each child blueprint, set its `step_id`, call `render(...)` with a config you construct, and wire the results together inside a parent `TaskGroup`:

```python
class QualityGateConfig(BaseModel):
    checks: list[str] = Field(default=["nulls", "duplicates"])
    report_channel: str = Field(default="data-alerts")

class QualityGate(Blueprint[QualityGateConfig]):
    """Run checks then send a report — composed from Validate and Report."""

    def render(self, config: QualityGateConfig) -> TaskGroup:
        with TaskGroup(group_id=self.step_id) as group:
            validate = Validate()
            validate.step_id = "validate"
            validate_group = validate.render(ValidateConfig(checks=config.checks))

            report = Report()
            report.step_id = "report"
            report_task = report.render(ReportConfig(channel=config.report_channel))

            validate_group >> report_task
        return group
```

YAML authors then see a single step with a flat config:

```yaml
steps:
  quality:
    blueprint: quality_gate
    checks: [nulls, duplicates, freshness]
    report_channel: "#data-alerts"
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
| `trigger_rule` | Airflow trigger rule for the step (e.g. `all_done`, `one_success`); validated against the installed Airflow version |

Everything else passes to the blueprint's config.

### Trigger Rules (0.3.0)

Use `trigger_rule` to control when a step runs relative to its upstream dependencies — for example, to run a notification step even if an upstream step failed:

```yaml
steps:
  analyze:
    blueprint: analyze
    depends_on: [extract]

  notify:
    blueprint: notify
    depends_on: [analyze]
    trigger_rule: all_done   # run regardless of whether analyze succeeded
```

Valid values are validated dynamically against the installed Airflow's `TriggerRule` enum (`all_success`, `all_done`, `one_success`, `none_failed`, etc.). When the step's blueprint renders a `TaskGroup`, the rule is applied only to the group's **root** tasks (those with no internal upstream), preserving the blueprint author's internal wiring.

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

## Blueprints in Python DAGs

Blueprints aren't tied to the YAML composition flow. Two patterns (both 0.3.0) let you use them from Python — useful for incremental adoption or data-driven DAG generation.

### Inside a Hand-Written DAG

To drop a blueprint-rendered step into an existing Python DAG, instantiate the Blueprint class, set its `step_id`, call `render()`, and wire it in with `>>`:

```python
# dags/hybrid_dag.py
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

from dags.etl_blueprints import Extract, ExtractConfig, Load, LoadConfig

with DAG(dag_id="hybrid_python_dag", start_date=datetime(2024, 1, 1), schedule=None, catchup=False) as dag:
    setup = BashOperator(task_id="setup", bash_command="echo 'setup'")

    extract = Extract()
    extract.step_id = "extract"
    extract_group = extract.render(ExtractConfig(source_table="raw.events", batch_size=100))

    load = Load()
    load.step_id = "load"
    load_task = load.render(LoadConfig(target_table="warehouse.events", mode="append"))

    finalize = BashOperator(task_id="finalize", bash_command="echo 'done'")

    setup >> extract_group >> load_task >> finalize
```

The `step_id` you set determines the `task_id` / `group_id` the blueprint renders under.

### Programmatic Building with `Builder` / `DAGConfig`

For data-driven DAG generation (one DAG per region, tenant, etc.), build DAGs in a loop with `Builder` and `DAGConfig`, then register each in `globals()` so Airflow discovers them:

```python
from blueprint import Builder, DAGConfig

builder = Builder()

for region in ["us", "eu", "apac"]:
    config = DAGConfig(
        dag_id=f"pipeline_{region}",
        schedule="@hourly",
        steps={
            "extract": {"blueprint": "extract", "source_table": f"raw.{region}"},
            "load": {"blueprint": "load", "depends_on": ["extract"], "target_table": f"out.{region}"},
        },
    )
    dag = builder.build(config)
    globals()[dag.dag_id] = dag
```

`DAGConfig` accepts the same fields you would write in YAML (`dag_id`, `steps`, plus any fields your `BlueprintDagArgs` consumes). `Builder`, `DAGConfig`, and `StepConfig` are all exported from `blueprint`. See `examples/advanced/dags/programmatic_dags.py` in the repo.

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

### Opt In with `supports_params = True`

A blueprint must set the class attribute `supports_params = True` for its config fields to register as Airflow params (namespaced as `{step}__{field}`). **Without it, `self.param()` / `self.resolve_config()` do nothing and no fields appear in the trigger form.** Only opt in for blueprints that actually use those methods — otherwise dead params clutter the form with no effect.

### Using `self.param()` in Template Fields

Use `self.param("field")` in operator template fields to make a config field overridable at runtime. Airflow renders the actual value at execution time:

```python
class ExtractConfig(BaseModel):
    query: str = Field(description="SQL query to run")
    batch_size: int = Field(default=1000, ge=1)

class Extract(Blueprint[ExtractConfig]):
    supports_params = True

    def render(self, config: ExtractConfig) -> TaskGroup:
        with TaskGroup(group_id=self.step_id) as group:
            BashOperator(
                task_id="run_query",
                bash_command=f"run-etl --query {self.param('query')} --batch {self.param('batch_size')}"
            )
        return group
```

### Using `self.resolve_config()` in Python Callables

For `@task` or `PythonOperator` callables, use `self.resolve_config()` to merge runtime params into config. It returns a new validated config instance:

```python
class Extract(Blueprint[ExtractConfig]):
    supports_params = True

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

Use `self.param()` for operators with template fields and `self.resolve_config()` for Python logic in `@task` functions; both can be combined in one blueprint.

### How It Works

- Params are **auto-generated** from Pydantic config models and namespaced per step (e.g. `step_name__field`)
- YAML values become param defaults; Pydantic metadata (description, constraints, enum values) flows through to the Airflow trigger form
- Invalid overrides raise `ValidationError` at execution time

### Trigger Form Customization

Pydantic field schema flows through to Airflow's trigger form. Control how each field renders with `json_schema_extra`:

```python
class LoadConfig(BaseModel):
    query: str = Field(description="SQL to execute", json_schema_extra={"format": "multiline"})
    schedule_date: str = Field(default="2024-01-01", json_schema_extra={"format": "date"})
```

Supported `format` values include `"multiline"` (textarea), `"date"`, `"date-time"`, and `"time"` (pickers). Also usable: `examples` (dropdown with free text), `values_display` (human-readable labels for enum/example values), and `description_md` (Markdown descriptions).

**Validation nuance:** only `Field` constraints that map to JSON Schema (`ge`, `le`, `pattern`, `min_length`, `max_length`, `Literal` enums) are enforced in the trigger form. Custom `@field_validator` / `@model_validator` logic does **not** map to JSON Schema, so it runs only at build time and inside `resolve_config()` — not in the form. If custom validators enforce important constraints, call `self.resolve_config()` in your `@task` function so they run on overridden values.

### Triggering with Overrides

Override params via the Airflow UI trigger form, or via the API using `conf` with the namespaced names:

```bash
curl -X POST /api/v2/dags/customer_pipeline/dagRuns \
  -d '{"conf": {"load__target_table": "staging.customers", "load__mode": "append"}}'
```

---

## Post-Build Callbacks

Use `on_dag_built` to post-process DAGs after they are constructed. This is useful for adding tags, access controls, audit metadata, or any cross-cutting concern.

```python
from pathlib import Path
from blueprint import build_all_dags

def add_audit_tags(dag, yaml_path: Path) -> None:
    dag.tags.append("managed-by-blueprint")
    dag.tags.append(f"source:{yaml_path.name}")

build_all_dags(on_dag_built=add_audit_tags)
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
| `blueprint schema <name>` | Generate JSON schema for a blueprint (step template) |
| `blueprint schema --dag-args` | Generate JSON schema for DAG-level YAML fields |
| `blueprint new` | Interactive DAG YAML creation |

### Validation Workflow

```bash
# Check all YAML files
uvx --from airflow-blueprint blueprint lint

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

### Version Rules

- A blueprint's discovered versions must form a contiguous `1..N` sequence. A gap (e.g. v1 and v3 with no v2) raises `NonContiguousVersionError` during discovery.
- Pinning a version that doesn't exist in YAML raises `InvalidVersionError`.

---

## Schema Generation

Generate JSON schemas for editor autocompletion or external tooling:

```bash
# Generate schema for a blueprint (step template)
uvx --from airflow-blueprint blueprint schema extract -o extract.schema.json

# Generate schema for DAG-level YAML fields (dag_id, steps, + custom BlueprintDagArgs fields)
uvx --from airflow-blueprint blueprint schema --dag-args -o dag-args.schema.json
```

Use `--dag-args` (with no blueprint name) to generate the schema for **DAG-level** YAML fields — `dag_id`, `steps`, and any fields your custom `BlueprintDagArgs` exposes — rather than a single step template's config.

As of 0.3.0, each emitted schema includes a top-level `templateType` field — `"blueprint"` for a step template, `"dag_args"` for DAG-level fields — so consumers can tell them apart. The command emits raw JSON when piped or written via `-o/--output` (and pretty, syntax-highlighted JSON when run interactively), so `>` redirection produces valid JSON.

### Astro Project Auto-Detection

After creating or modifying a blueprint, **automatically check** if the project is an Astro project by looking for a `.astro/` directory (created by `astro dev init`).

If the project is an Astro project, **automatically regenerate schemas** without prompting:

```bash
mkdir -p blueprint/generated-schemas
# For each name from `blueprint list`:
#   uvx --from airflow-blueprint blueprint schema NAME -o blueprint/generated-schemas/NAME.schema.json
# Also emit the DAG-level args schema:
#   uvx --from airflow-blueprint blueprint schema --dag-args -o blueprint/generated-schemas/dag-args.schema.json
```

The Astro IDE reads `blueprint/generated-schemas/` to render configuration forms. Keeping schemas in sync ensures the visual builder always reflects the latest blueprint configs.

If you cannot determine whether the project is an Astro project, ask the user once and remember for the rest of the session.

---

## Troubleshooting

### "Blueprint not found"

**Cause**: Blueprint class not in Python path.

**Fix**: Check template directory or use `--template-dir`:
```bash
uvx --from airflow-blueprint blueprint list --template-dir dags/templates/
```

### "Extra inputs are not permitted"

**Cause**: YAML field name typo with `extra="forbid"` enabled.

**Fix**: Run `uvx --from airflow-blueprint blueprint describe <name>` to see valid field names.

### DAG not appearing in Airflow

**Cause**: Missing or broken loader — including a loader that imports the deprecated `build_all`, which Airflow safe-mode may skip.

**Fix**: Ensure `dags/loader.py` exists and calls `build_all_dags()`:
```python
from blueprint import build_all_dags
build_all_dags()
```

### "ModuleNotFoundError: No module named 'airflow.providers.X'" from `blueprint list`/`lint`/`schema`

**Cause**: The standalone `uvx --from airflow-blueprint` CLI environment doesn't include Airflow provider packages that your Astro Runtime project has. A template importing provider operators can't be imported by the CLI. This is the CLI's isolated environment, not your project.

**Fix**: Add `--with apache-airflow-providers-X` to the uvx invocation (common: `apache-airflow-providers-standard`, `-google`, `-snowflake`):
```bash
uvx --from airflow-blueprint --with apache-airflow-providers-snowflake blueprint lint
```

### Validation errors shown as Airflow import errors

As of v0.2.0, Pydantic validation errors are surfaced as Airflow import errors with actionable messages instead of being silently swallowed. The error message includes details on missing fields, unexpected fields, and type mismatches, along with guidance to run `blueprint lint` or `blueprint describe`.

### "Cyclic dependency detected"

**Cause**: Circular `depends_on` references.

**Fix**: Review step dependencies and remove cycles.

### "MultipleDagArgsError"

**Cause**: More than one `BlueprintDagArgs` subclass discovered in the project.

**Fix**: Only one `BlueprintDagArgs` subclass is allowed. Remove or merge duplicates.

### "NonContiguousVersionError" / "InvalidVersionError"

**Cause**: A blueprint's versions don't form a contiguous `1..N` sequence (`NonContiguousVersionError`), or YAML pins a version that doesn't exist (`InvalidVersionError`).

**Fix**: Ensure versions increment by one with no gaps; run `uvx --from airflow-blueprint blueprint list` to see available versions.

### "non-YAML-compatible fields" (TypeError at import)

**Cause**: A config field uses a type Blueprint rejects since 0.3.0 — a multi-type union (e.g. `str | int`), bare `Any`, or `dict[str, Any]`.

**Fix**: Use a single, explicit type. `Optional[X]` / `X | None` is still allowed. See **Creating Blueprints → Config Field Types Must Be YAML-Compatible**.

### Debugging in Airflow UI

Every Blueprint task has extra fields in **Rendered Template**:
- `blueprint_step_config` - resolved YAML config
- `blueprint_step_code` - Python source of blueprint

---

## Verification Checklist

Before finishing, verify with user:

- [ ] `blueprint list` shows their templates
- [ ] `blueprint lint` passes (run it bare to scan all `*.dag.yaml` recursively, or pass a specific file — passing a directory path fails with `Is a directory`)
- [ ] `dags/loader.py` exists with `build_all_dags()`
- [ ] DAG appears in Airflow UI without parse errors

---

## Reference

- GitHub: https://github.com/astronomer/blueprint
- PyPI: https://pypi.org/project/airflow-blueprint/

### Astro IDE

- Astro IDE Blueprint docs: https://docs.astronomer.io/astro/ide-blueprint
