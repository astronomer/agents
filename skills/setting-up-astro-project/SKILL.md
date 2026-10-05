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

<!-- astro-cli-version:start -->
## Astro CLI version

Commands in this skill, including its reference files, are written for Astro CLI v2. Before anything else, run this as a command of its own, with nothing chained before or after it, and choose the dialect from what it prints: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`
On Windows `cmd.exe`, which has no `/dev/null`, run `astro local af --help >NUL 2>&1 && echo v2 || echo v1` instead.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI. Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` and `--output json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is the line under it, starting `# v1:`. Where something behaves differently on v1, a line starting **v1:** says how. If `af` is not on PATH, write `uvx --from astro-airflow-mcp af <args>` out in full in every command. Don't put it in a shell variable or alias: zsh won't split `$AF`, and shell state doesn't carry over between commands.
- v2 replaced `astro dev` with `astro local`; `astro dev <cmd>` on v2 fails and names its replacement.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project, although the probe printed v2. Switch to the v1 forms: the standalone `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.
- `-d` and `-o` mean deployment and output in v2, but DAG id and offset in v1, so never carry either into a v1 command. `--dag-id`, `--offset`, `--state`, `--limit`, `--try`, `--map-index`, and `--timeout` mean the same in both.
- If a command here, or in the project's `AGENTS.md`, disagrees with the installed CLI, trust the CLI: check `astro <cmd> --help` (v1: `af <cmd> --help` or `astro dev <cmd> --help`).
<!-- astro-cli-version:end -->

A project is a `pyproject.toml` with a `[tool.astro]` table.

**v1:** a project is a `Dockerfile`, `requirements.txt`, `packages.txt`, and `airflow_settings.yaml`. Each section below gives that layout too.

---

## Initialize a New Project

```bash
astro init
# v1: astro dev init
```

> **Don't pass a version flag unless the user explicitly asks for a specific pin** (`--airflow-version`). Plain `astro init` resolves to the newest supported Airflow or Astro Runtime, which is the right default. Specifying a version risks pinning to a stale value from training data. If the user wants to know what was installed, read it afterward instead of guessing: the `apache-airflow` requirement in `pyproject.toml`.
>
> **v1:** `--runtime-version` is a pin flag too, and the installed version is on the `FROM` line of the `Dockerfile`.

**v2:** `astro init` in a directory that already holds a v1 project upgrades it in place (it moves `requirements.txt` and `packages.txt` into `pyproject.toml` and carries `airflow_settings.yaml` over), so run it there only when the user asks for that.

Creates this structure:

```
project/
├── dags/
├── include/
├── plugins/
├── tests/
├── pyproject.toml   # manifest
└── AGENTS.md
```

**v1:** the structure is this instead:

```
project/
├── dags/                 # DAG files
├── include/              # SQL, configs, supporting files
├── plugins/              # Custom Airflow plugins
├── tests/                # Unit tests
├── Dockerfile            # Image customization
├── packages.txt          # OS-level packages
├── requirements.txt      # Python packages
└── airflow_settings.yaml # Connections, variables, pools
```

---

## Adding Dependencies

### Python Packages

```bash
uv add apache-airflow-providers-snowflake
```

`uv add` writes the requirement into `pyproject.toml`, keeps the `[tool.uv]` pins that hold Airflow to the build a deployment runs, and installs the package into the project's `.venv`, where a running standalone Airflow can import it. Restart anyway for what a provider registers at startup (connection types, plugins); in Docker mode the restart is what puts the package in the image.

**v1:** add the line to `requirements.txt` instead, which takes pip requirement lines:

```
apache-airflow-providers-snowflake==5.3.0
pandas==2.1.0
requests>=2.28.0
```

### OS Packages

List them in `pyproject.toml`, as a key under the `[tool.astro]` table `astro init` already wrote (a second `[tool.astro]` header breaks the file):

```toml
# under the existing [tool.astro]
packages = ["gcc", "libpq-dev"]
```

**v1:** list them in `packages.txt`, one per line.

On v2 only Docker mode (`astro local start --docker`) can install OS packages; standalone mode warns and runs without them.

### Custom Dockerfile

For complex setups (private PyPI, custom scripts). The project uses one only when the manifest names it (a key under the existing `[tool.astro]` table), only in Docker mode, and its `FROM` must name the same Airflow series as the manifest's pin:

```toml
# under the existing [tool.astro]
dockerfile = "Dockerfile"
```

```dockerfile
FROM quay.io/astronomer/astro-runtime:12.4.0

RUN pip install --extra-index-url https://pypi.example.com/simple my-package
```

**v1:** the project always builds from its `Dockerfile`.

**After modifying dependencies:** run

```bash
astro local restart
# v1: astro dev restart
```

---

## Configuring Connections, Variables & Pools

### `astro local env` and `[tool.astro.pools]`

v2 reads `airflow_settings.yaml` nowhere. Set connections and Airflow variables with `astro local env` (stored encrypted unless you pass `--plain`, which writes the project's `.env`):

```bash
# pipe the password in (a --password flag lands in shell history)
astro local env connection set my_postgres --type postgres --host localhost --port 5432 --login user --schema mydb
# v1: none (airflow_settings.yaml, below)
astro local env airflow-variable set env --value dev
# v1: none (airflow_settings.yaml, below)
astro local env list        # every declared value and where it resolves from
# v1: none
```

Pools are declared in `pyproject.toml`, and `astro local start` creates or updates them:

```toml
[tool.astro.pools.limited_pool]
slots = 5
```

### v1: `airflow_settings.yaml`

**v1:** connections, variables and pools go in `airflow_settings.yaml`, loaded automatically on environment start:

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

- **Export from the environment:** there is no export file; `astro local env list` shows every value and its source.
- **Import into the environment:** there is no file import; set each value with `astro local env connection set` / `airflow-variable set`.

```bash
astro local env list
# v1: astro dev object export --connections
astro local env connection set <conn_id> --type <type> ...
# v1: astro dev object import --connections --settings-file connections.yaml
```

**v1:** the export writes `airflow_settings.yaml` (a `--settings-file` must already exist), and the import reads the settings file it names.

---

## Validate Before Running

Parse DAGs to catch errors without starting the full environment:

```bash
astro local check
# v1: astro dev parse
```

---

## Related Skills

- **managing-astro-local-env**: Start, stop, and troubleshoot the local environment
- **authoring-dags**: Write and validate DAGs (uses MCP tools)
- **testing-dags**: Test DAGs (uses MCP tools)
- **deploying-airflow**: Deploy DAGs to production (Astro, Docker Compose, Kubernetes)
