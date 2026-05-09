---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, validating configurations, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint Implementation

You are helping a user work with Blueprint, a system for composing Airflow DAGs from YAML using reusable Python templates. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `airflow-blueprint` on PyPI
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+, Blueprint 0.2.0+

## Operating Rules

These behaviors apply throughout the session:

- **Apply fixes, don't just describe them.** When you identify a problem, edit the file. Don't explain a fix and stop.
- **Don't leave stubs.** If the user gives you reference material (specs, existing pipeline configs, scripts), extract every artifact it references. Do not write `# TODO: extract the remaining steps`.
- **Verify before declaring done.** A blueprint isn't working until it passes `blueprint lint` AND surfaces in Airflow without import errors AND (if Astro IDE matters to the user) the schema is valid JSON in `blueprint/generated-schemas/`.
- **Local success ≠ Astro Cloud success.** Path resolution, Docker bundle layout, and provider availability differ. Test both, or warn the user when you've only tested locally.

---

## Before Starting

Confirm with the user:
1. **Airflow version** ≥2.5
2. **Python version** ≥3.10
3. **Use case**: Blueprint is for standardized, validated templates. If user needs full Airflow flexibility, suggest writing DAGs directly or using DAG Factory instead.
4. **Reference material**: If the user points at existing pipeline docs, configs from another orchestrator, or a set of scripts — read them first and identify operation archetypes (e.g. extract, transform, validate, load, notify, maintenance) before writing any blueprint code. See **Designing the Blueprint Library**.

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
| "Templates not in Astro IDE library" | Go to **Schema Generation** (almost always invalid JSON) |
| "Standardize many similar pipelines" / "Migrate from another orchestrator" | Go to **Designing the Blueprint Library** |
| "FileNotFoundError on Astro Cloud but works locally" | Go to **Path Resolution Across Environments** |
| Blueprint errors / troubleshooting | Go to **Troubleshooting** |

---

## Designing the Blueprint Library

Before writing code, decide what blueprints exist. This is the highest-leverage decision in the project — getting it wrong leads to a "pipeline runner" instead of a reusable library.

### When the user references existing pipelines

If the user points at reference material — a spec doc, configs from another orchestrator, a directory of scripts, an existing Airflow project — read it end-to-end before designing. Don't stop at the first example.

1. **Enumerate the work.** Read every referenced artifact. Note the inputs, outputs, and side effects of each.
2. **Identify operation archetypes.** Group similar pieces of work. Examples vary by domain:
   - Data pipelines: extract, transform, validate, load, refresh
   - ML workflows: featurize, train, evaluate, deploy, score
   - Ops workflows: provision, configure, verify, notify, decommission
   - Reporting: collect, aggregate, render, distribute
3. **Each archetype is a candidate for its own Blueprint class** with its own typed config — not a stage in a single mega-blueprint.

### Two valid shapes

| Shape | When to use |
|-------|-------------|
| **Multiple focused blueprints** (one per archetype) | Production libraries where developers compose pipelines from named building blocks. Each blueprint has narrow, validated config that maps to one kind of work. Recommended default. |
| **One generic pipeline blueprint** with `pre_steps` / `parallel_steps` / `post_steps` / `maintenance_steps` lists | Demos, prototypes, or when the user explicitly wants one YAML knob to describe an entire workflow shape. Quick to ship, but every YAML re-declares the same operation types. |

If you ship the second shape, say so explicitly: "this is a pipeline runner, not a library — each YAML still has to spell out every step." Don't let the user discover that later.

### Red flags

- One Blueprint class with `pre_steps`/`parallel_steps`/`post_steps` lists when the source material has clearly distinct operation types
- Wrapping a single task in its own `TaskGroup` purely to make the IDE graph "look richer" — it's not best practice and makes IDE forms harder to fill in
- Hardcoding tool or vendor names into a blueprint that could be tool-agnostic (e.g. `bigquery_sql_pipeline` when `warehouse_query_pipeline` would do, or `slack_notify` when the underlying operator could target any chat tool)
- A single blueprint config with a `kind` discriminator that switches between unrelated behaviors — split it into separate blueprints instead

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
"""Airflow DAG loader for Astronomer Blueprint-managed DAG files."""

from blueprint import build_all

build_all()
```

> **Important — safe-mode DAG discovery.** Airflow's DAG file processor uses safe-mode scanning that only reads files containing the words `dag` or `airflow`. A loader.py with just `from blueprint import build_all; build_all()` is silently skipped, the DAG processor reports `Found N files` without including it, and your blueprints never register. The docstring above satisfies safe-mode. Don't remove it.

DAG-level configuration (schedule, description, tags, default_args, etc.) is handled via YAML fields and `BlueprintDagArgs` templates — see **Customizing DAG-Level Configuration**.

### 3. Verify Installation

```bash
uvx --from airflow-blueprint blueprint list --template-dir dags/templates
```

If your blueprints import provider operators (BigQuery, Snowflake, etc.), the standalone Blueprint CLI environment won't have them. Add `--with`:

```bash
# When templates use Google provider operators
uvx --from airflow-blueprint --with apache-airflow-providers-google blueprint list --template-dir dags/templates

# When templates use the standard provider (BashOperator, PythonOperator on Airflow 3+)
uvx --from airflow-blueprint --with apache-airflow-providers-standard blueprint list --template-dir dags/templates
```

If you see `ModuleNotFoundError: No module named 'airflow.providers.X'` from `blueprint list`, that's the standalone CLI environment, not your Astro project. Add `--with apache-airflow-providers-X` to the uvx invocation. The same applies to `blueprint lint` and `blueprint schema`.

If no blueprints found, user needs to create blueprint classes first.

---

## Creating Blueprints

When user wants to create a new blueprint template:

### Blueprint Structure

```python
# dags/templates/my_blueprints.py
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import TaskGroup
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
| `TaskGroup` import | Use `from airflow.sdk import TaskGroup` on Airflow 3+. `airflow.utils.task_group.TaskGroup` is deprecated and emits a warning. |
| `BashOperator`/`PythonOperator` import | Use `from airflow.providers.standard.operators.bash import BashOperator` on Airflow 3+. The standalone Blueprint CLI needs `--with apache-airflow-providers-standard` to import these. |

### Recommend Strict Validation

Suggest adding `extra="forbid"` to catch YAML typos:

```python
from pydantic import ConfigDict

class MyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # fields...
```

### YAML-Compatible Field Types

Blueprint validates that every config field round-trips through YAML. `dict[str, Any]` and bare `Any` are rejected at class definition time with:

```
TypeError: <Class> config model <ConfigClass> has non-YAML-compatible fields:
  params: field 'params': type Any is not YAML-compatible
```

For free-form params/labels/tags, define explicit type aliases:

```python
YamlScalar = str | int | float | bool | None
YamlValue = YamlScalar | list[YamlScalar] | dict[str, YamlScalar]

class StepConfig(BaseModel):
    params: dict[str, YamlValue] = Field(default_factory=dict)
```

Other field types to avoid in top-level config (cause "Unsupported Field" errors in the Astro IDE form renderer):
- Bare `Union[A, B]` without a discriminator
- Nested generics deeper than `dict[str, list[YamlScalar]]`
- Custom Pydantic models referenced by `Annotated[..., Discriminator(...)]`

If you need richer types, hide them inside a single string field that the blueprint parses internally, or break the blueprint into versions.

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

### Cluster Policy Compatibility

Some Astro deployments enforce cluster policies that require specific tags (e.g. `marketing-secrets`, `finance-secrets`) or owner formats. A blueprint that works locally can fail on Astro Cloud with:

```
AirflowClusterPolicyViolation: DAG '<id>' must declare at least one secret-access tag.
Valid tags: {'marketing-secrets', 'finance-secrets'}. DAG currently has tags: {'etl'}
```

When deploying to a customer environment:
1. Ask which tags or owners are required by their cluster policy.
2. Either bake the required tag into `BlueprintDagArgs.render()` so every DAG inherits it, or document it as a required YAML field.

---

## Path Resolution Across Environments

If a blueprint reads files from the project (templates, configs, schemas, scripts, fixtures, anything under `include/` or similar), it needs to resolve those paths in a way that works both locally and on Astro Cloud. This is the single most common reason a Blueprint project works locally and fails when deployed.

### The problem

`Path(__file__).resolve().parents[N]` works locally because the layout is stable: `<project>/dags/templates/foo.py`. On Astro Cloud, DAGs are bundled and parsed from a transient path like:

```
/tmp/airflow/dag_bundles/astro/main/dags/<timestamp>/dags/templates/foo.py
```

…but project files like `include/...` live at `/usr/local/airflow/include/...`. So `parents[2] / "include/some_file"` resolves under the bundle, where the file does not exist, and you get a `FileNotFoundError` from inside the blueprint at parse time. Locally everything looked fine.

### The fix

Resolve project-relative paths against multiple roots. `AIRFLOW_HOME` is set in every Astro deployment and points at the project root inside the container, so it works as a stable anchor in both environments.

```python
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AIRFLOW_HOME = Path(os.environ.get("AIRFLOW_HOME", "/usr/local/airflow"))


def _resolve_project_path(relative_path: str) -> Path:
    """Resolve a project-relative path. Works locally and on Astro Cloud."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Not found: {relative_path}")

    for root in (PROJECT_ROOT, PROJECT_ROOT.parent, AIRFLOW_HOME):
        resolved = root / candidate
        if resolved.exists():
            return resolved

    raise FileNotFoundError(
        f"Not found in any root: {relative_path}. "
        f"Checked: {PROJECT_ROOT}, {PROJECT_ROOT.parent}, {AIRFLOW_HOME}"
    )
```

This same pattern applies regardless of what the file is — SQL, YAML, JSON, a Python module loaded by path, a CSV fixture, etc.

Apply the same logic to `template_searchpath` in `BlueprintDagArgs.render()`:

```python
"template_searchpath": [str(PROJECT_ROOT), str(AIRFLOW_HOME)],
```

### Verifying the fix

The fix is invisible locally because both roots resolve to the same files. To prove it works:
1. Deploy to Astro and check the import-error panel (`af dags errors` or the deployment logs page).
2. If you don't have an Astro deployment handy, simulate it locally: `docker exec <dag-processor-container> python -c "from pathlib import Path; print(Path('include/sql/foo.sql').resolve())"` from inside the bundled DAG path.

Never tell the user "ready to deploy" if you've only verified the local path.

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

### CRITICAL: Always use `--output`, never shell redirect

The Blueprint CLI uses Rich for pretty terminal output. Piping `blueprint schema NAME > file.json` captures the **rendered** output — wrapped lines, padding spaces, and dropped commas at line boundaries — producing a file that *looks* like JSON but fails `json.loads()`. The Astro IDE silently drops invalid schema files, so the symptom is "my templates don't show up in the IDE library" with no error message anywhere.

**Always do this:**

```bash
blueprint schema extract --output blueprint/generated-schemas/extract.schema.json
```

**Never do this:**

```bash
# WRONG — produces invalid JSON, IDE silently ignores it
blueprint schema extract > blueprint/generated-schemas/extract.schema.json
```

Validate after generating:

```bash
python -c "import json; json.loads(open('blueprint/generated-schemas/extract.schema.json').read()); print('valid')"
```

A correctly generated schema includes `blueprint` and `version` constants under `properties` and lists both as required. If those are missing, the file is wrong.

### Astro Project Auto-Detection

After creating or modifying a blueprint, **automatically check** if the project is an Astro project by looking for a `.astro/` directory (created by `astro dev init`).

If the project is an Astro project, **automatically regenerate schemas** without prompting:

```bash
mkdir -p blueprint/generated-schemas

# For each blueprint name from `blueprint list`:
uvx --from airflow-blueprint --with apache-airflow-providers-standard \
  blueprint schema NAME --template-dir dags/templates \
  --output blueprint/generated-schemas/NAME.schema.json
```

After regenerating, **delete stale schema files** for blueprints you've renamed or removed. The IDE reads every file in `generated-schemas/`, so a leftover schema for a deleted blueprint will still appear in the library.

The Astro IDE reads `blueprint/generated-schemas/` to render configuration forms. Keeping schemas in sync — and committed to the branch the IDE is reading — ensures the visual builder always reflects the latest blueprint configs. If the IDE doesn't show templates after a deploy, check three things in order: (1) the schema file is valid JSON, (2) the schema file is committed and pushed, (3) the IDE is reading the same branch.

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

### `ModuleNotFoundError: No module named 'airflow.providers.X'` from `blueprint list`/`lint`/`schema`

**Cause**: The standalone `uvx --from airflow-blueprint` environment does not include Airflow providers, even though your Astro Runtime project does.

**Fix**: Add `--with apache-airflow-providers-X` to the uvx invocation. The most common ones for blueprints:
- `apache-airflow-providers-standard` — needed for `BashOperator`/`PythonOperator` on Airflow 3+
- `apache-airflow-providers-google` — BigQuery, GCS, etc.
- `apache-airflow-providers-snowflake` — Snowflake operators

### DAG not appearing in Airflow (no error, no DAG either)

**Most common cause**: `dags/loader.py` is being skipped by Airflow safe-mode DAG discovery because it doesn't contain the words `dag` or `airflow`.

**Fix**: Add a docstring:
```python
"""Airflow DAG loader for Astronomer Blueprint-managed DAG files."""

from blueprint import build_all

build_all()
```

Confirm by checking the DAG processor logs (`astro dev logs --dag-processor`). The "DAG File Processing Stats" table will list every file the processor actually scanned. If `loader.py` is missing from that table, it was filtered out by safe-mode.

**Other causes**: missing `dags/templates/__init__.py`, blueprint class import fails (check `astro dev logs --dag-processor` for tracebacks).

### `TypeError: ... has non-YAML-compatible fields`

**Cause**: A config field uses `Any`, an unconstrained `dict[str, Any]`, or a type Blueprint can't serialize through YAML.

**Fix**: Replace with explicit types. See **YAML-Compatible Field Types** above.

### `FileNotFoundError` only on Astro Cloud (works locally)

**Cause**: Blueprint resolves `include/...` paths against `Path(__file__).parents[2]`, which points into the bundle directory on Astro, not the project root.

**Fix**: See **Path Resolution Across Environments** — search multiple roots including `AIRFLOW_HOME`.

### Templates don't appear in Astro IDE library

This has one or two specific causes — work through them in order:

1. **Schema file is invalid JSON.** Most common. Run:
   ```bash
   python -c "import json; json.loads(open('blueprint/generated-schemas/NAME.schema.json').read())"
   ```
   If that errors, the schema was generated with shell redirect (`>`) instead of `--output`. Regenerate with `--output`. See **Schema Generation**.

2. **Schema file isn't committed/deployed.** The IDE reads the schema from the branch it's bound to. Verify `git status blueprint/generated-schemas/` is clean and the changes are pushed.

3. **Stale schema for a renamed blueprint.** If you renamed `bigquery_sql_pipeline` → `sql_script_pipeline`, delete `blueprint/generated-schemas/bigquery_sql_pipeline.schema.json`.

4. **"Unsupported Field" error visible in the IDE form.** A Pydantic field type isn't supported by the IDE's form renderer. See **YAML-Compatible Field Types**.

### `AirflowClusterPolicyViolation` on Astro

**Cause**: Customer cluster policy requires specific tags or owner formats.

**Fix**: Add the required tag in `BlueprintDagArgs.render()` or in YAML. See **Cluster Policy Compatibility**.

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

Before declaring the work done, verify all of these:

- [ ] `blueprint list --template-dir dags/templates` shows every expected blueprint
- [ ] `blueprint lint` passes for every `*.dag.yaml` file (loop over them; `blueprint lint dags/` on a directory currently fails with `Is a directory`)
- [ ] `dags/loader.py` has a docstring containing "Airflow" or "DAG" (safe-mode discovery)
- [ ] DAG appears in Airflow UI with `has_import_errors: false` (run `af dags get <dag_id>`)
- [ ] If the project is on Astro: deployed and confirmed import-error-free in the Astro UI, **not just locally**
- [ ] If Astro IDE is in scope:
  - `blueprint/generated-schemas/<name>.schema.json` exists for every blueprint
  - Each schema file passes `python -c "import json; json.loads(open(p).read())"`
  - Each schema file contains `blueprint` and `version` constants under `properties`
  - Stale schemas for renamed/deleted blueprints are removed
  - Schema files are committed and pushed to the branch the IDE reads
- [ ] If the blueprint reads any project-relative paths: verified to resolve under both `PROJECT_ROOT` and `AIRFLOW_HOME`
- [ ] If a customer cluster policy is in play: required tags are present on every DAG

---

## Reference

- GitHub: https://github.com/astronomer/blueprint
- PyPI: https://pypi.org/project/airflow-blueprint/

### Astro IDE

- Astro IDE Blueprint docs: https://docs.astronomer.io/astro/ide-blueprint
