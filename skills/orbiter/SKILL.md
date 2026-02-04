---
name: orbiter-translation-dev
description: Use when you need to migrate legacy orchestrator workflows (XML/JSON/YAML) to Apache Airflow DAGs using Orbiter, extend an existing Orbiter translation ruleset, or create a new ruleset. Covers translation rule types, object/operator mapping, and common implementation patterns. Before implementing, verify Python >= 3.10, the source format (XML/JSON/YAML), and that target Airflow version supports the operators you plan to emit.
---

# Orbiter Translation Ruleset Development

Execute steps in order. Prefer minimal, verifiable rules that preserve source context for debugging.

Orbiter is a **CLI and Framework** for converting workflows from legacy orchestration tools to Apache Airflow. This skill covers how to implement translation rulesets that transform source workflow definitions into valid Airflow DAG code.

> **Reference:** [Orbiter Documentation](https://astronomer.github.io/orbiter/)

## Prerequisites

Verify these items before proceeding:

- Confirm the goal: **new ruleset** vs **override an existing community ruleset**
- Identify the **source format** (XML/JSON/YAML) and confirm sample inputs are available
- Confirm **Python >= 3.10** and packages can be installed (`astronomer-orbiter`, optionally `orbiter-community-translations`)
- Confirm the intended **Airflow environment** (version/providers) supports the operators you intend to generate

**Stop conditions:**
- Source format unknown/ambiguous or sample inputs missing → **STOP**
- Python < 3.10 → **STOP**
- Required Airflow providers/operators unavailable → **STOP**

---

## Community Translations

Orbiter has **17+ community-maintained rulesets** for Control-M, Jenkins, SSIS, Oozie, Tidal, AutoSys, and more.

```bash
pip install orbiter-community-translations
orbiter translate --input-dir ./jenkins-exports/ --ruleset orbiter_translations.jenkins.translation_ruleset
```

> **Reference:** Full orchestrator list in `reference/advanced-patterns.md#supported-legacy-orchestrators`

Community rulesets are starting points—extend with custom `@task_rule` or `@dag_rule` for organization-specific patterns.

---

## File Types & Workspace Setup

Orbiter supports JSON, YAML, and XML files. See `reference/advanced-patterns.md#file-types--parsing` for parser details.

### **CRITICAL**: XML Parsing Behavior

Orbiter's XML parser **always returns lists**, even for single elements:

```python
# <workflow><task name="foo"/></workflow> becomes:
{'workflow': [{'task': [{'@name': 'foo'}]}]}  # Always lists!
```

**Always access `[0]`** when working with XML-sourced dictionaries.

### Workspace & Boilerplate

```
.
├── override.py          # Your translation ruleset
└── workflow/            # Source files (.json/.xml/.yaml)
```

```python
# override.py - essential imports
from orbiter.rules import dag_rule, task_rule, task_filter_rule, task_dependency_rule
from orbiter.objects.dag import OrbiterDAG
from orbiter.objects.operators.bash import OrbiterBashOperator
# Full import list: reference/advanced-patterns.md#common-imports
```

> **Reference:** TranslationRuleset structure template in `reference/advanced-patterns.md#translationruleset-structure`

---

## Step 1: Implement DAG Rules (`@dag_rule`)

DAG rules extract top-level workflow metadata and instantiate `OrbiterDAG` objects.

```python
from orbiter.rules import dag_rule
from orbiter.objects.dag import OrbiterDAG
from orbiter import clean_value
from pendulum import DateTime

@dag_rule(priority=1)  # Higher priority rules are evaluated first
def my_dag_rule(val: dict) -> OrbiterDAG | None:
    if "workflow" not in val:
        return None  # Pass to next rule

    workflow = val["workflow"]
    if isinstance(workflow, list):  # XML: always list
        workflow = workflow[0]

    dag_name = workflow.get("@name", "unnamed_dag")
    return OrbiterDAG(
        dag_id=dag_name,
        file_path=f"{clean_value(dag_name)}.py",
        schedule=workflow.get("@schedule"),
        start_date=DateTime(2024, 1, 1),
        catchup=False,
        tags=["migrated", "orbiter"],
    )
```

### Filter Rules (`@dag_filter_rule`, `@task_filter_rule`)

Filter rules select which workflows/tasks to process:

```python
from orbiter.rules import dag_filter_rule, task_filter_rule

@dag_filter_rule(priority=1)
def filter_active_workflows(val: dict) -> list[dict] | None:
    workflow = val.get("workflow", [{}])[0]
    if workflow.get("@status") == "inactive":
        return None  # Skip inactive
    return [val]

@task_filter_rule(priority=1)
def extract_tasks(val: dict) -> list[dict]:
    tasks = val.get("workflow", [{}])[0].get("task", [])
    return tasks if isinstance(tasks, list) else [tasks]
```

> **Reference:** OrbiterDAG fields in `reference/advanced-patterns.md#orbiterdag-fields`

---

## Step 2: Implement Task Rules (`@task_rule`)

Task rules convert individual task definitions into Airflow Operators.

```python
from orbiter.rules import task_rule
from orbiter.objects.operators.bash import OrbiterBashOperator

@task_rule(priority=2)
def shell_task_rule(val: dict) -> OrbiterBashOperator | None:
    if val.get("@type") != "shell":
        return None

    return OrbiterBashOperator(
        task_id=val.get("@name", "unnamed_task"),
        bash_command=val.get("command", "echo 'no command'"),
        doc_md=val.get("description"),
    )
```

### Priority System

Rules are evaluated in **descending priority order**. First non-`None` return wins.

> **Reference:** See `reference/operator-patterns.md` for the complete operator cheatsheet.

---

## Step 3: Implement Task Dependencies (`@task_dependency_rule`)

Dependency rules define execution order (`>>`) between tasks.

```python
from orbiter.rules import task_dependency_rule
from orbiter.objects.dag import OrbiterDAG
from orbiter.objects.task import OrbiterTaskDependency
from typing import List

@task_dependency_rule
def extract_dependencies(val: OrbiterDAG) -> List[OrbiterTaskDependency] | None:
    dependencies = []
    for task_id, task in val.tasks.items():
        original = (task.orbiter_kwargs or {}).get("val", {})
        downstream = original.get("ok_to") or original.get("downstream")
        
        if downstream:
            dependencies.append(OrbiterTaskDependency(
                task_id=task_id,
                downstream=downstream,  # Can be str or List[str]
            ))
    
    return dependencies if dependencies else None
```

---

## Step 4: Resource Mapping

Orbiter auto-generates connections, variables, and includes alongside DAGs:

```python
from orbiter.objects import conn_id
from orbiter.objects.variable import OrbiterVariable

# Connections: use conn_id() helper
OrbiterSQLExecuteQueryOperator(
    task_id="query", sql="SELECT 1",
    **conn_id("my_postgres", conn_type="postgres"),
)

# Variables: attach with orbiter_vars
OrbiterBashOperator(
    task_id="task", bash_command="echo $VAR",
    orbiter_vars={OrbiterVariable(key="VAR", value="some_value")},
)
```

> **Reference:** Full patterns (includes, pools, env vars) in `reference/operator-patterns.md#resource-mapping-patterns`

---

## Step 5: Post-Processing (`@post_processing_rule`)

Post-processing rules run after all DAGs/tasks are created.

```python
from orbiter.rules import post_processing_rule
from orbiter.objects.project import OrbiterProject

@post_processing_rule
def add_global_tags(val: OrbiterProject) -> None:
    for dag in val.dags.values():
        if dag.tags is None:
            dag.tags = []
        dag.tags.append("auto-migrated")
```

---

## Critical Gotchas

1. **XML Always Returns Lists** — Use `val["workflow"][0]["task"][0]`, not `val["workflow"]["task"]`
2. **Task IDs Auto-Cleaned** — `clean_value()` converts `"My Task"` → `"my_task"`, prefixes numbers: `"01-first"` → `"n01_first"`
3. **Task ID Suffix** — Orbiter appends `_task` by default. Override: `ORBITER_TASK_SUFFIX=""`
4. **Imports Required** — Every operator must have valid `imports` or raises `AssertionError`
5. **Return Object or None** — Rules must return the Orbiter object or `None` to pass to next rule
6. **File Path vs DAG ID** — `dag_id` = UI display; `file_path` = physical file in `dags/`

---

## Step 6: Final Validation

```bash
# Run translation (add LOG_LEVEL=DEBUG for verbose output)
orbiter translate --input-dir workflow/ --ruleset override.translation_ruleset

# Verify output
python -m py_compile output/dags/*.py && airflow dags list --subdir output/dags/
```

> **Reference:** Debugging, introspection, and `project.analyze()` in `reference/advanced-patterns.md`

---

## Related Skills

- **authoring-dags** - DAG authoring best practices for generated code
- **migrating-airflow-2-to-3** - If target environment is Airflow 3.x
- **testing-dags** - Validating generated DAGs
