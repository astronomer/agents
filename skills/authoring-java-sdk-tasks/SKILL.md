---
name: authoring-java-sdk-tasks
description: Write Airflow task logic in Java, Kotlin, or any JVM language using the Airflow Java SDK. Use when the user wants to implement Airflow tasks in Java/JVM, asks about `@Builder.Dag`/`@Builder.Task`/`@Builder.XCom`, the `Task`/`BundleBuilder` interfaces, reading connections/variables/XComs from Java, the JSON-to-Java type mapping, or logging from Java tasks. This skill covers the Java-specific native API; the shared Python-stub pattern and conceptual model live in authoring-language-sdk-tasks. For building/shipping the bundle see deploying-java-sdk-bundles; for coordinator config see configuring-airflow-language-sdks.
---

# Authoring Java SDK Tasks

The Airflow Java SDK implements the language-SDK model for the JVM: your Dag stays in Python, and each task instance runs in a short-lived JVM subprocess. This skill covers the **Java-specific** native API. The shared model — the Python `@task.stub` pattern, ID matching, and the XCom-as-JSON contract — lives in **authoring-language-sdk-tasks**; read that first if you're new to language SDKs.

> **Experimental.** The Java SDK is in preview. Artifact coordinates and APIs may change.

> **Related skills:** **authoring-language-sdk-tasks** (shared Python stub + concepts), **configuring-airflow-language-sdks** (route the queue to `JavaCoordinator`), **deploying-java-sdk-bundles** (compile and ship the JAR).

---

## Recap: the Python side

Java tasks are paired with Python stubs that carry no logic — they declare the task, queue, dependency graph, and retries. IDs must match the Java annotations exactly, and an upstream argument on a stub only declares the dependency (the value is fetched in Java). Full rules are in **authoring-language-sdk-tasks**; the minimal shape:

```python
from airflow.sdk import dag, task


@dag
def sales_pipeline():                     # dag_id "sales_pipeline" -> @Builder.Dag(id="sales_pipeline")
    @task.stub(queue="java")
    def extract(): ...                    # task_id "extract" -> @Builder.Task(id="extract")

    @task.stub(queue="java")
    def transform(extracted): ...

    transform(extract())


sales_pipeline()
```

---

## Java side: two APIs

Both APIs produce identical runtime behavior; pick by style, and you can mix them in one bundle.

### Annotation-based API (recommended)

Annotate a plain class; an annotation processor generates the wiring (`<ClassName>Builder`) at compile time.

```java
import static java.lang.System.Logger.Level.INFO;
import org.apache.airflow.sdk.*;

@Builder.Dag(id = "sales_pipeline")          // must match the Python dag_id
public class SalesPipeline {
  private static final System.Logger log = System.getLogger(SalesPipeline.class.getName());

  @Builder.Task(id = "extract")              // must match the Python @task.stub name
  public long extract(Client client) {
    var conn = client.getConnection("sales_db");
    log.log(INFO, "connected to {0}", conn.host);
    return 42L;                              // return value is pushed as the return_value XCom
  }

  @Builder.Task(id = "transform")
  public long transform(
      Client client,
      @Builder.XCom(task = "extract") long recordCount) {  // pulls extract's return_value
    var threshold = (String) client.getVariable("transform_threshold");
    return recordCount * 2;
  }

  @Builder.Task   // id omitted -> the method name "load" is used
  public void load(Context context, @Builder.XCom(task = "transform") long transformed) {
    log.log(INFO, "attempt {0}, value {1}", context.ti.tryNumber, transformed);
  }
}
```

Annotation reference:

| Annotation | Purpose |
|------------|---------|
| `@Builder.Dag(id = "...")` | Marks the class as a task container. `id` must match the Python `dag_id`; if omitted, the class name is used. Optional `to = "..."` renames the generated builder (default `<ClassName>Builder`). |
| `@Builder.Task(id = "...")` | Marks a method as a task. `id` must match the Python `@task.stub` function name; if omitted, the method name is used. |
| `@Builder.XCom(task = "...", key = "...")` | Injects an upstream task's XCom as a parameter. `task` defaults to the parameter name; `key` defaults to the producing task's `return_value`. The parameter type must be compatible with the stored JSON value. |

A task method's return value is automatically pushed as that task's `return_value` XCom. A method may declare `throws Exception`; any uncaught exception fails the task instance (which triggers retries if the stub configured them).

### Interface-based API

Implement `Task` directly when you want full control over registration and XCom handling.

```java
import org.apache.airflow.sdk.*;

public class ExtractTask implements Task {
  @Override
  public void execute(Context context, Client client) throws Exception {
    var conn = client.getConnection("sales_db");
    // ... do work ...
    client.setXCom(42L);   // push return_value explicitly
  }
}
```

Register tasks manually in a `Dag` and expose it through a `BundleBuilder`:

```java
public class MyBundle implements BundleBuilder {
  @Override
  public Iterable<Dag> getDags() {
    var dag = new Dag("sales_pipeline");      // Dag ID matches Python
    dag.addTask("extract", ExtractTask.class);
    dag.addTask("transform", TransformTask.class);
    return java.util.List.of(dag);
  }
}
```

Each `Task` class needs a public no-arg constructor. Task IDs must be unique within a Dag, and Dag IDs unique within a bundle.

---

## The entry point

Every bundle has a `main` that hands your Dags to the SDK server. The server connects to the coordinator, runs one task instance, and exits.

```java
import java.util.List;
import org.apache.airflow.sdk.*;

public class Main implements BundleBuilder {
  @Override
  public Iterable<Dag> getDags() {
    // With the annotation API, the *Builder classes are generated at compile time.
    return List.of(SalesPipelineBuilder.build());
  }

  public static void main(String[] args) {
    Server.create(args).serve(new Main().build());
  }
}
```

`Server.create(args)` parses the connection details Airflow passes on the command line — don't construct them by hand. Record this `main` class as the bundle's main class when you build it (see **deploying-java-sdk-bundles**).

---

## Talking to Airflow from a task: `Client`

A `Client` is passed into every task and is scoped to the current Dag run and task instance.

| Call | Returns | Notes |
|------|---------|-------|
| `client.getConnection(id)` | `Connection` | Fields: `id`, `type`, `host`, `schema`, `login`, `password`, `port`, `extra`. Any unset field is `null`. Throws if the connection doesn't exist. |
| `client.getVariable(key)` | `Object` (or `null`) | Cast to the type you expect, e.g. `(String) client.getVariable("threshold")`. |
| `client.getXCom(taskId)` | `Object` (or `null`) | Reads another task's `return_value` by default. Overloads accept `key`, `dagId`, `runId`, `mapIndex`, and `includePriorDates` for cross-Dag/run reads and mapped tasks. |
| `client.setXCom(value)` | — | Pushes the `return_value` XCom (interface API). Value must be JSON-serializable. With the annotation API, returning a value does this for you. |

### `Context`

The `Context` parameter exposes run metadata: `context.dagRun` (`dagId`, `runId`) and `context.ti` (`dagId`, `runId`, `taskId`, `mapIndex`, `tryNumber`). `tryNumber` is useful for retry-aware logic.

---

## XCom: Java types

XComs cross the boundary as JSON (the shared contract is in **authoring-language-sdk-tasks**). When you read one back in Java you get:

| Python type | JSON | Java type from `getXCom` |
|-------------|------|--------------------------|
| `int` | integer | `Long` (or `BigInteger` if too large) |
| `float` | decimal | `Double` |
| `str` | string | `String` |
| `bool` | boolean | `Boolean` |
| `None` | null | `null` |
| `list` | array | `List<Object>` |
| `dict` | object | `Map<String, Object>` |

Declare `@Builder.XCom` parameter types to match. A mismatch (e.g. declaring `int` when the value is a `String`) fails the task.

---

## Logging

Declare a logger as a static field named after the class — the conventional pattern regardless of framework:

```java
private static final System.Logger log = System.getLogger(SalesPipeline.class.getName());
```

For records to reach Airflow's task log store (and show in the UI), the bundle must include one of the SDK logging integration artifacts (`airflow-sdk-jpl`, `airflow-sdk-slf4j`, `airflow-sdk-log4j2`, or `airflow-sdk-jul`). Those are build-time dependencies and integration steps — see **deploying-java-sdk-bundles**. `System.Logger` (JPL) with `airflow-sdk-jpl` is the lightest option and needs no configuration.

---

## A complete worked example ships with the SDK

The SDK repository includes a runnable example under `java-sdk/example/`:

- `src/resources/dags/java_examples.py` — Python Dags pairing Python tasks with Java stubs, including a `load` stub with `retries=1`.
- `src/java/.../AnnotationExample.java` — annotation API, including a task that fails on `tryNumber == 1` and succeeds on retry.
- `src/java/.../InterfaceExampleBuilder.java` — the same tasks via the `Task` interface and `Dag.addTask(...)`.
- `src/java/.../ExampleBundleBuilder.java` — a `BundleBuilder` returning both Dags plus the `main` entry point.

Point users there for an end-to-end reference.

---

## Java-specific pitfalls

- **Cast `Object` returns deliberately.** `getVariable` and `getXCom` return `Object`; match the cast to the JSON type (see the table above).
- **`@Builder.XCom` parameter types must match the stored JSON type**, or the task fails at runtime.
- **The annotation processor must be on the build** for the annotation API (generates `<ClassName>Builder`); it is not needed for the interface API. See **deploying-java-sdk-bundles**.
- See **authoring-language-sdk-tasks** for the language-agnostic pitfalls (ID matching, one JVM per task instance, queue/retries on the stub).

---

## Related Skills

- **authoring-language-sdk-tasks**: Shared Python-stub pattern and concepts (read first).
- **configuring-airflow-language-sdks**: Route the `java` queue to `JavaCoordinator` and set JRE/coordinator options.
- **deploying-java-sdk-bundles**: Build the bundle (Gradle/Maven) and place the JAR where Airflow can find it.
- **authoring-dags**: General Airflow DAG authoring.
