# Orbiter Operator Patterns

Reference for mapping source task types to Orbiter operators.

## Table of Contents

- [Shell/Bash Commands](#shellbash-commands)
- [SQL Queries](#sql-queries)
- [Python Callables](#python-callables)
- [SSH Commands](#ssh-commands)
- [WinRM Commands](#winrm-commands-windows-remote)
- [Kubernetes Pods](#kubernetes-pods)
- [Spark (Livy)](#spark-livy)
- [Email Notifications](#email-notifications)
- [Empty/Placeholder Tasks](#emptyplaceholder-tasks)
- [Generic/Custom Operators & Sensors](#genericcustom-operators--sensors-fallback)
- [Creating Custom OrbiterOperator Subclasses](#creating-custom-orbiteroperator-subclasses)
- [Unmapped/Unknown Tasks](#unmappedunknown-tasks)
- [Task Callbacks](#task-callbacks)
- [Task Groups](#task-groups)
- [Schedule Options](#schedule-options)
- [OrbiterOperator Base Fields](#orbiteroperator-base-fields)
- [Resource Mapping Patterns](#resource-mapping-patterns)

---

## Shell/Bash Commands

```python
from orbiter.objects.operators.bash import OrbiterBashOperator

OrbiterBashOperator(
    task_id="run_script",
    bash_command="/path/to/script.sh --arg1 value",
)
```

---

## SQL Queries

```python
from orbiter.objects.operators.sql import OrbiterSQLExecuteQueryOperator
from orbiter.objects import conn_id

OrbiterSQLExecuteQueryOperator(
    task_id="run_query",
    sql="SELECT * FROM table WHERE date = '{{ ds }}'",
    **conn_id("my_database", conn_type="postgres"),
)
```

---

## Python Callables

```python
from orbiter.objects.operators.python import OrbiterPythonOperator

def my_python_function():
    print("Hello from Airflow!")

OrbiterPythonOperator(
    task_id="python_task",
    python_callable=my_python_function,
    op_kwargs={"param": "value"},
)
```

### Python with TaskFlow Decorator (`@task`)

```python
from orbiter.objects.operators.python import OrbiterDecoratedPythonOperator

def my_taskflow_function(param: str):
    print(f"TaskFlow says: {param}")

OrbiterDecoratedPythonOperator(
    task_id="taskflow_task",
    python_callable=my_taskflow_function,
)
# Renders as:
# @task()
# def my_taskflow_function(param: str):
#     print(f"TaskFlow says: {param}")
```

---

## SSH Commands

```python
from orbiter.objects.operators.ssh import OrbiterSSHOperator
from orbiter.objects import conn_id

OrbiterSSHOperator(
    task_id="remote_command",
    command="ls -la /home/user",
    environment={"MY_VAR": "value"},
    **conn_id("ssh_server", prefix="ssh", conn_type="ssh"),
)
```

---

## WinRM Commands (Windows Remote)

```python
from orbiter.objects.operators.win_rm import OrbiterWinRMOperator
from orbiter.objects import conn_id

OrbiterWinRMOperator(
    task_id="windows_command",
    command="Get-Process | Out-File C:\\logs\\processes.txt",
    **conn_id("winrm_server", prefix="ssh", conn_type="ssh"),
)
```

---

## Kubernetes Pods

```python
from orbiter.objects.operators.kubernetes_pod import OrbiterKubernetesPodOperator

OrbiterKubernetesPodOperator(
    task_id="k8s_job",
    image="my-docker-image:latest",
    cmds=["python", "script.py"],
    arguments=["--config", "/etc/config.yaml"],
)
```

> **Note:** Either `image` OR `pod_template_dict` is required.

**With Pod Template:**

```python
OrbiterKubernetesPodOperator(
    task_id="k8s_template_job",
    pod_template_dict={
        "apiVersion": "v1", "kind": "Pod",
        "spec": {"containers": [{"name": "main", "image": "ubuntu", "command": ["echo", "hello"]}]}
    },
)
```

---

## Spark (Livy)

```python
from orbiter.objects.operators.livy import OrbiterLivyOperator
from orbiter.objects import conn_id

OrbiterLivyOperator(
    task_id="spark_job",
    file="/path/to/spark_app.jar",
    **conn_id("livy_cluster", prefix="livy", conn_type="livy"),
)
```

> **Note:** `file` and other Livy-specific parameters are passed through via `model_extra` kwargs.

---

## Email Notifications

```python
from orbiter.objects.operators.smtp import OrbiterEmailOperator

OrbiterEmailOperator(
    task_id="send_alert",
    to="team@company.com",
    subject="Pipeline Complete",
    html_content="<p>Job finished successfully.</p>",
)
```

---

## Empty/Placeholder Tasks

```python
from orbiter.objects.operators.empty import OrbiterEmptyOperator

OrbiterEmptyOperator(
    task_id="start",
    doc_md="Marks the beginning of the workflow",
)
```

---

## Generic/Custom Operators & Sensors (Fallback)

When no specific `OrbiterOperator` exists, use `OrbiterTask`:

```python
from orbiter.objects.task import OrbiterTask
from orbiter.objects.requirement import OrbiterRequirement

# Works with Operators
OrbiterTask(
    task_id="custom_operator_task",
    imports=[
        OrbiterRequirement(
            package="apache-airflow-providers-google",
            module="airflow.providers.google.cloud.operators.bigquery",
            names=["BigQueryInsertJobOperator"],
        )
    ],
    configuration={"query": {"query": "SELECT 1", "useLegacySql": False}},
)

# Also works with Sensors
OrbiterTask(
    task_id="file_sensor_task",
    imports=[
        OrbiterRequirement(
            package="apache-airflow",
            module="airflow.sensors.filesystem",
            names=["FileSensor"],
        )
    ],
    filepath="/data/input.csv",
    poke_interval=60,
)
```

---

## Creating Custom OrbiterOperator Subclasses

For frequently-used operators without a built-in class:

```python
from orbiter.objects.task import OrbiterOperator
from orbiter.objects.requirement import OrbiterRequirement
from orbiter.objects import RenderAttributes

class OrbiterTriggerDagRunOperator(OrbiterOperator):
    """Custom operator for triggering other DAGs"""
    
    imports = [
        OrbiterRequirement(
            package="apache-airflow",
            module="airflow.operators.trigger_dagrun",
            names=["TriggerDagRunOperator"],
        )
    ]
    operator: str = "TriggerDagRunOperator"
    
    render_attributes: RenderAttributes = OrbiterOperator.render_attributes + [
        "trigger_dag_id",
        "wait_for_completion",
    ]
    
    trigger_dag_id: str
    wait_for_completion: bool = False
```

---

## Unmapped/Unknown Tasks

For tasks that cannot be translated, preserve the source:

```python
from orbiter.objects.operators.unmapped import OrbiterUnmappedOperator
import json

OrbiterUnmappedOperator(
    task_id="unknown_task",
    source=json.dumps(val),  # Preserve original for manual review
)
```

---

## Task Callbacks

Operators support callback functions for notifications:

```python
from orbiter.objects.callbacks.smtp import OrbiterSmtpNotifierCallback

OrbiterBashOperator(
    task_id="critical_task",
    bash_command="./critical_script.sh",
    on_failure_callback=OrbiterSmtpNotifierCallback(
        to="oncall@company.com",
        subject="CRITICAL: Task {{ task.task_id }} Failed",
        html_content="<p>Task failed in DAG {{ dag.dag_id }}</p>",
    ),
)
```

**Available callback fields:**
- `on_success_callback`
- `on_failure_callback`
- `on_retry_callback`
- `on_execute_callback`
- `on_skipped_callback`
- `sla_miss_callback` (DAG-level only)

---

## Task Groups

For grouping related tasks visually:

```python
from orbiter.objects.task_group import OrbiterTaskGroup
from orbiter.objects.operators.bash import OrbiterBashOperator

task_group = OrbiterTaskGroup(
    task_group_id="etl_group",
    tooltip="ETL processing tasks",
).add_tasks([
    OrbiterBashOperator(task_id="extract", bash_command="extract.sh"),
    OrbiterBashOperator(task_id="transform", bash_command="transform.sh").add_downstream("load"),
    OrbiterBashOperator(task_id="load", bash_command="load.sh"),
])

# Add task group to DAG
dag.add_tasks(task_group)
task_group.add_downstream("notify")
```

---

## Schedule Options

### Using `timedelta`

```python
from datetime import timedelta

OrbiterDAG(
    dag_id="hourly_dag",
    file_path="hourly_dag.py",
    schedule=timedelta(hours=1),
)
```

### Multiple Schedules (Timetable)

```python
from orbiter.objects.timetables.multiple_cron_trigger_timetable import OrbiterMultipleCronTriggerTimetable

OrbiterDAG(
    dag_id="multi_schedule_dag",
    file_path="multi_schedule_dag.py",
    schedule=OrbiterMultipleCronTriggerTimetable(
        crons=["0 6 * * *", "0 18 * * *"],
        timezone="UTC",
    ),
)
```

---

## OrbiterOperator Base Fields

All operators inherit these fields:

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | `str` | Unique task identifier (auto-cleaned) |
| `doc_md` | `str` | Task documentation |
| `trigger_rule` | `str` | e.g., `"all_success"`, `"one_failed"` |
| `pool` | `str` | Pool name |
| `pool_slots` | `int` | Slots to consume |

---

## Resource Mapping Patterns

Orbiter generates Airflow resources (connections, variables, includes) alongside DAGs.

### Connections

Use `conn_id()` helper to auto-generate connection resources:

```python
from orbiter.objects import conn_id

OrbiterSQLExecuteQueryOperator(
    task_id="query",
    sql="SELECT 1",
    **conn_id("my_postgres", conn_type="postgres"),
)
# Generates: OrbiterConnection(conn_id="my_postgres", conn_type="postgres")
```

### Variables

Attach variables to tasks with `orbiter_vars`:

```python
from orbiter.objects.variable import OrbiterVariable

OrbiterBashOperator(
    task_id="task",
    bash_command="echo $VAR",
    orbiter_vars={OrbiterVariable(key="VAR", value="some_value")},
)
# Generates: Variable in airflow_settings.yaml
```

### Environment Variables

```python
from orbiter.objects.env_var import OrbiterEnvVar

OrbiterBashOperator(
    task_id="task",
    bash_command="echo $SECRET",
    orbiter_env_vars={OrbiterEnvVar(key="SECRET", value="hidden")},
)
```

### Included Files

Bundle auxiliary Python modules with tasks:

```python
from orbiter.objects.include import OrbiterInclude
from orbiter.objects.requirement import OrbiterRequirement

OrbiterPythonOperator(
    task_id="run_util",
    python_callable="my_util_function",
    imports=[OrbiterRequirement(module="include.my_utils", names=["my_util_function"])],
    orbiter_includes={
        OrbiterInclude(
            filepath="include/my_utils.py",
            contents="def my_util_function():\n    return 42",
        ),
    },
)
# Creates: include/my_utils.py in output directory
```

### Pools

```python
from orbiter.objects import pools

OrbiterBashOperator(
    task_id="limited_task",
    bash_command="./resource_heavy.sh",
    **pools("limited_pool", slots=2),
)
# Generates: OrbiterPool(name="limited_pool", slots=2)
```
