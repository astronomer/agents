---
name: setting-up-astro-project
description: Initialize and configure Astro/Airflow projects (Astro CLI v2 `astro init` and pyproject.toml, or v1 `astro dev init`). Use when the user wants to create a new project, set up dependencies, configure connections/variables, or understand project structure. For running the local environment, see managing-astro-local-env.
---

# Astro Project Setup

This skill helps you initialize and configure Airflow projects using the Astro CLI.

> **To run the local environment**, see the **managing-astro-local-env** skill.
> **To write DAGs**, see the **authoring-dags** skill.
> **Open-source alternative:** If the user isn't on Astro, guide them to Apache Airflow's Docker Compose quickstart for local dev and the Helm chart for production. For deployment strategies, use the `deploying-airflow` skill.

---

## Astro CLI v1 or v2

Commands here are written for Astro CLI v2. Run `astro local af --help` once: it succeeds only on v2.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI (`uvx --from astro-airflow-mcp af` if `af` is not on PATH). Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is given beside it, marked `v1:`.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project: `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.

The two versions lay a project out differently: a v2 project is a `pyproject.toml` with a `[tool.astro]` table; a v1 project is a `Dockerfile`, `requirements.txt`, `packages.txt`, and `airflow_settings.yaml`. Each section below gives both.

---

## Initialize a New Project

```bash
astro init        # v1: astro dev init
```

> **Don't pass a version flag unless the user explicitly asks for a specific pin** (`--airflow-version` on v2; `--airflow-version` or `--runtime-version` on v1). Plain `astro init` / `astro dev init` resolves to the newest supported Airflow or Astro Runtime, which is the right default. Specifying a version risks pinning to a stale value from training data. If the user wants to know what was installed, read it afterward instead of guessing: the `apache-airflow` requirement in `pyproject.toml` (v1: the `FROM` line of the `Dockerfile`).

On v2, `astro init` in a directory that already holds a v1 project upgrades it in place (it moves `requirements.txt` and `packages.txt` into `pyproject.toml` and carries `airflow_settings.yaml` over), so run it there only when the user asks for that.

Creates this structure:

```
v2                                 v1
project/                           project/
├── dags/                          ├── dags/                 # DAG files
├── include/                       ├── include/              # SQL, configs, supporting files
├── plugins/                       ├── plugins/              # Custom Airflow plugins
├── tests/                         ├── tests/                # Unit tests
├── pyproject.toml   # manifest    ├── Dockerfile            # Image customization
└── AGENTS.md                      ├── packages.txt          # OS-level packages
                                   ├── requirements.txt      # Python packages
                                   └── airflow_settings.yaml # Connections, variables, pools
```

---

## Adding Dependencies

### Python Packages

```bash
uv add apache-airflow-providers-snowflake    # v1: add the line to requirements.txt
```

On v2, `uv add` writes the requirement into `pyproject.toml`, keeps the `[tool.uv]` pins that hold Airflow to the build a deployment runs, and installs the package into the project's `.venv`, where a running standalone Airflow can import it. Restart anyway for what a provider registers at startup (connection types, plugins); in Docker mode the restart is what puts the package in the image. On v1, `requirements.txt` takes pip requirement lines:

```
apache-airflow-providers-snowflake==5.3.0
pandas==2.1.0
requests>=2.28.0
```

### OS Packages

v2 lists them in `pyproject.toml`, as a key under the `[tool.astro]` table `astro init` already wrote (a second `[tool.astro]` header breaks the file); v1 in `packages.txt`, one per line:

```toml
# under the existing [tool.astro]
packages = ["gcc", "libpq-dev"]
```

On v2 only Docker mode (`astro local start --docker`) can install OS packages; standalone mode warns and runs without them.

### Custom Dockerfile

For complex setups (private PyPI, custom scripts). v1 always builds from the project's `Dockerfile`. v2 uses one only when the manifest names it (a key under the existing `[tool.astro]` table), only in Docker mode, and its `FROM` must name the same Airflow series as the manifest's pin:

```toml
# under the existing [tool.astro]
dockerfile = "Dockerfile"
```

```dockerfile
FROM quay.io/astronomer/astro-runtime:12.4.0

RUN pip install --extra-index-url https://pypi.example.com/simple my-package
```

**After modifying dependencies:** run `astro local restart` (v1: `astro dev restart`).

---

## Configuring Connections, Variables & Pools

### v2: `astro local env` and `[tool.astro.pools]`

v2 reads `airflow_settings.yaml` nowhere. Set connections and Airflow variables with `astro local env` (stored encrypted unless you pass `--plain`, which writes the project's `.env`):

```bash
astro local env connection set my_postgres --type postgres --host localhost --port 5432 --login user --schema mydb
# pipe the password in (a --password flag lands in shell history)
astro local env airflow-variable set env --value dev
astro local env list        # every declared value and where it resolves from
```

Pools are declared in `pyproject.toml`, and `astro local start` creates or updates them:

```toml
[tool.astro.pools.limited_pool]
slots = 5
```

### v1: `airflow_settings.yaml`

Loaded automatically on environment start:

```yaml
airflow:
  connections:
    - conn_id: my_postgres
      conn_type: postgres
      host: host.docker.internal
      port: 5432
      login: user
      password: pass
      schema: mydb

  variables:
    - variable_name: env
      variable_value: dev

  pools:
    - pool_name: limited_pool
      pool_slot: 5
```

### Export/Import

| Task | v2 | v1 |
|---|---|---|
| Export from the environment | `astro local env list` shows every value and its source (no export file) | `astro dev object export --connections` (writes `airflow_settings.yaml`; a `--settings-file` must already exist) |
| Import into the environment | no file import: set each value with `astro local env connection set` / `airflow-variable set` | `astro dev object import --connections --settings-file connections.yaml` |

---

## Validate Before Running

Parse DAGs to catch errors without starting the full environment:

```bash
astro local check     # v1: astro dev parse
```

---

## Related Skills

- **managing-astro-local-env**: Start, stop, and troubleshoot the local environment
- **authoring-dags**: Write and validate DAGs (uses MCP tools)
- **testing-dags**: Test DAGs (uses MCP tools)
- **deploying-airflow**: Deploy DAGs to production (Astro, Docker Compose, Kubernetes)
