# Orbiter Advanced Patterns

Debugging, introspection, reusable patterns, and configuration.

## Table of Contents

- [Debugging & Introspection](#debugging--introspection)
- [Reusable Patterns](#reusable-patterns)
- [Translation Configuration](#translation-configuration)
- [File Types & Parsing](#file-types--parsing)
- [TranslationRuleset Structure](#translationruleset-structure)
- [Supported Legacy Orchestrators](#supported-legacy-orchestrators)
- [Quick Reference](#quick-reference)
- [Community Resources](#community-resources)

---

## Debugging & Introspection

### OrbiterMeta: Rule Matching Insights

Every translated object stores metadata about which rule created it:

```python
task = dag.tasks["my_task"]

# See which rule matched
task.orbiter_meta.matched_rule_name      # "shell_task_rule"
task.orbiter_meta.matched_rule_priority  # 2
task.orbiter_meta.matched_rule_source    # Full source code of the rule

# See which keys the rule accessed
task.orbiter_meta.visited_keys           # ["@name", "command", "ok_to"]

# Access the original input
task.orbiter_kwargs                      # {"val": {"@name": "...", ...}}
```

### OrbiterProject.analyze(): Migration Coverage Report

Generate a summary to identify unmapped tasks:

```python
project = translation_ruleset.translate_fn(translation_ruleset, input_dir)

# Print markdown analysis
project.analyze(output_fmt="md")

# Export to JSON/CSV
with open("migration_report.json", "w") as f:
    project.analyze(output_fmt="json", output_file=f)
```

Output shows task counts per file:

```
           DAGs   OrbiterBashOperator   OrbiterUnmappedOperator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 workflow.xml     5                   3                       2
    Totals        5                   3                       2
```

### TranslationRuleset.test(): Unit Testing

Test rulesets without writing files to disk:

```python
from my_translation import translation_ruleset

# Test with a dict
result = translation_ruleset.test({"workflow": [{"@name": "test_dag"}]})
assert "test_dag" in result.dags

# Test with raw string input
xml_input = '<workflow name="demo"><task name="t1"/></workflow>'
result = translation_ruleset.test(xml_input)
assert len(result.dags["demo"].tasks) == 1
```

---

## Reusable Patterns

Use the `@pattern` decorator for composable logic:

```python
from orbiter.rules import pattern, task_rule
from orbiter.objects.operators.bash import OrbiterBashOperator

@pattern(params_doc={"command": "BashOperator.bash_command", "script": "BashOperator.bash_command"})
def command_pattern(val: dict) -> dict:
    """Extracts bash_command from 'command' or 'script' keys"""
    if cmd := val.get("command") or val.get("script"):
        return {"bash_command": cmd}
    return {}

@task_rule(priority=5, params_doc={"id": "*.task_id"} | command_pattern.params_doc)
def shell_task_rule(val: dict) -> OrbiterBashOperator | None:
    if result := command_pattern(val):
        return OrbiterBashOperator(
            task_id=val.get("id", "unknown"),
            **result,
        )
    return None
```

**Benefits:**
- Patterns are self-documenting via `params_doc`
- Logic is testable in isolation
- Rules stay concise

---

## Translation Configuration

Control parallel processing for large migrations:

```python
from orbiter.rules.rulesets import TranslationRuleset, TranslationConfig

translation_ruleset = TranslationRuleset(
    config=TranslationConfig(
        parallel=True,   # Run filter rulesets in parallel
        upfront=True,    # Filter all files before extracting any DAGs
    ),
    file_type={FileTypeXML},
    dag_filter_ruleset=...,
)
```

**When to use:**
- `parallel=True`: Large input directories with many files
- `upfront=True`: When filter rules need to see all files before DAG extraction

---

## File Types & Parsing

### Supported File Types

| FileType | Extensions | Parser | Notes |
|----------|------------|--------|-------|
| `FileTypeJSON` | `.json` | `json.loads` | Standard JSON parsing |
| `FileTypeYAML` | `.yaml`, `.yml` | `yaml.full_load_all` | Returns `dict` for single-doc, `list[dict]` for multi-doc |
| `FileTypeXML` | `.xml` | `xmltodict_parse` | **Always returns lists for elements** (see below) |

### XML Parsing Behavior

Orbiter's XML parser **always returns lists** for XML elements, even when there's only one child:

```python
# Source XML:
# <workflow><task name="foo"/></workflow>

# Parsed result:
{'workflow': [{'task': [{'@name': 'foo'}]}]}
#             ^        ^
#             |        └── Always a list, even with one <task>
#             └── Always a list, even with one <workflow>
```

**Always iterate or access `[0]`** when working with XML-sourced dictionaries.

---

## TranslationRuleset Structure

Complete template for building a translation ruleset:

```python
from orbiter.rules.rulesets import (
    TranslationRuleset, DAGFilterRuleset, DAGRuleset,
    TaskFilterRuleset, TaskRuleset, TaskDependencyRuleset, PostProcessingRuleset,
)
from orbiter.file_types import FileTypeXML

translation_ruleset = TranslationRuleset(
    file_type={FileTypeXML},  # Must be a Set
    dag_filter_ruleset=DAGFilterRuleset(ruleset=[...]),
    dag_ruleset=DAGRuleset(ruleset=[...]),
    task_filter_ruleset=TaskFilterRuleset(ruleset=[...]),
    task_ruleset=TaskRuleset(ruleset=[...]),
    task_dependency_ruleset=TaskDependencyRuleset(ruleset=[...]),
    post_processing_ruleset=PostProcessingRuleset(ruleset=[...]),
)
```

### OrbiterDAG Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dag_id` | `str` | Yes | Unique identifier, auto-cleaned to snake_case |
| `file_path` | `str` | Yes | Output filename relative to `dags/` folder |
| `schedule` | `str \| timedelta \| OrbiterTimetable` | No | Cron string, timedelta, or timetable |
| `start_date` | `DateTime` | No | DAG start date |
| `catchup` | `bool` | No | Whether to backfill |
| `tags` | `List[str]` | No | UI tags |
| `default_args` | `Dict` | No | Default task arguments |

---

## Supported Legacy Orchestrators

Community-maintained translation rulesets (from [orbiter-community-translations](https://github.com/astronomer/orbiter-community-translations)):

| Orchestrator | Format | Ruleset Import |
|--------------|--------|----------------|
| **Argo Workflows** | YAML | `orbiter_translations.argo` |
| **Automic (UC4)** | XML | `orbiter_translations.automic` |
| **AutoSys** | JIL | `orbiter_translations.autosys` |
| **Control-M** | XML | `orbiter_translations.control_m` |
| **Cron/Crontab** | TXT | `orbiter_translations.cron` |
| **DAG Factory** | YAML | `orbiter_translations.dag_factory` |
| **IBM DataStage** | XML | `orbiter_translations.data_stage` |
| **ESP Workload Automation** | TXT | `orbiter_translations.esp` |
| **IWA** | TXT | `orbiter_translations.iwa` |
| **JAMS Scheduler** | XML | `orbiter_translations.jams` |
| **Jenkins** | JSON | `orbiter_translations.jenkins` |
| **Kestra** | YAML | `orbiter_translations.kestra` |
| **Luigi** | Python | `orbiter_translations.luigi` |
| **Matillion** | YAML | `orbiter_translations.matillion` |
| **Apache Oozie** | XML | `orbiter_translations.oozie` |
| **SQL Server SSIS** | XML | `orbiter_translations.ssis` |
| **Talend** | JSON | `orbiter_translations.talend` |
| **Tidal Workload Automation** | XML | `orbiter_translations.tidal` |

---

## Quick Reference

### Rule Types

| Decorator | Input | Output | Purpose |
|-----------|-------|--------|---------|
| `@dag_filter_rule` | `dict` | `list[dict] \| None` | Filter/select source workflows |
| `@dag_rule` | `dict` | `OrbiterDAG \| None` | Create DAG from workflow |
| `@task_filter_rule` | `dict` | `list[dict]` | Extract task nodes |
| `@task_rule` | `dict` | `OrbiterOperator \| OrbiterTaskGroup \| None` | Create task from node |
| `@task_dependency_rule` | `OrbiterDAG` | `list[OrbiterTaskDependency] \| None` | Define dependencies |
| `@post_processing_rule` | `OrbiterProject` | `None` | Final modifications |

> **Note:** All rules support `priority` parameter. Higher priority = evaluated first.

### Common Imports

```python
# Rules
from orbiter.rules import (
    dag_rule, dag_filter_rule, task_rule, task_filter_rule,
    task_dependency_rule, post_processing_rule, pattern,
)

# Core Objects
from orbiter.objects.dag import OrbiterDAG
from orbiter.objects.task import OrbiterTask, OrbiterTaskDependency
from orbiter.objects.task_group import OrbiterTaskGroup
from orbiter.objects.requirement import OrbiterRequirement
from orbiter.objects.project import OrbiterProject

# Operators
from orbiter.objects.operators.bash import OrbiterBashOperator
from orbiter.objects.operators.python import OrbiterPythonOperator, OrbiterDecoratedPythonOperator
from orbiter.objects.operators.sql import OrbiterSQLExecuteQueryOperator
from orbiter.objects.operators.ssh import OrbiterSSHOperator
from orbiter.objects.operators.win_rm import OrbiterWinRMOperator
from orbiter.objects.operators.kubernetes_pod import OrbiterKubernetesPodOperator
from orbiter.objects.operators.smtp import OrbiterEmailOperator
from orbiter.objects.operators.livy import OrbiterLivyOperator
from orbiter.objects.operators.empty import OrbiterEmptyOperator
from orbiter.objects.operators.unmapped import OrbiterUnmappedOperator

# Resources
from orbiter.objects.connection import OrbiterConnection
from orbiter.objects.variable import OrbiterVariable
from orbiter.objects.env_var import OrbiterEnvVar
from orbiter.objects.include import OrbiterInclude
from orbiter.objects.pool import OrbiterPool

# Callbacks
from orbiter.objects.callbacks import OrbiterCallback
from orbiter.objects.callbacks.smtp import OrbiterSmtpNotifierCallback

# Rulesets
from orbiter.rules.rulesets import (
    TranslationRuleset, DAGFilterRuleset, DAGRuleset,
    TaskFilterRuleset, TaskRuleset, TaskDependencyRuleset, PostProcessingRuleset,
)
from orbiter.file_types import FileTypeJSON, FileTypeXML, FileTypeYAML

# Helpers
from orbiter.objects import conn_id, pools
from orbiter import clean_value
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `orbiter translate --input-dir <dir>` | Translate workflows to Airflow project |
| `orbiter analyze --input-dir <dir>` | Output migration report (JSON/CSV/MD) |
| `orbiter install <ruleset>` | Install a translation ruleset |
| `orbiter list-rulesets` | List available community rulesets |
| `orbiter document -r <ruleset>` | Generate HTML documentation |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `ORBITER_TASK_SUFFIX` | `_task` | Suffix for task variable names |
| `ORBITER_TRANSLATION_VERSION` | `latest` | Ruleset version to download |
| `TRIM_LOG_OBJECT_LENGTH` | `1000` | Max chars for logged objects |

---

## Community Resources

### Community Translations Repository

**GitHub:** [github.com/astronomer/orbiter-community-translations](https://github.com/astronomer/orbiter-community-translations)

Contains translation rulesets for 17+ legacy orchestrators:
- **CI/CD:** Jenkins
- **Enterprise Schedulers:** Control-M, Tidal, AutoSys, Automic, JAMS, ESP
- **ETL/ELT:** SSIS, DataStage, Talend, Matillion
- **Workflow Engines:** Oozie, Argo, Kestra, Luigi, DAG Factory
- **System Schedulers:** Cron

### Other Resources

- **Astronomer Registry:** [registry.astronomer.io](https://registry.astronomer.io/)
- **Orbiter Documentation:** [astronomer.github.io/orbiter](https://astronomer.github.io/orbiter/)
- **Orbiter Core:** [github.com/astronomer/orbiter](https://github.com/astronomer/orbiter)
