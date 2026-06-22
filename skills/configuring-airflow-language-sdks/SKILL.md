---
name: configuring-airflow-language-sdks
description: Configure Airflow to run language SDK tasks (Java and future native SDKs) — register a coordinator, map a queue to it, ensure the language runtime on workers, and tune coordinator options. Use when the user wants Airflow to route a queue to a native-language coordinator, asks about the `[sdk]` `coordinators`/`queue_to_coordinator` settings, `AIRFLOW__SDK__COORDINATORS`, `jars_root` or other coordinator `kwargs`, `task_startup_timeout`, or why their native tasks aren't being picked up. Covers the shared routing mechanism plus per-coordinator options (e.g. JavaCoordinator).
---

# Configuring Airflow for Language SDKs

To run language SDK tasks, Airflow needs to know two things: which **coordinator** launches the native subprocess, and which **queue** routes to that coordinator. The mechanism is identical across every language SDK — only each coordinator's `classpath` and `kwargs` differ. This skill documents the shared wiring once, then the per-coordinator options. It is platform-neutral: the same settings apply on open-source Airflow and on managed platforms like Astro.

> **Experimental.** The language SDKs are in preview; configuration keys may change.

> For the task code, see **authoring-language-sdk-tasks** (and the per-language authoring skill). For building and shipping the artifact, see the per-language deploy skill (e.g. **deploying-java-sdk-bundles**).

---

## Prerequisites on the worker

- The **language runtime** for the SDK you're using must be on the worker nodes, because the coordinator spawns a native subprocess per task instance. The exact runtime is per-SDK — see [Per-coordinator options](#per-coordinator-options) (for example, the Java SDK needs a **JRE 17+**).
- The compiled/native **artifact(s)** must be reachable on the worker. See the per-language deploy skill.
- The coordinators ship with the Airflow Task SDK (`apache-airflow-task-sdk`, installed with Airflow). **No extra Python package is required.**

---

## The two settings

Both live in the `[sdk]` configuration section and apply to every language SDK:

1. **`coordinators`** — a JSON object mapping a coordinator *name* you choose to its implementation (`classpath`) and constructor `kwargs`.
2. **`queue_to_coordinator`** — a JSON object mapping a task *queue* to a coordinator name.

A task whose stub sets `queue="..."` is handed to the named coordinator, which launches the native subprocess. The coordinator name is arbitrary — it just has to be the same string in both settings. The queue name must match the `queue=` set on the Python `@task.stub`.

### Option A: `airflow.cfg`

```ini
[sdk]
coordinators = {
  "java-jdk17": {
    "classpath": "airflow.sdk.coordinators.java.JavaCoordinator",
    "kwargs": {"jars_root": ["/opt/airflow/jars"]}
  }
}
queue_to_coordinator = {"java": "java-jdk17"}
```

### Option B: environment variables

Each value must be **valid one-line JSON**. This form is convenient for containers, `.env` files, Docker Compose, and Helm.

```bash
export AIRFLOW__SDK__COORDINATORS='{"java-jdk17": {"classpath": "airflow.sdk.coordinators.java.JavaCoordinator", "kwargs": {"jars_root": ["/opt/airflow/jars"]}}}'
export AIRFLOW__SDK__QUEUE_TO_COORDINATOR='{"java": "java-jdk17"}'
```

You can register **multiple coordinators** at once (e.g. one per language) and map different queues to each.

---

## Per-coordinator options

The `classpath` and `kwargs` are specific to each coordinator. Add a subsection here as new language SDKs land.

### JavaCoordinator

- **`classpath`**: `airflow.sdk.coordinators.java.JavaCoordinator`
- **Worker runtime**: JRE 17+ (`java` on `PATH`, or set `java_executable`).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `jars_root` | *(required)* | One or more directories scanned **recursively** for `.jar` files. Accepts a string or a list of strings/paths. The classpath is assembled automatically. |
| `java_executable` | `"java"` | Path to the `java` binary. Defaults to `java` on `$PATH`. |
| `jvm_args` | `[]` | Extra JVM arguments, e.g. `["-Xmx1g", "-Dsome.property=value"]`. |
| `main_class` | *(auto-detect)* | Explicit entry-point class. If omitted, the coordinator scans `jars_root` for a JAR whose manifest declares `Main-Class`. **Set this explicitly if multiple executable JARs are present** — otherwise the choice is non-deterministic. |
| `task_startup_timeout` | `10.0` | Seconds to wait for the subprocess to connect after launch. Increase it if JVM startup is slow (constrained hardware, large classpath, first cold start). |

**Java logging via `java.util.logging`.** Most Java logging integrations need only a build dependency (see **deploying-java-sdk-bundles**). The exception is a JUL `logging.properties` file, wired through `jvm_args`:

```ini
[sdk]
coordinators = {
  "java-jdk17": {
    "classpath": "airflow.sdk.coordinators.java.JavaCoordinator",
    "kwargs": {
      "jars_root": ["/opt/airflow/jars"],
      "jvm_args": ["-Djava.util.logging.config.file=/opt/airflow/logging.properties"]
    }
  }
}
```

*(Future coordinators — for other languages — will list their own `classpath`, runtime, and `kwargs` here.)*

---

## Verifying the configuration

1. Confirm the language runtime is present where workers run (e.g. `java -version` via `astro dev bash`, or `docker compose exec ... java -version`).
2. Confirm the artifact directory referenced in `kwargs` (e.g. `jars_root`) actually contains your artifact on the worker filesystem.
3. Trigger the Dag and open the native task's logs — you should see the subprocess start and your task output.

### Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Task fails immediately mentioning coordinator or queue | `coordinators` / `queue_to_coordinator` not valid one-line JSON, or the queue name doesn't match the stub's `queue=`. Fix the JSON and restart. |
| Runtime not found (e.g. `java: command not found`) | The language runtime isn't on the worker, or the executable path kwarg is wrong. Install the runtime and verify its version. |
| "No artifact found" / "no Dags" | The artifact-directory kwarg points at the wrong place, or the artifact isn't there yet. Confirm the path and that it was copied in. |
| Dag run hangs at the native task | Raise `task_startup_timeout` (e.g. `30.0`); first-run subprocess startup can be slow. |
| Wrong/ambiguous entry point (Java) | Multiple executable JARs under `jars_root`. Set `main_class` explicitly. |

---

## Related Skills

- **authoring-language-sdk-tasks**: The shared Python-stub pattern and conceptual model.
- **authoring-java-sdk-tasks**: Java task code and matching Python stubs.
- **deploying-java-sdk-bundles**: Build the bundle and put the artifact where the coordinator scans.
- **deploying-airflow**: General deployment of Airflow on Astro, Docker Compose, or Kubernetes.
