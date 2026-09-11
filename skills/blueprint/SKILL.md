---
name: blueprint
description: Define reusable Airflow task group templates with Pydantic validation and compose DAGs from YAML. Use when creating blueprint templates, composing DAGs from YAML, declaring shared variables or per-environment profiles, validating configurations, sharing templates as an installable package, or enabling no-code DAG authoring for non-engineers.
---

# Blueprint Implementation

You are helping a user work with Blueprint, a system for composing Airflow DAGs from YAML using reusable Python templates. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `airflow-blueprint` on PyPI — this skill documents **0.5.0**
> **Repo**: https://github.com/astronomer/blueprint
> **Requires**: Python 3.10+, Airflow 2.5+
> **Cross-references**: the `airflow` skill for Astro CLI, registry, and REST API discovery commands; `authoring-dags` or `dag-factory` when the user needs full Airflow flexibility instead of validated templates.

---

## Determine What the User Needs

| User Request | Action |
|--------------|--------|
| "Create a blueprint" / "Define a template" | Go to **Creating Blueprints** |
| "Build a template from other templates" | Go to **Composing Templates** |
| "Create a DAG from YAML" / "Compose steps" | Go to **Composing DAGs in YAML** |
| "Reuse a value across steps or DAGs" / "Different value per environment" | Go to **Variables and Profiles** |
| "Use a blueprint in an existing Python DAG" / "Generate DAGs in a loop" | Go to **Blueprints in Python DAGs** |
| "Customize DAG args" / "Add tags to DAG" / "Different DAG defaults per folder" | Go to **Customizing DAG-Level Configuration** |
| "Share templates across repos" / "Install blueprints from a package" | Go to **Sharing Blueprints as a Package** |
| "Override config at runtime" / "Trigger with params" | Go to **Runtime Parameter Overrides** |
| "Post-process DAGs" / "Add callback" / "Don't let one bad file break everything" | Go to **Loader Options** |
| "Validate my YAML" / "Lint blueprint" | Go to **Validation Commands** |
| "Set up blueprint in my project" | Go to **Project Setup** |
| "Version my blueprint" | Go to **Versioning** |
| "Generate schema" / "Astro IDE setup" | Go to **Schema Generation** |
| Blueprint errors / troubleshooting | Go to **Troubleshooting** |

---

## Project Setup

If the user is starting fresh, guide them through setup:

### 1. Install the Package

Add `airflow-blueprint>=0.5.0` to `requirements.txt`.

### 2. Create the Loader

Create `dags/loader.py`:

```python
from blueprint import build_all_airflow_dags

build_all_airflow_dags()
```

> **The function name matters.** Airflow's safe-mode DAG file processor only parses files containing both `airflow` and `dag`, so the import line itself is what makes the loader discoverable. `build_all` and `build_all_dags` still work as deprecated aliases that emit `DeprecationWarning`; migrate existing loaders to `build_all_airflow_dags`.

DAG-level configuration (schedule, description, tags, default_args, etc.) is handled via YAML fields and `BlueprintDagArgs` templates — see **Customizing DAG-Level Configuration**.

### 3. Verify Installation

Run `blueprint list` from the project root. If no blueprints are found, the user needs to create blueprint classes first.

---

## Creating Blueprints

### Canonical Example

Config model, generic base class, and a `render()` returning a task or group keyed on `self.step_id`. Adapt this rather than inventing a different structure:

```python
# dags/templates/my_blueprints.py
from airflow.operators.bash import BashOperator
from airflow.utils.task_group import TaskGroup
from blueprint import Blueprint, BaseModel, Field

class MyConfig(BaseModel):
    source_table: str = Field(description="Source table name")
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

Config fields must be single-typed. Multi-type unions like `str | int` or `Union[A, B]` are **rejected at class-definition time** (raises `TypeError`) because they produce ambiguous YAML parsing and `anyOf` schemas. The check recurses through nested models, list items, and dict values.

- **Allowed**: scalars (`str`, `int`, `float`, `bool`), `Literal[...]`, `list[X]`, `dict[str, V]`, nested `BaseModel`, and `Optional[X]` / `X | None` (the nullable pattern).
- **Rejected**: `str | int`, `Union[A, B]`, or any union with more than one non-`None` arm. Bare `Any` and `dict[str, Any]` are rejected for the same reason — use an explicit single type for the value.

### Internal Fields Not Settable from YAML

Use `Field(default=..., init=False)` for fields used inside `render()` that should not be overridable from YAML. They are excluded from the constructor and omitted from JSON Schema output:

```python
class ExtractConfig(BaseModel):
    source_table: str
    _internal_batch_multiplier: int = Field(default=4, init=False)
```

### Recommend Strict Validation for Step Configs

A **step** config model inherits Pydantic's default `extra="ignore"`, so a misspelled field in a step's YAML is silently dropped rather than reported. Suggest `model_config = ConfigDict(extra="forbid")` to turn those typos into errors:

```python
class MyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_table: str
```

DAG args config models are the opposite and need no such setting — Blueprint makes them strict for you (see **Customizing DAG-Level Configuration**).

---

## Composing Templates

A blueprint can instantiate and render **other blueprints** inside its `render()` method, letting you build higher-level templates from lower-level building blocks while exposing a single, flat config to YAML authors.

Inside `render()`, instantiate each child blueprint, set its `step_id`, call `render(...)` with a config you construct, and wire the results together inside a parent `TaskGroup`:

```python
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

YAML authors then see a single step with a flat config, and the composed children stay invisible to them.

---

## Composing DAGs in YAML

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
| `trigger_rule` | Airflow trigger rule for the step; validated against the installed Airflow version |

Everything else passes to the blueprint's config.

### Trigger Rules

Use `trigger_rule` to control when a step runs relative to its upstream dependencies — for example, to run a notification step even if an upstream step failed:

```yaml
steps:
  notify:
    blueprint: notify
    depends_on: [analyze]
    trigger_rule: all_done   # run regardless of whether analyze succeeded
```

Values are validated dynamically against the installed Airflow's `TriggerRule` enum, so the accepted set follows your Airflow version rather than this skill. When the step's blueprint renders a `TaskGroup`, the rule applies only to the group's **root** tasks (those with no internal upstream), preserving the blueprint author's internal wiring.

### Jinja2 Support

YAML supports Jinja2 templating with access to environment variables, Airflow variables/connections, and runtime context:

```yaml
dag_id: "{{ env.get('ENV', 'dev') }}_pipeline"
schedule: "{{ var.value.schedule | default('@daily') }}"

steps:
  extract:
    blueprint: extract
    output_path: "/data/{{ context.ds_nodash }}/output.csv"
```

Available template variables:

- `env` — environment variables
- `var` — Airflow Variables
- `conn` — Airflow Connections
- `context` — proxy that generates Airflow template expressions for runtime macros (e.g. `context.ds_nodash`, `context.dag_run.conf`, `context.task_instance.xcom_pull(...)`)
- `profile` — the active variable profile name, or nothing when none is selected. Useful for deriving a value from the profile rather than enumerating it per profile: `dag_id: "pipeline_{{ profile }}"`

For values that are fixed at parse time and shared across steps or DAGs, prefer **Variables and Profiles** over a Jinja `{% set %}` block — variables are scoped, shareable, and visible to `blueprint lint`.

---

## Variables and Profiles

DAG YAML can declare variables and reference them as `${name}`. Use this to stop repeating a value across steps and DAGs.

Declare them in a `blueprint.vars.yaml` shared by every DAG beneath it, in a DAG's own `vars:` block, or both — nearer declarations override further ones:

```yaml
# dags/blueprint.vars.yaml — shared by every DAG beneath it
vars:
  landing_dataset: raw_events
  warehouse_db: analytics
```

```yaml
# dags/customer_etl.dag.yaml
vars:
  stream: customer_events
  retention_days: 90

steps:
  load:
    blueprint: load
    target_table: ${warehouse_db}.${landing_dataset}.${stream}
    expiration_days: ${retention_days}
```

Substitution runs after YAML parsing, so `expiration_days` stays an `int` rather than becoming the string `"90"`. Values are scalars or lists, and variables may compose (`base: ${db}.${schema}`).

Variable names match `^[A-Za-z_][A-Za-z0-9_-]*$` — hyphens are allowed, and periods are reserved so dotted namespaces can be added later without ambiguity.

> **`${...}` is always a variable reference.** Anything else that uses that syntax — most often a shell variable in a `bash_command` — must be escaped as `$${...}`, or Blueprint tries to resolve it as a variable. Only `$$` immediately before `{` is treated as an escape, so a bare `$$` (a shell PID, an awk field) needs no change. `blueprint lint` reports each unescaped occurrence and names the escape in the error, so lint the project after adopting variables.

### Profiles

A variable can carry a different value per named profile, selected at build time. Environments are the obvious use, but the mechanism is just named selection:

```yaml
profiles: [prod, dev]
vars:
  warehouse_db:
    prod: analytics
    dev: sandbox
```

```python
build_all_airflow_dags(profile="prod" if is_production else "dev")
```

Every profile a DAG declares must give the variable a value; a partial mapping is an error rather than a silent fallback.

### Inspecting Variables

`blueprint vars <path>` shows the resolved value of each variable and where it came from, and flags variables a DAG never references. `blueprint lint` validates every declared profile unless `--profile` narrows it to one. Pass `--root` to match the path the loader builds from, or resolution differs between lint and runtime.

---

## Blueprints in Python DAGs

Blueprints aren't tied to the YAML composition flow. Two patterns let you use them from Python — useful for incremental adoption or data-driven DAG generation.

### Inside a Hand-Written DAG

Instantiate the Blueprint class, set its `step_id`, call `render()`, and wire it in with `>>`:

```python
# dags/hybrid_dag.py
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

from dags.etl_blueprints import Extract, ExtractConfig

with DAG(dag_id="hybrid_python_dag", start_date=datetime(2024, 1, 1), schedule=None, catchup=False) as dag:
    setup = BashOperator(task_id="setup", bash_command="echo 'setup'")

    extract = Extract()
    extract.step_id = "extract"
    extract_group = extract.render(ExtractConfig(source_table="raw.events"))

    setup >> extract_group
```

The `step_id` you set determines the `task_id` / `group_id` the blueprint renders under.

### Programmatic Building with `Builder` / `DAGConfig`

For data-driven DAG generation (one DAG per region, tenant, etc.), build DAGs in a loop and register each in `globals()` so Airflow discovers them:

```python
from blueprint import Builder, DAGConfig

builder = Builder()

for region in ["us", "eu", "apac"]:
    config = DAGConfig(
        dag_id=f"pipeline_{region}",
        schedule="@hourly",
        steps={
            "extract": {"blueprint": "extract", "source_table": f"raw.{region}"},
        },
    )
    dag = builder.build(config, source_path=__file__)
    globals()[dag.dag_id] = dag
```

`DAGConfig` accepts the same fields you would write in YAML. Pass `source_path=__file__` so the DAG args template is resolved from this file's directory the same way a YAML file's would be — without it, resolution falls back to the project-wide default (see **Customizing DAG-Level Configuration**).

---

## Customizing DAG-Level Configuration

By default, Blueprint supports `schedule` and `description` as DAG-level YAML fields. To use other DAG constructor arguments (tags, default_args, catchup, etc.), define a `BlueprintDagArgs` subclass. Its `render()` returns a dict of kwargs passed to the Airflow `DAG()` constructor, so the accepted keys are whatever your Airflow version's `DAG` accepts.

```python
# dags/dag_args.py
from typing import Any

from pydantic import BaseModel
from blueprint import BlueprintDagArgs

class ProjectDagArgsConfig(BaseModel):
    schedule: str | None = None
    tags: list[str] = []
    owner: str = "data-team"

class ProjectDagArgs(BlueprintDagArgs[ProjectDagArgsConfig]):
    def render(self, config: ProjectDagArgsConfig) -> dict[str, Any]:
        return {
            "schedule": config.schedule,
            "tags": config.tags,
            "default_args": {"owner": config.owner},
        }
```

The declared fields then become valid DAG-level YAML keys, validated by the config model.

### Several Templates per Project

A project may define more than one template. Each DAG uses the template defined **closest above it**: resolution starts in the DAG file's own directory and walks up parent directories, so a subdirectory overrides its parents.

```
dags/
  dag_args.py             ProjectDagArgs
  customer.dag.yaml       -> ProjectDagArgs
  sandbox/
    dag_args.py           SandboxDagArgs
    probe.dag.yaml        -> SandboxDagArgs
```

A DAG with no template above it falls back to the one declared `default=True`, then to the sole registered template, then to the built-in `DefaultDagArgs`. A template is scoped to the directory holding the `.py` file that defines it, so **moving that file rescopes it** — the most common surprise in this feature.

Nothing in the DAG YAML changes: a DAG never names its template. Run `blueprint list` to see which template applies to which path, which one is the fallback, and where each is defined; `blueprint lint` names the resolved template per DAG.

A template registers under the snake_case form of its class name — `ProjectDagArgs` becomes `project_dag_args` — which is the name `blueprint schema --dag-args <name>` expects. Setting `name = "..."` overrides it, and must itself be snake_case.

### Undeclared Fields Are Rejected

A DAG args config model defines the DAG YAML's top-level surface, so Blueprint applies `extra="forbid"` to it automatically — an undeclared top-level key is an error rather than a silently ignored one. **This is the opposite default from step configs**, which ignore unknown keys unless you opt in.

This shows up in the generated schema as `additionalProperties: false`, so editors and the Astro IDE reject unknown top-level keys too.

Setting `extra` yourself on the model leaves your choice intact. To defer to the model's own policy instead, pass `allow_extra=True` on the class:

```python
class LooseDagArgs(BlueprintDagArgs[LooseConfig], allow_extra=True):
    ...
```

### Rules

- Two templates in the same directory is an error, as is two sharing a name (`name = "..."` on the class renames one) or more than one declaring `default=True`.
- If no subclass exists anywhere, the built-in `DefaultDagArgs` is used (`schedule` and `description` only).

---

## Sharing Blueprints as a Package

Blueprints can be shared across repositories as an installable package instead of copied files. The package advertises itself under the `airflow_blueprint.blueprints` entry-point group, and Blueprint discovers it once installed, with no per-repo configuration:

```toml
# pyproject.toml of the shared package
[project.entry-points."airflow_blueprint.blueprints"]
company_blueprints = "company_blueprints"
```

The value must be a plain dotted module or package path. The advertised module — and every submodule, if it is a package — is scanned exactly like a locally discovered file, so any `Blueprint` or `BlueprintDagArgs` subclass defined in it is registered.

Consumers install the package and the blueprints appear in `blueprint list` alongside local ones, with the source column distinguishing them. A package that fails to import raises `EntryPointLoadError` rather than silently vanishing from the registry.

To turn discovery off, pass `discover_entry_points=False` to the loader, or the corresponding `--no-entry-points` flag to the CLI (`--help` confirms which commands accept it).

---

## Runtime Parameter Overrides

Blueprint config fields can be overridden at DAG trigger time using Airflow params, letting users customize behavior when manually triggering DAGs.

### Opt In with `supports_params = True`

A blueprint must set the class attribute `supports_params = True` for its config fields to register as Airflow params (namespaced as `{step}__{field}`). **Without it, `self.param()` / `self.resolve_config()` do nothing and no fields appear in the trigger form.** Only opt in for blueprints that actually use those methods — otherwise dead params clutter the form with no effect.

### Canonical Example

Use `self.param()` in operator template fields, where Airflow renders the value at execution time; use `self.resolve_config()` in Python callables, where you need a validated config object. Both can appear in one blueprint:

```python
class Extract(Blueprint[ExtractConfig]):
    supports_params = True

    def render(self, config: ExtractConfig) -> TaskGroup:
        bp = self  # capture reference for the closure

        @task(task_id="run_query")
        def run_query(**context):
            resolved = bp.resolve_config(config, context)
            execute(resolved.query, resolved.batch_size)

        with TaskGroup(group_id=self.step_id) as group:
            BashOperator(
                task_id="shell_step",
                bash_command=f"run-etl --query {self.param('query')}",
            )
            run_query()
        return group
```

### How It Works

- Params are **auto-generated** from Pydantic config models and namespaced per step (e.g. `step_name__field`)
- YAML values become param defaults; Pydantic metadata (description, constraints, enum values) flows through to the Airflow trigger form
- Invalid overrides raise `ValidationError` at execution time
- Override them from the trigger form, or by posting `conf` with the namespaced names to the DAG run endpoint (`af api ls --filter dagRun` finds the current path — see the `airflow` skill)

### Trigger Form Customization

Pydantic field schema flows through to Airflow's trigger form; `json_schema_extra` controls how each field renders (`format` values such as multiline and date pickers, `examples`, `values_display`, `description_md`). The Airflow version determines which are honoured, so check against the form rather than assuming.

**Validation nuance:** only `Field` constraints that map to JSON Schema (`ge`, `le`, `pattern`, `min_length`, `max_length`, `Literal` enums) are enforced in the trigger form. Custom `@field_validator` / `@model_validator` logic does **not** map to JSON Schema, so it runs only at build time and inside `resolve_config()`. If custom validators enforce important constraints, call `self.resolve_config()` in your `@task` function so they run on overridden values.

---

## Loader Options

`build_all_airflow_dags()` takes the options that govern a whole project. The ones that change behaviour materially:

| Option | Effect |
|---|---|
| `profile=` | Selects which profile's values the `${...}` variables resolve to (see **Variables and Profiles**) |
| `skip_invalid_dags=True` | Renders the valid YAML files and skips faulty ones instead of failing the import |
| `discover_entry_points=False` | Turns off discovery of blueprints installed as packages |
| `on_dag_built=` | Callback to post-process each DAG after construction |

`discover_entry_points` is ignored when `bp_registry` is supplied directly, since that registry has already run discovery.

The rest of the signature is plumbing that rarely needs changing: `search_path` and `pattern` control YAML discovery, `register_globals` overrides the caller's `globals()`, `render_templates` and `template_context` govern Jinja, and `bp_registry` supplies a pre-built registry.

### Excluding Files with `.airflowignore`

YAML discovery honours `.airflowignore`, using Airflow's own ignore-file walker — so the syntax, the `core.dag_ignore_file_syntax` setting, and nested ignore files behave exactly as they do for the DAG processor. `blueprint lint` honours it too when scanning a directory, so a draft excluded from Airflow is also excluded from lint; passing that file explicitly still lints it, which is how you check a draft on purpose.

Patterns are matched against the tail of each path, so name patterns like `*.dag.yaml` behave as with `rglob`. `**` is not supported before Python 3.13.

### Post-Build Callbacks

Use `on_dag_built` to post-process DAGs after construction — adding tags, access controls, or audit metadata:

```python
from pathlib import Path
from blueprint import build_all_airflow_dags

def add_audit_tags(dag, yaml_path: Path) -> None:
    dag.tags.append("managed-by-blueprint")
    dag.tags.append(f"source:{yaml_path.name}")

build_all_airflow_dags(on_dag_built=add_audit_tags)
```

The callback receives the constructed Airflow `DAG` (mutable) and the `Path` of the YAML file that defined it.

### Skipping Invalid Files

`skip_invalid_dags=True` stops one bad YAML file from taking down every other DAG in the folder. Explain both costs before recommending it:

- Errors no longer surface as Airflow import errors, because the loader itself parses cleanly. They go to the DAG processor log instead, which is a much less visible place to look.
- Duplicate DAG ids stop being an error — every such file parses, and the first DAG wins.

Pair it with `blueprint lint` in CI, so invalid files are caught somewhere visible.

---

## Validation Commands

Run CLI commands with uvx:

```bash
uvx --from airflow-blueprint blueprint <command>
```

| Command | When to Use |
|---------|-------------|
| `list` | Show available blueprints, versions, sources, and DAG args templates |
| `describe <name>` | Show config schema for a blueprint |
| `lint` | Validate DAG YAML — bare to scan recursively, or pass one file |
| `vars <path>` | Show resolved variables for a DAG and where each came from |
| `schema` | Generate JSON Schema for a blueprint or for DAG-level fields |
| `new` | Interactive DAG YAML creation. `--output-dir` picks where the file lands, which also selects the DAG args template it is validated against |

Every command takes `--help`, and `-h` / `-v` work as shorthands for `--help` / `--version`.

Run them from the **project root**, not from inside `dags/` — a bare invocation resolves `dags/` relative to the working directory, so running from within it finds no blueprints. Use `--template-dir` for any other layout.

> **Provider operators in the CLI.** The `uvx --from airflow-blueprint` environment is isolated and does **not** include the Airflow provider packages your Astro Runtime project has. If templates import provider operators, add `--with <provider-package>` so the CLI can import them — otherwise `list`/`lint`/`schema` fail with `ModuleNotFoundError`:
>
> ```bash
> uvx --from airflow-blueprint --with apache-airflow-providers-google blueprint list --template-dir dags/templates
> ```

---

## Versioning

### Version Naming Convention

Versions are separate classes with a `V{N}` suffix: `Extract` is v1, `ExtractV2` is v2, and each carries its own config model. A blueprint's discovered versions must form a contiguous `1..N` sequence.

```python
class Extract(Blueprint[ExtractConfig]):        # v1
    def render(self, config): ...

class ExtractV2(Blueprint[ExtractV2Config]):    # v2, breaking changes
    def render(self, config): ...
```

### Explicit Name and Version

When the class name doesn't follow the convention, set them directly:

```python
class MyCustomExtractor(Blueprint[ExtractV3Config]):
    name = "extract"
    version = 3

    def render(self, config): ...
```

An explicit `name` must be snake_case (`^[a-z][a-z0-9_]*$`) or the class raises `ValueError` at definition time. Without one, the name is the snake_case form of the class name.

### Using Versions in YAML

Omit `version` to get the latest; pin it to hold a step on an older one:

```yaml
steps:
  legacy_extract:
    blueprint: extract
    version: 1
    source_table: raw.data
```

`blueprint list` shows the discovered versions of each blueprint.

---

## Schema Generation

Generate JSON schemas for editor autocompletion or external tooling. `blueprint schema <name>` emits a step template's config; `blueprint schema --dag-args` emits the DAG-level fields (`dag_id`, `steps`, and whatever your `BlueprintDagArgs` exposes). With multiple DAG args templates, `--dag-args` takes an optional template name.

Each emitted schema includes a top-level `templateType` field — `"blueprint"` for a step template, `"dag_args"` for DAG-level fields — so consumers can tell them apart. The command emits raw JSON when piped or written with `-o/--output`, and pretty, highlighted JSON when run interactively.

> **Write with `-o/--output`, not `>`.** Importing a template can print warnings to stdout — an Airflow deprecation warning from an operator import is the common case — and those interleave with the JSON, leaving redirected output unparseable. `-o` writes the schema alone.

> **Optional fields emit a plain type.** An optional config field is published as `{"type": "string"}`, not an `anyOf` with a null branch — optionality is carried by the schema's `required` array alone. This keeps generated clients and form renderers from producing a union wrapper type for every optional field. Airflow params deliberately differ and keep a nullable type, because an unset optional param is an explicit null rather than an absent key; do not "fix" one to match the other.

### Astro Project Auto-Detection

After creating or modifying a blueprint, **automatically check** whether the project is an Astro project by looking for a `.astro/` directory (created by `astro dev init`).

If it is, **automatically regenerate schemas** without prompting, writing one file per blueprint from `blueprint list` plus the DAG-level args schema, into `blueprint/generated-schemas/`. The Astro IDE reads that directory to render configuration forms, so keeping it in sync ensures the visual builder reflects the latest configs.

If you cannot determine whether the project is an Astro project, ask the user once and remember for the rest of the session.

---

## Troubleshooting

Error messages carry their own remediation hints; read the message before applying anything here.

### "Blueprint not found"

**Cause**: Blueprint class not in Python path.

**Fix**: Point the CLI at the right directory with `--template-dir`, and check `blueprint list` for what is actually discovered. If the blueprint is meant to come from an installed package, confirm entry-point discovery is on.

### "Extra inputs are not permitted"

**Cause**: YAML field name typo with `extra="forbid"` enabled.

**Fix**: Run `blueprint describe <name>` to see valid field names.

### DAG not appearing in Airflow

**Cause**: Missing or broken loader — including a loader that imports a deprecated alias, which Airflow safe-mode may skip.

**Fix**: Ensure `dags/loader.py` calls `build_all_airflow_dags()`. If `skip_invalid_dags=True` is set, the file parses even when a DAG is broken, so check the DAG processor log rather than the import errors view.

### "ModuleNotFoundError: No module named 'airflow.providers.X'" from the CLI

**Cause**: The standalone `uvx --from airflow-blueprint` environment doesn't include the Airflow provider packages your project has, so a template importing provider operators can't be imported. This is the CLI's isolated environment, not your project.

**Fix**: Add `--with apache-airflow-providers-X` to the uvx invocation.

### Unresolved or unexpected `${...}`

**Cause**: A `${...}` that is not a declared variable — commonly a shell variable in a `bash_command`, or a variable declared in a `blueprint.vars.yaml` outside the search root.

**Fix**: Escape non-variable occurrences as `$${...}`. For genuinely missing variables, run `blueprint vars <path>` to see what resolves and `blueprint lint` for the full list; check that `--root` matches the path the loader uses.

### "CyclicVariableError" / "CompositionDepthError"

**Cause**: Variables that reference each other in a loop, or a composition chain deeper than the resolver's limit.

**Fix**: The error names the cycle or the chain. Break it by inlining one value; `blueprint vars <path>` shows what each variable resolves to.

### "MultipleDagArgsError" / "DuplicateDagArgsError" / "MultipleDefaultDagArgsError"

**Cause**: Not that several templates exist — that is supported. These fire when resolution is ambiguous: two templates in one directory, two sharing a name, or more than one declaring `default=True`.

**Fix**: Move one template to the directory whose DAGs should use it, rename one with `name = "..."`, or leave only one `default=True`. `blueprint list` shows which template applies where.

### "DagArgsNotFoundError"

**Cause**: A named DAG args template was requested that isn't registered.

**Fix**: Check the name against `blueprint list`.

### "EntryPointLoadError"

**Cause**: An installed package advertising blueprints failed to import.

**Fix**: Import the module directly to see the real traceback, and confirm the package and its dependencies are installed in the same environment as Airflow.

### "NonContiguousVersionError" / "InvalidVersionError"

**Cause**: A blueprint's versions don't form a contiguous `1..N` sequence, or YAML pins a version that doesn't exist.

**Fix**: Ensure versions increment by one with no gaps; run `blueprint list` to see available versions.

### "non-YAML-compatible fields" (TypeError at import)

**Cause**: A config field uses a type Blueprint rejects — a multi-type union (e.g. `str | int`), bare `Any`, or `dict[str, Any]`.

**Fix**: Use a single, explicit type. `Optional[X]` / `X | None` is still allowed. See **Creating Blueprints → Config Field Types Must Be YAML-Compatible**.

### "Cyclic dependency detected"

**Cause**: Circular `depends_on` references.

**Fix**: Review step dependencies and remove cycles.

### Debugging in Airflow UI

Every Blueprint task has extra fields in **Rendered Template**:

- `blueprint_step_config` — resolved YAML config
- `blueprint_step_code` — Python source of the blueprint

---

## Verification Checklist

Before finishing, verify with the user:

- [ ] `blueprint list` shows their templates, and the expected DAG args template applies to each path
- [ ] `blueprint lint` passes (bare to scan all `*.dag.yaml` recursively, or pass a specific file — passing a directory path fails with `Is a directory`)
- [ ] `blueprint vars` resolves as expected, if variables or profiles are in use
- [ ] `dags/loader.py` exists and calls `build_all_airflow_dags()`
- [ ] DAG appears in Airflow UI without parse errors

---

## Reference

- GitHub: https://github.com/astronomer/blueprint
- PyPI: https://pypi.org/project/airflow-blueprint/

### Astro IDE

- Astro IDE Blueprint docs: https://docs.astronomer.io/astro/ide-blueprint
