---
name: configuring-airflow-language-sdks
description: Configure Airflow to run language SDK tasks (Java, Go, and future native SDKs): register a coordinator, map a queue to it, ensure the runtime/artifact on workers, and tune coordinator options. Use when the user wants Airflow to route a queue to a native-language coordinator, asks about the `[sdk]` `coordinators`/`queue_to_coordinator` settings, `AIRFLOW__SDK__COORDINATORS`, `jars_root`/`executables_root` or other coordinator `kwargs`, `JavaCoordinator` or `ExecutableCoordinator`, `task_startup_timeout`, or why their native tasks aren't being picked up. Covers the shared routing mechanism plus per-coordinator options (JavaCoordinator, ExecutableCoordinator).
---

# Configuring Airflow for Language SDKs

To run language SDK tasks, Airflow needs to know two things: which **coordinator** launches the native subprocess, and which **queue** routes to that coordinator. The mechanism is identical across every language SDK; only each coordinator's `classpath` and `kwargs` differ. This skill documents the shared wiring once, then the per-coordinator options. It is platform-neutral: the same settings apply on open-source Airflow and on managed platforms like Astro.

> **Experimental.** The language SDKs are in preview; configuration keys may change.

> For the task code, see the per-language authoring skill (**authoring-java-sdk-tasks**, **authoring-go-sdk-tasks**) and the shared **authoring-language-sdk-tasks**. For building and shipping the artifact, see the per-language deploy skill (**deploying-java-sdk-bundles**, **deploying-go-sdk-bundles**).

---

## Prerequisites on the worker

- The **runtime or artifact the SDK needs** must be present on the worker nodes, because the coordinator spawns a native subprocess per task instance. What that is differs per SDK (see [Per-coordinator options](#per-coordinator-options)):
  - **JVM SDKs (Java):** a language runtime (JRE 17+) plus the compiled JAR(s).
  - **Compiled-executable SDKs (Go):** no language runtime. The bundle is a self-contained native executable, but it must be built for the worker's OS/arch.
- The compiled/native **artifact(s)** must be reachable on the worker. See the per-language deploy skill.
- The coordinators ship with the Airflow Task SDK (`apache-airflow-task-sdk`, installed with Airflow). **No extra Python package is required.**

---

## The two settings

Both live in the `[sdk]` configuration section and apply to every language SDK:

1. **`coordinators`**: a JSON object mapping a coordinator *name* you choose to its implementation (`classpath`) and constructor `kwargs`.
2. **`queue_to_coordinator`**: a JSON object mapping a task *queue* to a coordinator name.

A task whose stub sets `queue="..."` is handed to the named coordinator, which launches the native subprocess. The coordinator name is arbitrary; it just has to be the same string in both settings. The queue name must match the `queue=` set on the Python `@task.stub`.

### Option A: `airflow.cfg`

```ini
[sdk]
coordinators = {
  "java-jdk17": {
    "classpath": "airflow.sdk.coordinators.java.JavaCoordinator",
    "kwargs": {"jars_root": ["/opt/airflow/jars"]}
  },
  "go": {
    "classpath": "airflow.sdk.coordinators.executable.ExecutableCoordinator",
    "kwargs": {"executables_root": ["/opt/airflow/executable-bundles"]}
  }
}
queue_to_coordinator = {"java": "java-jdk17", "golang": "go"}
```

### Option B: environment variables

Each value must be **valid one-line JSON**. This form is convenient for containers, `.env` files, Docker Compose, and Helm.

```bash
export AIRFLOW__SDK__COORDINATORS='{"go": {"classpath": "airflow.sdk.coordinators.executable.ExecutableCoordinator", "kwargs": {"executables_root": ["/opt/airflow/executable-bundles"]}}}'
export AIRFLOW__SDK__QUEUE_TO_COORDINATOR='{"golang": "go"}'
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
| `main_class` | *(auto-detect)* | Explicit entry-point class. If omitted, the coordinator scans `jars_root` for a JAR whose manifest declares `Main-Class`. **Set this explicitly if multiple executable JARs are present**, otherwise the choice is non-deterministic. |
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

### ExecutableCoordinator (Go and other self-contained-executable SDKs)

- **`classpath`**: `airflow.sdk.coordinators.executable.ExecutableCoordinator`
- **Worker runtime**: none beyond the bundle itself. The bundle is a self-contained native executable (AFBNDL01), so it needs no language runtime, but it must be built for the worker's OS/arch (a mismatch fails with `exec format error`).

| Parameter | Default | Description |
|-----------|---------|-------------|
| `executables_root` | *(required)* | One or more directories scanned **recursively** for executable bundles (AFBNDL01-trailered native binaries). Accepts a string or a list of strings/paths. Bundles are identified by the trailer magic, not by filename. The coordinator matches an incoming `dag_id` against each bundle's embedded manifest and verifies its integrity hash before launching. |

---

## Verifying the configuration

1. Confirm the runtime/artifact is present where workers run (e.g. `java -version` for Java; for Go, that the packed bundle exists and matches the worker's OS/arch) via `astro dev bash` or `docker compose exec ...`.
2. Confirm the artifact directory referenced in `kwargs` (`jars_root` / `executables_root`) actually contains your artifact on the worker filesystem.
3. Trigger the Dag and open the native task's logs; you should see the subprocess start and your task output.

### Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Task fails immediately mentioning coordinator or queue | `coordinators` / `queue_to_coordinator` not valid one-line JSON, or the queue name doesn't match the stub's `queue=`. Fix the JSON and restart. |
| Runtime not found (e.g. `java: command not found`) | The language runtime isn't on the worker, or the executable path kwarg is wrong. Install the runtime and verify its version. |
| "No artifact found" / "no Dags" / "no bundle contains dag_id" | The artifact-directory kwarg points at the wrong place, the artifact isn't there yet, or its `dag_id` doesn't match the stub. Confirm the path and the IDs. |
| Go bundle is skipped silently | Not a valid AFBNDL01 bundle, or its integrity hash failed (re-pack after any strip/sign/rebuild). |
| `exec format error` on the Go bundle | Built for a different OS/arch than the worker. Cross-compile with `--goos`/`--goarch` (see **deploying-go-sdk-bundles**). |
| Dag run hangs at the native task | Raise `task_startup_timeout` (e.g. `30.0`); first-run subprocess startup can be slow. |
| Wrong/ambiguous entry point (Java) | Multiple executable JARs under `jars_root`. Set `main_class` explicitly. |

---

## Related Skills

- **authoring-language-sdk-tasks**: The shared Python-stub pattern and conceptual model.
- **authoring-java-sdk-tasks**: Java task code and matching Python stubs.
- **authoring-go-sdk-tasks**: Go task code and matching Python stubs.
- **deploying-java-sdk-bundles**: Build the Java bundle and put the JAR where the coordinator scans.
- **deploying-go-sdk-bundles**: Build/pack the Go bundle and place it where the coordinator scans.
- **deploying-airflow**: General deployment of Airflow on Astro, Docker Compose, or Kubernetes.
