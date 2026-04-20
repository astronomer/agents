---
name: airflow-hitl
description: Use when the user needs human-in-the-loop workflows in Airflow (approval/reject, form input, or human-driven branching). Covers ApprovalOperator, HITLOperator, HITLBranchOperator, HITLEntryOperator, HITLTrigger. Requires Airflow 3.1+. Does not cover AI/LLM calls (see airflow-ai).
---

# Airflow Human-in-the-Loop Operators

Pause a DAG until a human responds via the Airflow UI or REST API. HITL operators are deferrable — they release their worker slot while waiting.

> **Requires Airflow 3.1+** (`uvx --from astro-airflow-mcp af config version`).
>
> **UI location**: Browse → Required Actions. Respond from the task instance page's Required Actions tab.
>
> **Cross-references**: `airflow-ai` for AI/LLM task decorators; `airflow` for registry and API discovery commands used below.

---

## Step 1 — Pick the capability you need

| Capability | Class (verify in Step 2) |
|---|---|
| Approve or reject; downstream skips on reject | `ApprovalOperator` |
| Present N options and return which were chosen | `HITLOperator` |
| Branch to one or more downstream tasks based on a choice | `HITLBranchOperator` |
| Collect a form (no approve/select step) | `HITLEntryOperator` |
| Use the HITL trigger directly (advanced / custom operators) | `HITLTrigger` |

This is the only place class names are hardcoded. The provider adds, renames, and removes params across releases — do not copy parameter lists from memory. Fetch the current signature before writing code.

---

## Step 2 — Discover the current signatures from the Airflow Registry

Before writing HITL code, run these to see the live roster and constructor params (see the `airflow` skill for the full `af registry` reference):

```bash
# Every HITL-related module in the standard provider
uvx --from astro-airflow-mcp af registry modules standard \
  | jq '.modules[] | select(.import_path | test("\\.hitl\\.")) | {name, type, import_path, short_description, docs_url}'

# Constructor signatures: name, type, default, required, description
uvx --from astro-airflow-mcp af registry parameters standard \
  | jq '.classes | to_entries[] | select(.key | test("\\.hitl\\.")) | {fqn: .key, parameters: .value.parameters}'

# Pin to the exact installed provider version
uvx --from astro-airflow-mcp af config providers \
  | jq '.providers[] | select(.package_name == "apache-airflow-providers-standard") | .version'
# then: af registry parameters standard --version <VERSION>
```

If the registry shows a param that this skill does not mention, prefer the registry. If the registry shows a class that is not in Step 1, treat it as additive — the decision table above may be stale.

---

## Step 3 — Canonical example (approval gate)

Starting point for any HITL task. Adapt by swapping the class name and params per Step 2.

```python
from airflow.providers.standard.operators.hitl import ApprovalOperator
from airflow.sdk import dag, task, chain, Param
from pendulum import datetime

@dag(start_date=datetime(2025, 1, 1), schedule="@daily")
def approval_example():
    @task
    def prepare():
        return "Review quarterly report"

    approval = ApprovalOperator(
        task_id="approve_report",
        subject="Report Approval",
        body="{{ ti.xcom_pull(task_ids='prepare') }}",
        defaults="Approve",              # Auto-selected on timeout
        params={"comments": Param("", type="string")},
    )

    @task
    def after_approval(result):
        print(f"Decision: {result['chosen_options']}")

    chain(prepare(), approval)
    after_approval(approval.output)

approval_example()
```

For the other classes in Step 1, the shape is the same (`task_id`, `subject`, plus class-specific params). Verify each constructor through Step 2 — for example, `HITLBranchOperator` requires every option either to match a downstream task id directly or to be resolved via a mapping param surfaced in the registry.

---

## Step 4 — Behavior contracts (stable across versions)

### Timeout
- With `defaults` set: task succeeds on timeout, default option(s) selected.
- Without `defaults`: task fails on timeout.

### Markdown + Jinja in `body`
`body` supports Markdown and is Jinja-templatable. Render XCom context directly:

```python
body = """**Total Budget:** {{ ti.xcom_pull(task_ids='get_budget') }}

| Category | Amount |
|----------|--------|
| Marketing | $1M |
"""
```

### Callbacks
All HITL operators accept the standard Airflow callback kwargs (`on_success_callback`, `on_failure_callback`, etc.).

### Notifiers
HITL operators accept a `notifiers` list. Inside a notifier's `notify(context)` method, build a link to the pending task with `HITLOperator.generate_link_to_ui_from_context(context, base_url=...)`.

### Restricting who can respond
The parameter name and accepted identifier format depend on the active auth manager. Do **not** hardcode — check which one is active and which kwarg the current provider exposes:

```bash
uvx --from astro-airflow-mcp af config show | jq '.auth_manager // .core.auth_manager'
```

Then look up the current kwarg in Step 2 (at the time of writing it is `assigned_users`, accepting identifiers in whatever format the active auth manager uses — Astro uses the Astro user ID, FabAuthManager uses email, SimpleAuthManager uses username).

---

## Step 5 — Responding from external integrations

For Slack bots, custom apps, or scripts. Discover the live endpoint rather than hardcoding a path:

```bash
uvx --from astro-airflow-mcp af api ls --filter hitl           # live endpoint list
uvx --from astro-airflow-mcp af api spec \
  | jq '.paths | to_entries[] | select(.key | test("hitl"))'   # request/response schemas
```

The PATCH-to-respond pattern is stable; the exact path is discovered. Typical shape:

```python
import os, requests

HOST = os.environ["AIRFLOW_HOST"]
TOKEN = os.environ["AIRFLOW_API_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# List pending — use the path from `af api ls --filter hitl`
requests.get(f"{HOST}/<path>", headers=HEADERS, params={"state": "pending"})

# Respond — same discovered path family, PATCH
requests.patch(
    f"{HOST}/<path>/{dag_id}/{run_id}/{task_id}",
    headers=HEADERS,
    json={"chosen_options": ["Approve"], "params_input": {"comments": "ok"}},
)
```

---

## Step 6 — Safety checks

- [ ] Airflow version ≥ 3.1 (`af config version`).
- [ ] Constructor kwargs match the current registry output from Step 2 — no `respondents`-vs-`assigned_users` style drift.
- [ ] For branching: every option resolves to a downstream task id (directly or via the mapping kwarg from Step 2).
- [ ] Every value in `defaults` is also in `options`.
- [ ] `execution_timeout` set; `defaults` configured if timeout should succeed rather than fail.
- [ ] API token configured if external responders are part of the flow.

---

## References

The upstream docs URL is surfaced per-module by the registry — do not hardcode:

```bash
uvx --from astro-airflow-mcp af registry modules standard \
  | jq '.modules[] | select(.import_path | test("\\.hitl\\.")) | {name, docs_url}'
```

## Related skills

- **airflow** — `af registry`, `af api`, `af config` command reference.
- **airflow-ai** — AI/LLM task decorators and GenAI patterns.
- **authoring-dags** — general DAG writing best practices.
- **testing-dags** — iterative test → debug → fix cycles.
