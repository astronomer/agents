---
name: deploying-java-sdk-bundles
description: Builds and deploys compiled Airflow Java SDK bundles so workers can run them. Use when the user wants to package a JVM task bundle into a JAR, asks about the `org.apache.airflow.sdk` Gradle plugin, `./gradlew bundle`, the Maven shade/BOM setup, fat vs thin JARs, the logging integration artifacts (JPL, SLF4J, Log4j 2, JUL), preview/snapshot builds, or getting the JAR onto an Airflow worker (Docker, Kubernetes, or Astro). For the task code see authoring-java-sdk-tasks; for the Airflow coordinator settings see configuring-airflow-language-sdks.
---

# Deploying Java SDK Bundles

A Java SDK deployment has one artifact: a **bundle** — your compiled task classes plus the SDK, packaged as a JAR (or a thin JAR alongside its dependency JARs). You build it with Gradle or Maven, then place it in a directory that the `JavaCoordinator` scans (`jars_root`) on every worker. This skill is platform-neutral; it shows the build once, then both an open-source and an Astro deployment path.

> **Experimental.** The Java SDK is in preview. Artifact versions below are shown as `${version}`; while the SDK is pre-release you may need to build the artifacts into your local Maven repository yourself (see the preview builds section).

> **Order of operations:** build the bundle (this skill) → place it where `jars_root` points → configure the coordinator (**configuring-airflow-language-sdks**). The task code itself is **authoring-java-sdk-tasks**.

---

## Build with Gradle (recommended)

Apply the SDK's Gradle plugin and declare dependencies in `build.gradle`:

```groovy
plugins {
    id("org.apache.airflow.sdk") version "${version}"
}

repositories {
    mavenCentral()
}

dependencies {
    annotationProcessor("org.apache.airflow:airflow-sdk-processor:${version}")  // annotation API only
    implementation("org.apache.airflow:airflow-sdk:${version}")
    // Optional logging integration, e.g.:
    // implementation("org.apache.airflow:airflow-sdk-jpl:${version}")
}

airflowBundle {
    mainClass = "com.example.Main"   // your BundleBuilder entry point
    // fatJar = false                // opt out of the single-JAR build (see below)
}
```

Build it:

```bash
./gradlew bundle
```

The `build/bundle/` directory then holds all required JAR(s). Notes:

- The `annotationProcessor` line is needed **only if you use the annotation-based API**. The interface-based API doesn't need it.
- By default the plugin produces a **fat JAR** (via the Shadow plugin) — one self-contained file, which avoids cross-project dependency clashes. Set `fatJar = false` in `airflowBundle` for thin JARs; you then deploy every dependency JAR too.
- The Gradle plugin validates that `mainClass` exists at build time (`verifyBundleMainClass`).

---

## Build with Maven

Import the BOM so artifact versions and the supervisor schema version are managed in one place:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>org.apache.airflow</groupId>
      <artifactId>airflow-sdk-bom</artifactId>
      <version>${version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.apache.airflow</groupId>
    <artifactId>airflow-sdk</artifactId>   <!-- version from the BOM -->
  </dependency>
</dependencies>
```

Wire the annotation processor through `maven-compiler-plugin` (annotation API only) so it stays off the runtime classpath. Then pick a packaging option:

- **Fat JAR (recommended):** use `maven-shade-plugin`. In its `ManifestResourceTransformer`, set `<mainClass>` to your `BundleBuilder` and add the manifest entry `Airflow-Supervisor-Schema-Version` resolved from the BOM property `${airflow.supervisor.schema.version}` (don't hard-code it). `mvn package` writes the JAR to `target/`.
- **Thin JAR:** use `maven-jar-plugin` to set `Main-Class` and `maven-dependency-plugin` (`copy-dependencies`) to collect runtime JARs into `target/bundle/`. Here `Airflow-Supervisor-Schema-Version` is not needed — Airflow reads it from the `airflow-sdk` JAR on the classpath.

Unlike Gradle, Maven does **not** validate `mainClass` at build time; a wrong value only fails at runtime.

---

## Logging integration

For task log records to reach Airflow's log store (and the task log view in the UI), the bundle must include **exactly one** SDK logging artifact per logging facade you use. Versions are managed by `airflow-sdk-bom`; Maven users apply the same artifact IDs.

**Choosing a facade.** For a greenfield project, prefer JPL (`System.Logger`) — it is built into the JDK, so your tasks need no extra logging API. Pick another facade only when the libraries you integrate with already log through it, so their records reach Airflow too. Preference order: JPL > SLF4J = Log4j 2 > JUL; treat JUL as legacy integration only, not a choice for new code.

| Facade | Artifact | Setup beyond the dependency |
|--------|----------|-----------------------------|
| `System.Logger` (JPL) | `airflow-sdk-jpl` | None — the provider is discovered via `ServiceLoader`. |
| SLF4J 2.x | `airflow-sdk-slf4j` | None — the binding is discovered automatically (pulls in `slf4j-api` for you). |
| Log4j 2 | `airflow-sdk-log4j2` | `log4j-core` on the runtime classpath + `AirflowAppender` declared in `log4j2.xml` (below). |
| `java.util.logging` (JUL) | `airflow-sdk-jul` | Call `AirflowJulHandler.setup()` in `main()` (below), or use a `logging.properties` file (see **configuring-airflow-language-sdks**). |

**Log4j 2** — `log4j-core` hosts the plugin loader that discovers the appender (`log4j-api` comes in transitively):

```groovy
implementation("org.apache.airflow:airflow-sdk-log4j2:${version}")
runtimeOnly("org.apache.logging.log4j:log4j-core:${log4jVersion}")
```

```xml
<Configuration>
  <Appenders>
    <AirflowAppender name="Airflow"/>
  </Appenders>
  <Loggers>
    <Root level="info">
      <AppenderRef ref="Airflow"/>
    </Root>
  </Loggers>
</Configuration>
```

**JUL** — call `AirflowJulHandler.setup()` before any task runs. It clears the root logger's existing handlers (the default `ConsoleHandler` writes to stderr, which Airflow would otherwise capture as `task.stderr` at ERROR level, duplicating each record):

```java
public static void main(String[] args) {
    AirflowJulHandler.setup();
    Server.create(args).serve(new MyBundle().build());
}
```

**Don't double up providers.** A second `System.LoggerFinder` implementation alongside `airflow-sdk-jpl`, or a second SLF4J binding (`logback-classic`, `slf4j-simple`) alongside `airflow-sdk-slf4j`, makes provider selection unpredictable.

---

## Preview builds (before a stable release)

**Skip this section if you depend on a stable release.** Once you pin a released version (e.g. `1.0.0`) published to Maven Central, the `mavenCentral()` repository in the build snippets above is enough.

While the SDK is pre-release, the documented path is to build the artifacts and the Gradle plugin from the Airflow repo into your local Maven repository:

```bash
# in apache/airflow's java-sdk/ directory
./gradlew publishToMavenLocal -PskipSigning=true
```

Then add `mavenLocal()` in your project, in **both** `pluginManagement` (in `settings.gradle`) and project `repositories` (in `build.gradle`) — this is how the SDK's own example project resolves it.

Once `-SNAPSHOT` artifacts are published to Apache's snapshot Nexus, that repository can stand in for the local build (same two places):

```groovy
maven {
    name = "apacheSnapshots"
    url = "https://repository.apache.org/content/repositories/snapshots/"
    mavenContent { snapshotsOnly() }
}
```

Snapshots move; force a refresh with `./gradlew bundle --refresh-dependencies`. (For Maven, add the same repository to `<repositories>` and `<pluginRepositories>`.)

---

## Place the bundle where the coordinator scans

The coordinator scans `jars_root` recursively and builds the classpath automatically, so you copy the whole output directory:

```bash
cp build/bundle/* /opt/airflow/jars/    # /opt/airflow/jars == jars_root
```

The worker also needs a **JRE 17+**. Wiring the coordinator to this directory is covered in **configuring-airflow-language-sdks**.

---

## Deployment paths

Astronomer tooling is **not required** — the SDK runs on any Airflow with the Task SDK. Choose the path that matches the user's setup.

### Open-source (Docker / Kubernetes)

Bake the JRE and the bundle into your Airflow image, or mount them:

```dockerfile
FROM apache/airflow:3          # pin a specific 3.x in production
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/airflow/jars
COPY build/bundle/ /opt/airflow/jars/
USER airflow
```

On Kubernetes (Helm chart), bake the JAR into a custom image as above, or mount it via a shared volume; set the `[sdk]` config through environment variables on the worker/scheduler. See **deploying-airflow** for the broader Docker Compose and Helm workflow.

### Astro (one option, not required)

If the user is on Astronomer's Astro CLI, the same idea maps onto an Astro project:

1. Build the bundle, then stage it in the project: `mkdir -p include/jars && cp ../java-bundle/build/bundle/*.jar include/jars/`.
2. Edit the project `Dockerfile` to install a JRE and copy the JARs to the coordinator's directory:

   ```dockerfile
   FROM quay.io/astronomer/astro-runtime:<version>
   USER root
   RUN apt-get update \
       && apt-get install -y --no-install-recommends default-jre-headless \
       && apt-get clean && rm -rf /var/lib/apt/lists/*
   RUN mkdir -p /opt/airflow/jars
   COPY include/jars/ /opt/airflow/jars/
   USER airflow
   ```

3. Put the coordinator config in the project's `.env` (loaded automatically) — see **configuring-airflow-language-sdks** for the `AIRFLOW__SDK__*` values.
4. `astro dev start` (or `astro dev restart` after changes) builds the image and starts Airflow locally; deploy with `astro deploy` as usual.

> Don't pin Astro Runtime / Airflow versions from memory — read the generated `Dockerfile` or check current docs. While the SDK and Airflow 3.3 are in preview, a beta/dev Astro Runtime image may be required.

---

## Deploy checklist

- Bundle built (`./gradlew bundle` or `mvn package`) and `mainClass` points at your `BundleBuilder`.
- `annotationProcessor` present **iff** you use the annotation API.
- JAR(s) copied into the worker's `jars_root` directory; with thin JARs, dependency JARs too.
- JRE 17+ available on the worker.
- Coordinator + `queue_to_coordinator` configured (**configuring-airflow-language-sdks**).
- If multiple executable JARs exist under `jars_root`, set `main_class` explicitly.

---

## Related Skills

- **authoring-java-sdk-tasks**: Write the Java task code and the matching Python stubs.
- **configuring-airflow-language-sdks**: Register the coordinator and route the queue.
- **deploying-airflow**: General Airflow deployment (Astro, Docker Compose, Kubernetes).
- **setting-up-astro-project**: Initialize and configure an Astro project.
