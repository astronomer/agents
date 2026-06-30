---
name: authoring-language-sdk-tasks
description: The language-neutral foundation for Airflow language SDKs — implement task logic in a non-Python language while the Dag stays in Python. Use when the user wants to run an Airflow task in another language (Java, Kotlin, or other JVM/native languages), asks how the Python `@task.stub` pairs with native task code, how task/Dag IDs must match across the two sides, how data passes via XCom as JSON, or which language SDKs exist. This skill owns the shared Python-stub pattern and conceptual model; for a specific language's native API, build, and runtime, use that language's skill (e.g. authoring-java-sdk-tasks).
---

# Authoring Language SDK Tasks (Shared Foundation)

Airflow language SDKs let you implement task logic in a language other than Python while the Dag and its scheduling stay in Python. This skill describes the parts that are identical across every language SDK. Each language has its own companion skill for the native API, build tooling, and runtime — see [Per-language skills](#per-language-skills).

> **Experimental.** The language SDKs are in preview. APIs and artifact coordinates may change.

---

## The model

A Dag is authored in Python as usual. Tasks that should run in another language are declared as **stubs** routed to a dedicated queue. At runtime, Airflow hands a stub task to a **coordinator** that launches a short-lived **native subprocess** for that one task instance, runs your compiled/native code, and shuts the subprocess down.

Consequences that hold for every language SDK:

- **One subprocess per task instance** — there is no shared in-process state between task instances. Pass data via XCom or an external store.
- **The Dag, schedule, retries, and queue routing live in Python.** The native side only implements task logic.
- **Data crossing the boundary is JSON.** See [The XCom-as-JSON contract](#the-xcom-as-json-contract).

---

## The two-sided model

Every task has two halves that must agree:

1. A **Python stub** in a normal Dag file — no logic; it declares the task, its queue, the dependency graph, and retry policy.
2. A **native implementation** (Java, etc.) whose IDs match the Python side and where the work happens.

### Python side (scheduling)

The example below uses the Java SDK to be concrete, but the Python side is **identical for every language SDK**. The queue name (`"java"` here) is an arbitrary label you choose — it just has to match a key in `queue_to_coordinator` (see **configuring-airflow-language-sdks**). Pick whatever name fits the SDK you're routing to.

```python
from datetime import timedelta
from airflow.sdk import dag, task


@dag
def sales_pipeline():
    @task.stub(queue="java")            # queue selects the coordinator (see configuring-airflow-language-sdks)
    def extract(): ...

    @task.stub(queue="java")
    def transform(extracted): ...        # arg only declares the dependency

    @task.stub(queue="java", retries=1, retry_delay=timedelta(seconds=5))
    def load(transformed): ...

    @task()                              # an ordinary Python task can sit downstream
    def report(loaded):
        print(f"done: {loaded}")

    report(load(transform(extract())))


sales_pipeline()
```

Rules that apply regardless of language:

- The **stub function name is the task ID** and the `@dag` name (or `dag_id=`) is the Dag ID. The native side must use these exact IDs.
- An upstream argument on a stub (e.g. `transform(extracted)`) exists **only to declare the dependency** in Python. The value itself is fetched on the native side via XCom — passing it in Python does not hand it to the native code.
- **Queue, retries, and other task arguments are set on the stub**, not in the native code. A native task that fails is reported back to Airflow, which then applies the stub's retry policy.
- The `queue` value is what routes the task to a coordinator; the same string must appear in `queue_to_coordinator` (see **configuring-airflow-language-sdks**).

---

## The XCom-as-JSON contract

XCom values are stored as JSON in Airflow's metadata database, so the boundary between Python and any native language is JSON. The Python/JSON side is the same for every SDK:

| Python type | JSON |
|-------------|------|
| `int` | number (integer) |
| `float` | number (decimal) |
| `str` | string |
| `bool` | boolean |
| `None` | null |
| `list` | array |
| `dict` | object |

Each language SDK maps these JSON types onto its own native types (e.g. a JSON integer becomes a Java `Long`). The native-type column lives in that language's skill. The key portability rule: a value pushed by one task is read by another **as JSON**, so the consuming side must expect a type compatible with what was stored.

---

## What is language-specific (and lives elsewhere)

This skill deliberately stops at the shared concepts. The following differ per language and are documented in each language's companion skills:

- **Native task API** — how you declare tasks, read connections/variables/XComs, and push results (annotations, interfaces, function registration, etc.).
- **Native type mapping** — the native column of the JSON table above.
- **Build and packaging** — how the artifact is compiled and bundled.
- **Runtime prerequisite** — what must be installed on the worker (e.g. a JRE).

The Airflow-side wiring (which coordinator runs which queue) is shared in structure but has per-coordinator options; it lives in **configuring-airflow-language-sdks**.

---

## Language-agnostic pitfalls

- **IDs must match exactly** across the Python stub function name and the native task ID, and across `@dag`/`dag_id` and the native Dag ID. Mismatches surface as "no Dags" or missing-XCom errors.
- **Both sides need the upstream reference.** Python declares the dependency by passing the upstream call; the native code retrieves the value via XCom.
- **Set queue and retries on the stub**, never in the native code.
- Assets, deferral, and some other Airflow features have limited or no support in the language SDKs today.

---

## Per-language skills

- **authoring-java-sdk-tasks**: Java/Kotlin/JVM native API, type mapping, and logging.
- *(Future language SDKs each add their own `authoring-<lang>-sdk-tasks` skill that builds on this one.)*

## Related Skills

- **configuring-airflow-language-sdks**: Route a queue to a coordinator and set runtime options.
- **authoring-dags**: General Airflow DAG authoring (the Python side lives here too).
- **deploying-java-sdk-bundles**: Build and ship the Java artifact (per-language deploy skills follow the same shape).
