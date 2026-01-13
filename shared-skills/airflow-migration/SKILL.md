---
name: airflow-2-to-3-migration
description: Guide for migrating Apache Airflow 2.x projects to Airflow 3.x. Use when the user mentions Airflow 3 migration, upgrade, compatibility issues, breaking changes, or wants to modernize their Airflow codebase. If you detect Airflow 2.x code that needs migration, prompt the user and ask if they want you to help upgrade. Always load this skill as the first step for any migration-related request.
---

# Airflow 2 to 3 Migration Skill

This skill helps migrate **Airflow 2.x DAG code** to **Airflow 3.x**, focusing on code changes (imports, operators, hooks, context, API usage).

**Important**: Before migrating to Airflow 3, strongly recommend upgrading to Airflow 2.11 first, then to at least Airflow 3.0.11 (ideally directly to 3.1). Other upgrade paths would make rollbacks impossible. See: https://www.astronomer.io/docs/astro/airflow3/upgrade-af3#upgrade-your-airflow-2-deployment-to-airflow-3. Additionally, early 3.0 versions have many bugs—3.1 provides a much better experience.

## Migration at a Glance

1. Run Ruff's Airflow migration rules to auto-fix detectable issues (AIR30/AIR301/AIR302/AIR31/AIR311/AIR312).
   - `ruff check --preview --select AIR --fix --unsafe-fixes .`
2. Scan for remaining issues using the manual search checklist in **section 9**.
   - Focus on: direct metadata DB access, legacy imports, scheduling/context keys, XCom pickling, datasets→assets, REST API/auth, plugins, and file paths to files in the `dags` and/or `include` folder that might have changed due to the automatically configured AstroDagBundle.
3. Plan changes per file and issue type:
   - Fix imports → update operators/hooks/providers → refactor metadata access to using the Airflow client instead of direct access → fix use of outdated context variables -> fix scheduling logic.
4. Implement changes incrementally, re-running Ruff and code searches after each major change.
5. Explain changes to the user and caution them to test any updated logic such as refactored metadata, scheduling logic and use of the Airflow context.

## Code Migration Guidance

### 1. Architecture & Metadata DB Access (Code Impact)

Airflow 3 changes how components talk to the metadata database:

- Workers no longer connect directly to the metadata DB.
- Task code runs via the **Task Execution API** exposed by the **API server**.
- The **DAG processor** runs as an independent process **separate from the scheduler** and uses an **in‑process API server** to access the metadata DB when code in DAG files requires it.
- The **Triggerer** uses the task execution mechanism via an **in‑process API server** to execute user code (for example when requiring variables or connections).

**Key code impact**:
Task code can still import ORM sessions/models, but **any attempt to use them to talk to the metadata DB will fail** with:

```text
RuntimeError: Direct database access via the ORM is not allowed in Airflow 3.x
```

#### 1.1 Direct metadata DB access patterns to search for

When scanning DAGs, custom operators, and `@task` functions, look for:

- Session helpers:
  - `from airflow.utils.session import provide_session`
  - `from airflow.utils.session import create_session`
  - `@provide_session`
  - `with create_session() as session: ...`
- Sessions from settings:
  - `from airflow.settings import Session`
  - `with Session() as session: ...`
- Engine access:
  - `from airflow.settings import engine`
  - `with engine.connect() as connection: ...`
  - `Session(bind=engine)`
- ORM usage with models:
  - `from airflow.models import DagModel, DagRun, TaskInstance, ...`
  - `session.query(DagModel)...`, `session.query(DagRun)...`, etc.
- Any use of the SQLAlchemy `Session` with the Airflow engine:
  - `from sqlalchemy.orm.session import Session`
  - `Session(bind=engine)`

All of these patterns must be refactored.

#### 1.2 Replacement pattern: Airflow Python client (`apache-airflow-client`)

Preferred for rich metadata access patterns:

1. Add an Airflow client whose version matches the project's Airflow runtime (for example, in `requirements.txt`):

```text
apache-airflow-client==<your-airflow-runtime-version>
```

2. In task code (custom operator or `@task`), use the client instead of ORM sessions:

```python
import os
from airflow.sdk import BaseOperator

_HOST = os.getenv(
    "AIRFLOW__API__BASE_URL",
    "https://<your-org-id>.astronomer.run/<short-deployment-id>/",
)  # see: https://www.astronomer.io/docs/astro/airflow-api
_DEPLOYMENT_API_TOKEN = os.getenv("DEPLOYMENT_API_TOKEN")


class ListDagsWithClientOperator(BaseOperator):
    def execute(self, context):
        import airflow_client.client
        from airflow_client.client.api.dag_api import DAGApi

        configuration = airflow_client.client.Configuration(
            host=_HOST,
            access_token=_DEPLOYMENT_API_TOKEN,
        )

        with airflow_client.client.ApiClient(configuration) as api_client:
            dag_api = DAGApi(api_client)
            dags = dag_api.get_dags(limit=10)
            self.log.info("Found %d DAGs", len(dags.dags))
```

#### 1.3 Replacement pattern: direct REST API calls (`requests`)

For simple cases, call the REST API directly using `requests`:

```python
from airflow.sdk import task
import os
import requests

_HOST = os.getenv(
    "AIRFLOW__API__BASE_URL",
    "https://<your-org-id>.astronomer.run/<short-deployment-id>/",
)  # see: https://www.astronomer.io/docs/astro/airflow-api
_DEPLOYMENT_API_TOKEN = os.getenv("DEPLOYMENT_API_TOKEN")


@task
def list_dags_via_api() -> None:
    dags_url = f"{_HOST}/api/v2/dags"
    auth_headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {_DEPLOYMENT_API_TOKEN}",
    }
    dags_response = requests.get(dags_url, headers=auth_headers, params={"limit": 10})
    dags_response.raise_for_status()
    dags_data = dags_response.json()
    print(dags_data)
```

**Do not** attempt to bypass the restriction by using the ORM or `engine` from task code.

---

### 2. Ruff Airflow Migration Rules (Code Linting)

Use Ruff's Airflow rules to detect and fix many breaking changes automatically.

- **AIR30 / AIR301 / AIR302**: Removed code and imports in Airflow 3 – **must be fixed**.
- **AIR31 / AIR311 / AIR312**: Deprecated code and imports – still work but will be removed in future versions; **should be fixed**.

Commands to run (via `uv`) against the project root:

```bash
# Auto-fix all detectable Airflow issues (safe + unsafe)
ruff check --preview --select AIR --fix --unsafe-fixes .

# Check remaining Airflow issues without fixing
ruff check --preview --select AIR .
```

---

### 3. Removed Modules & Import Reorganizations

#### 3.1 `airflow.contrib.*` removed

The entire `airflow.contrib.*` namespace is removed in Airflow 3.

**Before (Airflow 2.x, removed in Airflow 3):**

```python
from airflow.contrib.operators.dummy_operator import DummyOperator
```

**After (Airflow 3):**

```python
from airflow.providers.standard.operators.empty import EmptyOperator
```

Use `EmptyOperator` instead of the removed `DummyOperator`.

#### 3.2 Core operators moved to provider packages

Many commonly used core operators moved to the **standard provider**.

Example for `BashOperator` and `PythonOperator`:

```python
# Airflow 2 legacy imports (removed in Airflow 3, AIR30/AIR301)
from airflow.operators.bash_operator import BashOperator
from airflow.operators.python_operator import PythonOperator

# Airflow 2/3 deprecated imports (still work but deprecated, AIR31/AIR311)
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Recommended in Airflow 3: Standard provider
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
```

Operators moved to the `apache-airflow-providers-standard` package include (non‑exhaustive):

- `BashOperator`
- `BranchDateTimeOperator`
- `BranchDayOfWeekOperator`
- `LatestOnlyOperator`
- `PythonOperator`
- `PythonVirtualenvOperator`
- `ExternalPythonOperator`
- `BranchPythonOperator`
- `BranchPythonVirtualenvOperator`
- `BranchExternalPythonOperator`
- `ShortCircuitOperator`
- `TriggerDagRunOperator`

This provider is installed on Astro Runtime by default.

#### 3.3 Hook and sensor imports moved to providers

Most hooks and sensors live in provider packages in Airflow 3. Look for very old imports:

```python
from airflow.hooks.http_hook import HttpHook
from airflow.hooks.base_hook import BaseHook
```

Replace with provider imports:

```python
from airflow.providers.http.hooks.http import HttpHook
from airflow.sdk import BaseHook  # base hook from task SDK where appropriate
```

#### 3.4 `EmailOperator` moved to SMTP provider

In Airflow 3, `EmailOperator` is provided by the **SMTP provider**, not the standard provider.

```python
from airflow.providers.smtp.operators.smtp import EmailOperator

EmailOperator(
    task_id="send_email",
    conn_id="smtp_default",
    to="receiver@example.com",
    subject="Test Email",
    html_content="This is a test email",
)
```

Ensure `apache-airflow-providers-smtp` is added to any project that uses email features or notifications so that email‑related code is compatible with Airflow 3.2 and later.

---

### 4. Task SDK & Param Usage

In Airflow 3, most classes and decorators used by DAG authors are available via the **Task SDK** (`airflow.sdk`). Using these imports makes it easier to evolve your code with future Airflow versions.

#### 4.1 Key Task SDK imports

Prefer these imports in new code:

```python
from airflow.sdk import (
    dag,
    task,
    setup,
    teardown,
    DAG,
    TaskGroup,
    BaseOperator,
    BaseSensorOperator,
    Param,
    ParamsDict,
    Variable,
    Connection,
    Context,
    Asset,
    AssetAlias,
    AssetAll,
    AssetAny,
    DagRunState,
    TaskInstanceState,
    TriggerRule,
    WeightRule,
    BaseHook,
    BaseNotifier,
    XComArg,
    chain,
    chain_linear,
    cross_downstream,
    get_current_context,
)
```

Some common mappings from legacy imports:

- `airflow.decorators.dag` → `airflow.sdk.dag`
- `airflow.decorators.task` → `airflow.sdk.task`
- `airflow.utils.task_group.TaskGroup` → `airflow.sdk.TaskGroup`
- `airflow.models.dag.DAG` → `airflow.sdk.DAG`
- `airflow.models.baseoperator.BaseOperator` → `airflow.sdk.BaseOperator`
- `airflow.models.param.Param` → `airflow.sdk.Param`
- `airflow.datasets.Dataset` → `airflow.sdk.Asset`
- `airflow.datasets.DatasetAlias` → `airflow.sdk.AssetAlias`

---

### 5. SubDAGs, SLAs, and Other Removed Code Features

#### 5.1 SubDAGs removed

Search for:

- `SubDagOperator(`
- `from airflow.operators.subdag_operator import SubDagOperator`
- `from airflow.operators.subdag import SubDagOperator`

Migration guidance:

- Use `TaskGroup` or `@task_group` for logical grouping **within a single DAG**.
- For workflows that were previously split via SubDAGs, consider:
  - Refactoring into **smaller DAGs**.
  - Using **Assets** (formerly Datasets) for cross‑DAG dependencies.

#### 5.2 SLAs removed

Search for:

- `sla=`
- `sla_miss_callback`
- `SLAMiss`

Code changes:

- Remove SLA‑related parameters from tasks and DAGs.
- Remove SLA‑based callbacks from DAG definitions.
- On **Astro**, use **Astro Alerts** for DAG/task-level SLAs.

#### 5.3 Other removed or renamed code features

- `DagParam` removed → use `Param` from `airflow.sdk`.
- `SimpleHttpOperator` removed → use `HttpOperator` from the HTTP provider.
- Trigger rules:
  - `dummy` → use `TriggerRule.ALWAYS`.
  - `none_failed_or_skipped` → use `TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS`.
- `.xcom_pull` behavior:
  - In Airflow 3, calling `xcom_pull(key="...")` **without** `task_ids` always returns `None`; always specify `task_ids` explicitly.
- `fail_stop` DAG parameter renamed to `fail_fast`.
- `max_active_tasks` now limits **active task instances per DAG run** instead of across all DAG runs.

---

### 6. Scheduling & Context Changes (Code Logic)

#### 6.1 Default scheduling behavior

Airflow 3 changes default DAG scheduling:

- `schedule=None` instead of `timedelta(days=1)`.
- `catchup=False` instead of `True`.

Code impact:

- If a DAG relied on implicit daily scheduling, explicitly set `schedule`.
- If a DAG relied on catchup by default, explicitly set `catchup=True`.

#### 6.2 Removed context keys and replacements

Removed or changed keys and suggested replacements:

| Removed Key | Replacement |
|-------------|-------------|
| `execution_date` | `context["dag_run"].logical_date` |
| `tomorrow_ds` / `yesterday_ds` | Use `data_interval_start` and `data_interval_end` |
| `prev_ds` / `next_ds` | Use `prev_start_date_success` or timetable API |
| `triggering_dataset_events` | `triggering_asset_events` with Asset objects |
| `conf` | Use `Variable` or `Connection` |

Note: These replacements are **not always drop‑in**; logic changes may be required.

#### 6.3 `days_ago` removed

The helper `days_ago` from `airflow.utils.dates` was removed. Replace with explicit datetimes:

```python
# WRONG - Removed in Airflow 3
from airflow.utils.dates import days_ago
start_date=days_ago(2)

# CORRECT - Use pendulum
import pendulum
start_date=pendulum.today("UTC").add(days=-2)
```

---

### 7. XCom Pickling Removal

In Airflow 3:

- `AIRFLOW__CORE__ENABLE_XCOM_PICKLING` is removed.
- The default XCom backend supports JSON‑serializable types, pandas DataFrames, Delta Lake tables, and Apache Iceberg tables.

If tasks need to pass complex objects (e.g. NumPy arrays), you must use a **custom XCom backend**.

---

### 8. Datasets → Assets

Datasets were renamed to Assets in Airflow 3; the old APIs are deprecated.

Mappings:

- `airflow.datasets.Dataset` → `airflow.sdk.Asset`
- `airflow.datasets.DatasetAlias` → `airflow.sdk.AssetAlias`
- `airflow.datasets.DatasetAll` → `airflow.sdk.AssetAll`
- `airflow.datasets.DatasetAny` → `airflow.sdk.AssetAny`

When working with asset events in the task context, **do not use plain strings as keys** in `outlet_events` or `inlet_events`:

```python
# WRONG
outlet_events["myasset"]

# CORRECT
from airflow.sdk import Asset
outlet_events[Asset(name="myasset")]
```

---

### 9. Code Migration Checklist

After running Ruff's AIR rules, use this manual search checklist:

1. **Direct metadata DB access**
   - Search for: `provide_session`, `create_session`, `Session(`, `engine`
   - Fix: Refactor to use Airflow Python client or REST API

2. **Legacy imports**
   - Search for: `from airflow.contrib`, `from airflow.operators.`, `from airflow.hooks.`
   - Fix: Map to provider imports

3. **Removed DAG arguments**
   - Search for: `schedule_interval=`, `timetable=`, `days_ago(`, `fail_stop=`
   - Fix: Use `schedule=` and `pendulum`

4. **Deprecated context keys**
   - Search for: `execution_date`, `prev_ds`, `next_ds`, `yesterday_ds`, `tomorrow_ds`
   - Fix: Use `data_interval_start/end` and `dag_run.logical_date`

5. **XCom pickling**
   - Search for: `ENABLE_XCOM_PICKLING`, `.xcom_pull(` without `task_ids=`
   - Fix: Use JSON-serializable data or custom backend

6. **Datasets → Assets**
   - Search for: `airflow.datasets`, `triggering_dataset_events`
   - Fix: Switch to `airflow.sdk.Asset`

7. **Removed operators**
   - Search for: `SubDagOperator`, `SimpleHttpOperator`, `DagParam`, `DummyOperator`
   - Fix: Use TaskGroups, HttpOperator, Param, EmptyOperator

8. **Email changes**
   - Search for: `airflow.operators.email.EmailOperator`
   - Fix: Use SMTP provider

9. **REST API v1**
   - Search for: `/api/v1`
   - Fix: Update to `/api/v2` with Bearer tokens

10. **File paths**
    - Search for: `open("include/...)`, relative paths
    - Fix: Use `__file__` or `AIRFLOW_HOME` anchoring

---

### 10. DAG Bundles & File Paths

On Astro Runtime, Airflow 3 uses a versioned DAG bundle, so file paths behave differently:

**For files inside `dags/` folder:**
```python
import os
dag_dir = os.path.dirname(__file__)
with open(os.path.join(dag_dir, "my_file.txt"), "r") as f:
    contents = f.read()
```

**For files in `include/` or other mounted folders:**
```python
import os
with open(f"{os.getenv('AIRFLOW_HOME')}/include/my_file.txt", 'r') as f:
    contents = f.read()
```

---

## Resources

- [Astronomer Airflow 3 Upgrade Guide](https://www.astronomer.io/docs/astro/airflow3/upgrade-af3)
- [Airflow 3 Release Notes](https://airflow.apache.org/docs/apache-airflow/stable/release_notes.html)
- [Ruff Airflow Rules](https://docs.astral.sh/ruff/rules/#airflow-air)
