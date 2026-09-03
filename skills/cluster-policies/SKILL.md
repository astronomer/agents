---
name: cluster-policies
description: Enforces governance and coding standards across every DAG in a deployment using Airflow cluster policies. Use when the user wants to validate or mutate DAGs, tasks, task instances, or Kubernetes pods at parse or schedule time - naming conventions, required tags/owners, queue or pool routing, connection restrictions, resource limits, or any "every DAG must..." rule; also on mentions of dag_policy, task_policy, task_instance_mutation_hook, pod_mutation_hook, airflow_local_settings.py, or AirflowClusterPolicyViolation. Not for validation a DAG author opts into themselves inside their own DAG file (see authoring-dags).
---

# Airflow Cluster Policies

Cluster policies are plain Python functions that Airflow calls automatically while parsing DAGs, scheduling task instances, and building Kubernetes pods. They can inspect and reject non-compliant DAGs/tasks, or silently mutate attributes (queue, pool, tags, connections, pod spec) to enforce a standard across every project in a deployment — without any individual DAG author having to opt in.

> **Applies to**: every DAG file parsed by the DAG processor and every task instance scheduled in the deployment where the policy is installed — not just the DAG that triggered the check.
>
> **Verify your installed version first**: `af config version`, then match it against the versioned docs in Step 2 below. Cluster policy hook signatures have changed across Airflow releases (for example, whether `task_instance_mutation_hook` also receives the `DagRun`) — do not assume the shape below is exact for your version.
>
> **Cross-references**: `airflow` for `af config`/`af registry`/`af api` discovery commands; `airflow-plugins` for the plugin entry-point mechanism reused in Step 5.

---

## Step 1 — Pick the hook type you need

| Hook | Object it receives | Fires when | Example governance use case |
|---|---|---|---|
| `dag_policy` | `DAG` | Once per DAG file, after the `DAG` object is fully built during DAG processing | Reject any DAG where `catchup=True` and `max_active_runs != 1`; require an owner email inside `tags` |
| `task_policy` | `BaseOperator` | Once per task, during the same DAG-processing pass — mutates the shared task template, so the change applies to every run of that task | Force every `KubernetesPodOperator` or `deferrable=True` task onto a dedicated lightweight queue; restrict which connections a task may reference |
| `task_instance_mutation_hook` | `TaskInstance` | Scheduler-side, when a task instance row is created or reconciled — may run more than once for the same instance as it moves through scheduling | Route only high map-index dynamic-mapped instances to a bigger-resource queue; drop success callbacks on manually-triggered or backfill runs |
| `pod_mutation_hook` | `kubernetes.client.models.V1Pod` | Once per worker pod, immediately before the `KubernetesExecutor` or `KubernetesPodOperator` submits it | Add a toleration or `nodeSelector` so Kubernetes-run tasks land on a specific node pool |

This table is an anchor, not a contract — the exact parameters accepted by each hook can gain optional arguments across Airflow releases. Confirm the live signature with Step 2 before writing code against it.

---

## Step 2 — Verify hook signatures before writing code

```bash
af config version
```

Then read the hookspecs straight from the Airflow version actually installed, rather than trusting memory:

```bash
python -c "import inspect, airflow.policies as p; print(inspect.getsource(p))"
```

Cross-check against the docs page for that exact version — swap `stable` for the version string from `af config version`:

```
https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/cluster-policies.html
```

If the introspected source shows a parameter this skill doesn't mention (for example, an optional `dag_run` argument added to `task_instance_mutation_hook`), prefer the introspected signature — it is ground truth for the running deployment.

---

## Step 3 — Canonical example (a governance policy module)

One module implementing all four hooks together — the shape to drop into `airflow_local_settings.py` (Step 5a) or a plugin module (Step 5b) unmodified. Adapt the conditions to your own rules; verify attribute names against Step 2 first.

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from airflow.exceptions import AirflowClusterPolicyViolation

if TYPE_CHECKING:
    from airflow.models.baseoperator import BaseOperator
    from airflow.models.dag import DAG
    from airflow.models.taskinstance import TaskInstance
    from kubernetes.client.models import V1Pod

log = logging.getLogger(__name__)


def dag_policy(dag: DAG) -> None:
    if dag.catchup and dag.max_active_runs != 1:
        raise AirflowClusterPolicyViolation(
            "If catchup is enabled, max_active_runs must be set to 1."
        )
    if not any(tag.endswith("@yourcompany.com") for tag in dag.tags):
        raise AirflowClusterPolicyViolation(
            f"DAG '{dag.dag_id}' must carry an owner email in its tags."
        )


def task_policy(task: BaseOperator) -> None:
    kpo_path = "airflow.providers.cncf.kubernetes.operators.pod.KubernetesPodOperator"
    task_path = f"{task.__class__.__module__}.{task.__class__.__name__}"
    if task_path == kpo_path or getattr(task, "deferrable", False):
        task.queue = "kubernetes-and-deferred-queue"
        log.info("cluster_policy: %s.%s routed to %s", task.dag_id, task.task_id, task.queue)


def task_instance_mutation_hook(task_instance: TaskInstance) -> None:
    if task_instance.map_index is not None and task_instance.map_index > 5:
        task_instance.queue = "spare-high-resource-queue"
        log.info(
            "cluster_policy: %s map_index=%s routed to %s",
            task_instance.task_id,
            task_instance.map_index,
            task_instance.queue,
        )


def pod_mutation_hook(pod: V1Pod) -> None:
    from kubernetes.client import models as k8s

    pod.spec.tolerations = (pod.spec.tolerations or []) + [
        k8s.V1Toleration(key="node-group", operator="Equal", value="airflow-worker", effect="NoSchedule")
    ]
```

---

## Step 4 — Behavior contracts (stable across versions)

### Parsing vs. scheduling vs. pod build
- `dag_policy` and `task_policy` run during DAG processing — before the DAG is usable at all. A `DAG`/task that fails either one never becomes runnable.
- `dag_policy` runs after the `DAG` object is fully constructed, so mutating `dag.default_args` inside it has no effect on tasks that already exist — use `task_policy` for anything that needs to change per-task behavior.
- `task_policy` mutates the operator template itself: every task instance derived from that task inherits the change. `task_instance_mutation_hook` operates at the instance level and can target specific instances selectively (by `try_number`, `map_index`, run type, and so on) without touching the shared template.
- `pod_mutation_hook` runs once, synchronously, right before the pod spec is submitted to Kubernetes — there is no second pass the way there can be for task instances.

### Two exceptions, two outcomes
- Raise `AirflowClusterPolicyViolation` (`airflow.exceptions`) to reject a DAG or task outright. It is recorded in the metadata database's import-error table and shown to every user as a DAG Import Error in the Airflow UI — the DAG stays broken until the author fixes it.
- Raise `AirflowClusterPolicySkipDag` instead when you want to deliberately exclude a DAG (for example, an opt-in beta tag) without it looking broken — it is not recorded as an import error and does not appear in the UI's error list. Default to `AirflowClusterPolicyViolation`; reach for the skip variant only when silent exclusion is genuinely the intended behavior.

### Import hygiene
When type-hinting `dag: DAG` at module scope in a policy module, import `DAG` from `airflow.models.dag` rather than the top-level `airflow` package, to avoid a circular import during Airflow's own startup.

---

## Step 5 — Testing cluster policies

Policies run inline during parsing or scheduling — there's no CLI or REST endpoint to invoke them through. Test them like any plain function: construct the object the hook expects and call it directly.

```python
import pytest
from airflow.exceptions import AirflowClusterPolicyViolation
from airflow.models.dag import DAG

from airflow_local_settings import dag_policy


def test_dag_policy_rejects_catchup_with_max_active_runs_over_one():
    dag = DAG(
        dag_id="backfill_heavy",
        schedule="@daily",
        catchup=True,
        max_active_runs=5,
        tags=["team@yourcompany.com"],
    )
    with pytest.raises(AirflowClusterPolicyViolation):
        dag_policy(dag)
```

The same pattern covers the other three hooks: build a `BaseOperator(task_id=..., dag=dag)` and call `task_policy(task)` directly; build a `TaskInstance(task=task, run_id=...)` and call `task_instance_mutation_hook(ti)` directly; construct a `kubernetes.client.models.V1Pod` fixture and call `pod_mutation_hook(pod)` directly. None of this requires a running scheduler or webserver.

---

## Step 6 — Safety-critical rules

Cluster policies do not run in a sandbox. They execute inline, synchronously, inside the same process doing the most important job in the deployment. These two rules are not suggestions:

**Never perform blocking I/O inside a policy function.** No network calls, no `sleep`, nothing that isn't near-instant, in-memory, CPU-bound logic. `dag_policy` and `task_policy` run inside the DAG processor for every parse of every DAG file; `task_instance_mutation_hook` runs inside the scheduler's own loop while it holds an open transaction, so it must not open a new database session or call anything that implicitly commits one (for example, don't call `task_instance.get_dagrun()` without passing the active session). A single slow or hanging policy stalls or crashes that process — taking down scheduling for every DAG and every task in the deployment, not just the one being evaluated.

**Always document or log every mutation a policy makes.** A policy that silently changes `queue`, `pool`, `retries`, callbacks, or any other attribute is invisible in the DAG author's own source code. When their task lands on a different queue than the one written in the DAG file, or picks up a callback they never added, they have no way to find out a policy did it unless the policy says so — in a log line, in the shared policy module's own documentation, or in team-facing docs. Treat every mutation branch as something that must be discoverable, not just correct.

---

## Step 7 — Two implementation paths

**(a) `airflow_local_settings.py` — single project.** Place the module at `$AIRFLOW_HOME/config/airflow_local_settings.py` with plain functions named `dag_policy`, `task_policy`, `task_instance_mutation_hook`, `pod_mutation_hook`. On Astro, this is the project's `config/` directory, picked up by the Dockerfile's build (confirm your Dockerfile actually copies `config/` if it was customized away from the default). Use this when the policy only needs to apply to one project/deployment.

**(b) A shared, `@hookimpl`-decorated module — many projects.** Decorate functions with `@hookimpl` from `airflow.policies` instead of relying on the bare function name:

```python
from airflow.policies import hookimpl


@hookimpl
def task_policy(task) -> None:
    ...
```

Either drop this module inside a project's `plugins/` directory (Airflow's plugin manager auto-discovers `@hookimpl` functions there, no `AirflowPlugin` subclass required), or ship it as a proper pip-installed package that registers the `airflow.policy` setuptools entry point so every project that installs the package gets the same governance for free:

```toml
[project.entry-points."airflow.policy"]
governance = "my_package.policies"
```

Multiple registered implementations of the same hook are all called (pluggy chains them); use this path once the same policy needs to apply across more than one Airflow project.

---

## Safety checklist

- [ ] No network calls, `sleep`, or other blocking I/O anywhere in a `dag_policy`, `task_policy`, `task_instance_mutation_hook`, or `pod_mutation_hook`.
- [ ] `task_instance_mutation_hook` opens no new DB session and calls nothing that implicitly commits one.
- [ ] Every mutation branch has a paired log statement, or is otherwise documented somewhere a DAG author will actually find it.
- [ ] Rejections raise `AirflowClusterPolicyViolation` with a message specific enough to self-serve a fix; deliberate exclusions raise `AirflowClusterPolicySkipDag` instead.
- [ ] Conditions were checked against the introspected hookspec (Step 2) for the Airflow version actually running, not from memory.
- [ ] Every branch has a direct unit test that constructs the object and calls the hook (Step 5 pattern).

---

## References

- [Apache Airflow — Cluster Policies](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/cluster-policies.html) — swap `stable` for the version from `af config version` to see the exact signatures and exceptions for that release.
- `python -c "import inspect, airflow.policies as p; print(inspect.getsource(p))"` — the hookspecs for the Airflow version actually installed.

## Related skills

- **airflow** — `af config`, `af registry`, and `af api` command reference used for discovery in Step 2.
- **airflow-plugins** — building Airflow plugins with `plugins/`-directory modules and setuptools entry points; the same mechanism used to share a policy in Step 7b.
- **authoring-dags** — general DAG writing conventions a cluster policy might enforce.
- **setting-up-astro-project** — project structure, including the `config/` directory used for `airflow_local_settings.py` on Astro.
