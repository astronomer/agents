---
name: dag-factory
description: Author Apache Airflow DAGs declaratively with dag-factory YAML configs. Use when creating dag-factory templates, composing DAGs from YAML for dag-factory, configuring defaults/dynamic tasks/datasets/callbacks for dag-factory, or validating dag-factory configurations.
---

# DAG Factory

You are helping a user build Apache Airflow DAGs declaratively with **dag-factory**, a library that turns YAML configuration files into Airflow DAGs. Execute steps in order and prefer the simplest configuration that meets the user's needs.

> **Package**: `dag-factory` on PyPI
> **Repo**: https://github.com/astronomer/dag-factory
> **Docs**: https://astronomer.github.io/dag-factory/latest/
> **Targets**: dag-factory **v1.0+** only. For pre-1.0 projects, see [reference/migration.md](reference/migration.md) before applying any guidance from this skill.
> **Requires**: Python 3.10+, Airflow 2.4+ (Airflow 3 supported)

## Before Starting

Confirm with the user:
1. **Airflow version** ≥2.4
2. **Python version** ≥3.10
3. **dag-factory version**: this skill targets **v1.0+**. If the project is on <1.0, follow [reference/migration.md](reference/migration.md) to upgrade before continuing.
4. **Use case**: dag-factory is for declarative, low-code DAG authoring. If the user needs reusable, validated Pythonic templates with Pydantic, suggest **blueprint** instead. If they need full Python flexibility, suggest the **authoring-dags** skill.

---

## Determine What the User Needs

| User Request | Action |
|--------------|--------|
| "Create a YAML DAG" / "Convert this Python DAG to YAML" | Go to **Defining a DAG in YAML** |
| "Set up dag-factory in my project" | Go to **Project Setup** |
| "Share defaults across DAGs" / "Set start_date once" | Go to **Defaults** |
| "Use a custom operator" / "Use KPO / Slack / Snowflake" | Go to **Custom & Provider Operators** |
| "Dynamic / mapped tasks" / "expand / partial" | Go to **Dynamic Task Mapping** |
| "Schedule on dataset" / "Outlets and inlets" | Go to **Datasets** |
| "Add a callback" / "Slack on failure" | Go to **Callbacks** |
| "Use a timetable" / "datetime in YAML" / "timedelta in YAML" | Go to **Custom Python Objects (`__type__`)** |
| "Lint my YAML" / "Validate" | Go to **Validation Commands** |
| "Convert Airflow 2 YAML to Airflow 3" | Go to **Validation Commands** (`dagfactory convert`) |
| "Migrate from dag-factory <1.0" | See [reference/migration.md](reference/migration.md) |
| dag-factory errors / troubleshooting | Go to **Troubleshooting** |

---

## Project Setup

### 1. Install the Package

Add to `requirements.txt`:

```
dag-factory>=1.0.0
```

dag-factory **does not** install Airflow providers automatically. Install any provider packages your YAML references (e.g., `apache-airflow-providers-slack`, `apache-airflow-providers-cncf-kubernetes`).

### 2. Create the Loader

Create `dags/load_dags.py` so Airflow's DAG processor will pick it up:

```python
import os
from pathlib import Path

from dagfactory import load_yaml_dags

CONFIG_ROOT_DIR = Path(os.getenv("CONFIG_ROOT_DIR", "/usr/local/airflow/dags/"))

# Option A: load every *.yml / *.yaml under a folder
load_yaml_dags(globals_dict=globals(), dags_folder=str(CONFIG_ROOT_DIR))

# Option B: load a single file
# load_yaml_dags(globals_dict=globals(), config_filepath=str(CONFIG_ROOT_DIR / "my_dag.yml"))

# Option C: load from an in-Python dict
# load_yaml_dags(globals_dict=globals(), config_dict={...})
```

`globals_dict=globals()` is required so generated DAG objects are registered into the module namespace where Airflow can discover them.

### 3. Verify Installation

```bash
dagfactory --version
```

---

## Defining a DAG in YAML

Each top-level YAML key (other than `default`) defines a DAG. The key becomes the `dag_id`. **Use the list format for `tasks` and `task_groups`** — it is the recommended format since v1.0.0.

```yaml
# dags/example_dag_factory.yml
default:
  default_args:
    start_date: 2024-11-11

basic_example_dag:
  default_args:
    owner: "custom_owner"
  description: "this is an example dag"
  schedule: "0 3 * * *"
  catchup: false
  task_groups:
    - group_name: "example_task_group"
      tooltip: "this is an example task group"
      dependencies: [task_1]
  tasks:
    - task_id: "task_1"
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo 1"
    - task_id: "task_2"
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo 2"
      dependencies: [task_1]
    - task_id: "task_3"
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo 3"
      dependencies: [task_1]
      task_group_name: "example_task_group"
```

### Key Fields

| Field | Where | Purpose |
|-------|-------|---------|
| `default` | top-level | Shared DAG-level args applied to every DAG in this file |
| `default_args` | DAG or `default` block | Standard Airflow `default_args` (owner, retries, start_date, ...) |
| `schedule` | DAG | Cron expression, preset (`@daily`), Dataset list, or `__type__` timetable |
| `catchup` / `description` / `tags` | DAG | Standard Airflow DAG kwargs |
| `tasks` | DAG | List of task dicts; each requires `task_id` and `operator` |
| `operator` | task | **Full import path** to operator class (e.g. `airflow.operators.bash.BashOperator`) |
| `dependencies` | task / task_group | List of upstream `task_id`s or `group_name`s |
| `task_groups` | DAG | List of group dicts; each requires `group_name` |
| `task_group_name` | task | Assigns a task to a task group |

Tasks do **not** need to be ordered by dependency in the YAML — dag-factory resolves the DAG topology.

### Dictionary Format (Legacy)

Pre-1.0 dictionary format (where `tasks` is a dict keyed by `task_id`) still works for backward compatibility, but prefer the list format for new code.

---

## Defaults

There are four ways to set defaults, in **precedence order** (highest first):

1. `default_args` / DAG-level keys inside an individual DAG
2. The top-level `default:` block in the same YAML file
3. `defaults_config_dict=` argument to `load_yaml_dags`
4. A `defaults.yml` (or `defaults.yaml`) file via `defaults_config_path=` (or auto-detected next to the DAG YAML)

> Note: loader argument names and several other field names changed in v1.0.0. See [reference/migration.md](reference/migration.md) if you're working on an older project.

### `default` Block in the Same File

Powerful for templating multiple DAGs from one file:

```yaml
default:
  default_args:
    owner: "data-team"
    start_date: 2025-01-01
    retries: 2
  catchup: false
  schedule: "@daily"

dag_one:
  description: "first DAG"
  tasks:
    - task_id: t1
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo one"

dag_two:
  description: "second DAG"
  tasks:
    - task_id: t1
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo two"
```

### `defaults.yml` File

Place a `defaults.yml` next to the DAG YAML, or point `defaults_config_path` at a parent directory. dag-factory **merges** all `defaults.yml` files walking up the directory tree, with the file closest to the DAG YAML winning. DAG-level args (e.g. `schedule`, `catchup`) go at the root of `defaults.yml`; per-task defaults go under `default_args`.

```yaml
# defaults.yml
schedule: 0 1 * * *
catchup: false
default_args:
  start_date: '2024-12-31'
  owner: data-team
```

---

## Custom & Provider Operators

Reference any operator by its **full Python import path**. dag-factory passes all other task keys as kwargs to that operator.

```yaml
tasks:
  - task_id: begin
    operator: airflow.providers.standard.operators.empty.EmptyOperator
  - task_id: make_bread
    operator: customized.operators.breakfast_operators.MakeBreadOperator
    bread_type: 'Sourdough'
```

The operator's package must be installed and importable. For Airflow 3, prefer `airflow.providers.standard.operators.*` over the legacy `airflow.operators.*` paths — the `dagfactory convert` CLI rewrites these automatically.

### KubernetesPodOperator

Specify the operator path and pass kwargs directly. As of v1.0, dag-factory no longer does legacy type casting — use `__type__` for nested k8s objects.

```yaml
tasks:
  - task_id: hello-world-pod
    operator: airflow.providers.cncf.kubernetes.operators.pod.KubernetesPodOperator
    image: "python:3.12-slim"
    cmds: ["python", "-c"]
    arguments: ["print('hi')"]
    name: example-pod
    namespace: default
    container_resources:
      __type__: kubernetes.client.models.V1ResourceRequirements
      limits: {cpu: "1", memory: "1024Mi"}
      requests: {cpu: "0.5", memory: "512Mi"}
```

---

## Dynamic Task Mapping

Use `expand` and `partial` keys on a task to map dynamically. dag-factory has two distinct ways to reference an upstream task's output:

- **`task_id.output`** — XCom-style reference, used inside `expand` `op_args` / `op_kwargs` (and the equivalent kwargs of other operators).
- **`+task_id`** — bare value reference, used when the value sits directly under `expand` (e.g. `expand: {number: +numbers_list}`) or as a TaskFlow decorator argument.

Don't mix them: `+request` won't resolve inside `op_args`, and `request.output` won't resolve as a bare `expand` value.

```yaml
dynamic_task_map:
  default_args:
    start_date: 2025-01-01
  schedule: "0 3 * * *"
  tasks:
    - task_id: request
      operator: airflow.providers.standard.operators.python.PythonOperator
      python_callable_name: make_list
      python_callable_file: $CONFIG_ROOT_DIR/expand_tasks.py
    - task_id: process
      operator: airflow.providers.standard.operators.python.PythonOperator
      python_callable_name: consume_value
      python_callable_file: $CONFIG_ROOT_DIR/expand_tasks.py
      partial:
        op_kwargs:
          fixed_param: "test"
      expand:
        op_args: request.output    # XCom-style — used inside op_args / op_kwargs
      dependencies: [request]
```

Bare-value form (TaskFlow `decorator` tasks, or any non-`op_args` mapping):

```yaml
tasks:
  - task_id: numbers_list
    decorator: airflow.sdk.definitions.decorators.task
    python_callable: sample.build_numbers_list
  - task_id: double_number
    decorator: airflow.sdk.definitions.decorators.task
    python_callable: sample.double
    expand:
      number: +numbers_list   # + resolves to upstream task `numbers_list`'s XComArg
```

For named map indices (Airflow 2.9+), set `map_index_template: "{{ task.custom_mapping_key }}"` and have the callable assign `context["custom_mapping_key"]`.

**Tested patterns**: simple mapping, task-generated mapping, repeated mapping, `partial`, multiple-parameter mapping, `map_index_template`.
**Unsupported / untested**: mapping over task groups, zipping, transforming expanding data.

---

## Datasets

Use `inlets` / `outlets` on tasks to declare dataset producers, and a list of dataset URIs as `schedule` to consume them.

```yaml
producer_dag:
  default_args:
    start_date: '2024-01-01'
  schedule: "0 5 * * *"
  catchup: false
  tasks:
    - task_id: task_1
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo 1"
      outlets: ['s3://bucket_example/raw/dataset1.json']

consumer_dag:
  default_args:
    start_date: '2024-01-01'
  schedule: ['s3://bucket_example/raw/dataset1.json']
  catchup: false
  tasks:
    - task_id: task_1
      operator: airflow.operators.bash.BashOperator
      bash_command: "echo 'consumer'"
```

### Conditional Dataset Scheduling (Airflow 2.9+ / dag-factory 0.22+)

Nesting the logical operators `__and__` / `__or__` under `datasets` key.

```yaml
schedule:
  datasets:
    __or__:
      - __and__:
          - s3://bucket-cjmm/raw/dataset_custom_1
          - s3://bucket-cjmm/raw/dataset_custom_2
      - s3://bucket-cjmm/raw/dataset_custom_3
```

---

## Callbacks

Three styles, all valid at the DAG, TaskGroup, or Task level (or under `default_args`):

### 1. String pointing to a callable

```yaml
- task_id: task_1
  operator: airflow.operators.bash.BashOperator
  bash_command: "echo task_1"
  on_failure_callback: include.custom_callbacks.output_standard_message
```

With kwargs:

```yaml
- task_id: task_2
  operator: airflow.operators.bash.BashOperator
  bash_command: "echo task_2"
  on_success_callback:
    callback: include.custom_callbacks.output_custom_message
    param1: "Task status"
    param2: "Successful!"
```

### 2. File path + function name (no kwargs)

```yaml
- task_id: task_3
  operator: airflow.operators.bash.BashOperator
  bash_command: "echo task_3"
  on_retry_callback_name: output_standard_message
  on_retry_callback_file: /usr/local/airflow/include/custom_callbacks.py
```

### 3. Provider callbacks

```yaml
- task_id: task_4
  operator: airflow.operators.bash.BashOperator
  bash_command: "echo task_4"
  on_failure_callback:
    callback: airflow.providers.slack.notifications.slack.send_slack_notification
    slack_conn_id: slack_conn_id
    text: ":red_circle: Task Failed."
    channel: "#channel"
```

The provider package must be installed.

---

## Custom Python Objects (`__type__`)

For anything that isn't a simple scalar — `datetime`, `timedelta`, `Asset`, timetables, k8s objects — use the generalized object syntax:

```yaml
start_date:
  __type__: datetime.datetime
  year: 2025
  month: 1
  day: 1

execution_timeout:
  __type__: datetime.timedelta
  hours: 1

schedule:
  __type__: airflow.timetables.trigger.CronTriggerTimetable
  cron: "0 1 * * 3"
  timezone: UTC
```

- `__type__` is the **full import path** to the class
- `__args__` is a list of positional arguments
- Other keys become keyword arguments
- For lists of typed objects, use `__type__: builtins.list` with an `items:` key

### Reserved Keys

Don't use these YAML keys for your own data — dag-factory reserves them: `__type__`, `__args__`, `__join__`, `__and__`, `__or__`. The key `items` is also reserved when used inside a `__type__: builtins.list` block — don't add a custom field named `items` to a typed list construction.

---

## Validation Commands

After installing, the `dagfactory` CLI is on PATH:

| Command | When to Use |
|---------|-------------|
| `dagfactory --version` | Confirm install / version |
| `dagfactory lint <path>` | Validate YAML syntax for a file or directory |
| `dagfactory lint <path> --verbose` | Show a per-file table of results |
| `dagfactory convert <path>` | Show diffs to migrate Airflow 2 → 3 import paths |
| `dagfactory convert <path> --override` | Apply the conversions in place |

### Validation Workflow

```bash
# 1. Lint YAML
dagfactory lint dags/

# 2. Have Airflow parse to catch operator/import errors
#    (Astro CLI users)
astro dev parse
```

`dagfactory lint` only checks YAML syntax — operator import errors and missing kwargs surface at Airflow parse time.

---

## Troubleshooting

### "Operator not found" / `ModuleNotFoundError`

**Cause**: Provider package not installed, or wrong import path.

**Fix**: Install the provider (`pip install apache-airflow-providers-...`) and verify the path. For Airflow 3, run `dagfactory convert` to update legacy `airflow.operators.*` paths to `airflow.providers.standard.operators.*`.

### YAML parses but the DAG doesn't appear in Airflow

**Cause**: Loader file missing or `globals_dict=globals()` not passed.

**Fix**: Ensure a Python file in `dags/` calls `load_yaml_dags(globals_dict=globals(), ...)`. Check `astro dev parse` (or `airflow dags list-import-errors`) for parse errors.

### "Argument is not JSON-serializable" / wrong kwarg type

**Cause**: A scalar string is being passed where a Python object is expected (e.g. `start_date: "2025-01-01"` for a field that needs `datetime`).

**Fix**: Use `__type__: datetime.datetime` (or `datetime.timedelta` etc.) per **Custom Python Objects**.

### Conditional dataset schedule ignored

**Cause**: Airflow <2.9, dag-factory <0.22, or using legacy `!and`/`!or` keys.

**Fix**: Upgrade and rename to `__and__` / `__or__`.

### Multiple `defaults.yml` not merging as expected

**Cause**: `defaults_config_path` not pointing at a parent directory of the DAG YAML.

**Fix**: Set `defaults_config_path` to the highest ancestor folder you want included; dag-factory walks the tree from DAG file → ancestor and merges in that order, with files closer to the DAG winning.

---

## Verification Checklist

Before finishing, verify with the user:

- [ ] `dagfactory lint dags/` passes
- [ ] Loader file exists in `dags/` and calls `load_yaml_dags(globals_dict=globals(), ...)`
- [ ] Required Airflow providers are in `requirements.txt`
- [ ] DAG appears in Airflow UI without import errors

---

## Related Skills

- **authoring-dags** — Writing Airflow DAGs in pure Python with `af` CLI validation. Use when YAML can't express what you need.
- **testing-dags**: For testing DAGs, debugging failures, and the test -> fix -> retest loop
- **debugging-dags**: For troubleshooting failed DAGs

## Reference

- GitHub: https://github.com/astronomer/dag-factory
- Docs: https://astronomer.github.io/dag-factory/latest/
- PyPI: https://pypi.org/project/dag-factory/
- Migration Guide: https://astronomer.github.io/dag-factory/latest/migration_guide/
