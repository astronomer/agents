---
name: deploying-go-sdk-bundles
description: Build, pack, and deploy compiled Airflow Go SDK bundles so the ExecutableCoordinator can run them. Use when the user wants to compile a Go task bundle, asks about `go build`, `go tool airflow-go-pack`, the AFBNDL01 self-contained executable bundle, packing or inspecting a bundle, placing it under `executables_root`, cross-compiling a bundle for workers, `go-sdk` module versioning/tags/pseudo-versions, or getting the bundle onto an Airflow worker (Docker, Kubernetes, or Astro). For the task code see authoring-go-sdk-tasks; for the shared coordinator settings see configuring-airflow-language-sdks.
---

# Deploying Go SDK Bundles

A Go SDK deployment has one artifact: a **bundle**, a single self-contained native executable that also carries its embedded source and a manifest (the AFBNDL01 format, "the executable *is* the bundle"). You build and pack it with `go`, place it where Airflow's `ExecutableCoordinator` scans, and the Python task runner forks it once per task instance. This skill is platform-neutral: it shows the build, the coordinator wiring, then how to get the bundle onto a worker.

> **Experimental.** The Go SDK is under active development and not production-ready. Everything resolves against the single module `github.com/apache/airflow/go-sdk` (Go 1.24+).

> **Order of operations:** write the tasks (**authoring-go-sdk-tasks**) -> build and pack the bundle (this skill) -> place it under `executables_root` and configure the coordinator -> deploy the matching Python stub Dag.

---

## Build and pack the bundle

The coordinator only recognizes a **packed** bundle: it scans for the AFBNDL01 trailer and silently skips any file that lacks it, so a plain `go build` binary is not deployable on its own. Use the packer, shipped as a Go 1.24 `tool` directive in `go.mod` (no global install, version pinned per project):

```bash
go tool airflow-go-pack ./example/bundle                              # build + pack in one step
go tool airflow-go-pack --goos linux --goarch amd64 ./example/bundle -- -trimpath  # cross-compile; flags after -- pass to `go build`
go tool airflow-go-pack --executable ./bin/sample-dag-bundle --source main.go --airflow-metadata  # pack an existing binary
go tool airflow-go-pack inspect ./bin/sample-dag-bundle               # inspect a packed bundle
```

The packer builds the binary, execs it with `--airflow-metadata` to capture the manifest from `RegisterDags`, then appends source + manifest + a 64-byte trailer. The result is one runnable file.

- **Build for the worker's OS/arch.** The bundle is a native executable and is not portable; cross-compile with `--goos`/`--goarch`. A mismatched binary fails on the worker with `exec format error`.
- **Re-pack after any change to the binary.** Re-stripping, re-signing, or swapping in a debug build invalidates the trailer's `binary_sha256`, and the bundle is then rejected.

---

## Wire up the coordinator

Python's `ExecutableCoordinator` scans `executables_root`, matches the incoming `dag_id` against each bundle's embedded manifest, verifies its integrity hash, then forks the bundle. No Go process runs on the host.

1. Place the packed executable under a scanned directory:

   ```bash
   cp ./bundle /opt/airflow/executable-bundles/   # identified by the AFBNDL01 trailer, not by filename
   ```

2. Register `ExecutableCoordinator` and route the queue to it (see **configuring-airflow-language-sdks**):

   ```ini
   [sdk]
   coordinators = {"go": {"classpath": "airflow.sdk.coordinators.executable.ExecutableCoordinator", "kwargs": {"executables_root": ["/opt/airflow/executable-bundles"]}}}
   queue_to_coordinator = {"golang": "go"}
   ```

3. Deploy the matching Python stub Dag; its `queue=` must equal the `queue_to_coordinator` key (`golang` here), and its `dag_id`/`task_id`s must match what the bundle registered.

---

## Deployment paths

The SDK runs on any Airflow with the Task SDK; Astronomer tooling is not required.

### Docker / Kubernetes

Cross-compile the bundle for the image's platform and bake it in. No Go runtime or worker process is needed in the image; the Python task runner forks the bundle.

```dockerfile
FROM apache/airflow:3.3.0        # the language SDKs target Airflow 3.3+
COPY ./executable-bundles/ /opt/airflow/executable-bundles/
# set AIRFLOW__SDK__COORDINATORS and AIRFLOW__SDK__QUEUE_TO_COORDINATOR as env vars
```

On the Helm chart, bake the bundle into a custom image as above or mount it via a shared volume, and set the `[sdk]` config through environment variables on the worker/scheduler. See **deploying-airflow** for the broader Docker Compose and Helm workflow.

### Astro (one option, not required)

1. Build/pack the bundle, then stage it in the project: `mkdir -p include/executable-bundles && cp ../go-bundle/<packed-bundle> include/executable-bundles/`.
2. In the project `Dockerfile`, copy the bundle to the coordinator's directory: `COPY include/executable-bundles/ /opt/airflow/executable-bundles/`.
3. Put the coordinator config in the project `.env` (loaded automatically): the `AIRFLOW__SDK__*` JSON values (see **configuring-airflow-language-sdks**).
4. `astro dev start` (or `astro dev restart` after changes); deploy with `astro deploy`.

> Don't pin Astro Runtime / Airflow versions from memory; read the generated `Dockerfile` or current docs. While the Go SDK is in preview, a beta/dev image may be required.

---

## Versioning and preview installs

`go-sdk/` is a single Go module, so the only release tag is the module tag in monorepo subdir form, `go-sdk/vX.Y.Z` (do not create per-`cmd` tags). Your bundle module depends on `github.com/apache/airflow/go-sdk`; pinning that version also pins `airflow-go-pack`, which is a package in the same module referenced through the `tool` directive. Pin against a released tag once one exists:

```bash
go get github.com/apache/airflow/go-sdk@vX.Y.Z
```

No version has been voted on or released yet, and the existing `go-sdk/v1.0.0-beta1` tags in the repo are placeholders, not releases (`proxy.golang.org` caches tags immutably, so do not rely on them). To try an unreleased build before a real tag exists, depend on a commit or branch; Go fabricates a pseudo-version:

```bash
go get github.com/apache/airflow/go-sdk@<commit-or-branch>
```

---

## Deploy checklist

- Bundle built **and packed** (`go tool airflow-go-pack`); registered `dag_id`/`task_id` match the Python stubs.
- Built for the worker's OS/arch (e.g. `--goos linux --goarch amd64`).
- Packed AFBNDL01 bundle placed under a directory in `executables_root`.
- `ExecutableCoordinator` + `queue_to_coordinator` configured (**configuring-airflow-language-sdks**).
- Python stub Dag deployed, its `queue=` routed to the Go coordinator.
- Re-packed after any rebuild/strip/sign (preserves `binary_sha256`).

---

## Related Skills

- **authoring-go-sdk-tasks**: Write the Go task code and the matching Python stubs.
- **configuring-airflow-language-sdks**: Register `ExecutableCoordinator` and route the queue.
- **deploying-airflow**: General Airflow deployment (Astro, Docker Compose, Kubernetes).
- **setting-up-astro-project**: Initialize and configure an Astro project.
