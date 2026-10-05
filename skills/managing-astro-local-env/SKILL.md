---
name: managing-astro-local-env
description: Manage local Airflow environment with Astro CLI (standalone and Docker modes; `astro local` on Astro CLI v2, `astro dev` on v1). Use when the user wants to start, stop, or restart Airflow, view logs, query the Airflow API, troubleshoot, or fix environment issues. For project setup, see setting-up-astro-project.
---

# Astro Local Environment

This skill helps you manage your local Airflow environment using the Astro CLI.

> **To set up a new project**, see the **setting-up-astro-project** skill.
> **When Airflow is running**, use the **airflow**, **authoring-dags**, and **testing-dags** skills to query and test it.

## Astro CLI v1 or v2

Commands here are written for Astro CLI v2. Before anything else, run this as a command of its own, with nothing chained before or after it, and choose the dialect from what it prints: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI. Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is given beside it, marked `v1:`. If `af` is not on PATH, write `uvx --from astro-airflow-mcp af <args>` out in full in every command. Don't put it in a shell variable or alias: zsh won't split `$AF`, and shell state doesn't carry over between commands.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project: `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.
- If a command here, or in the project's `AGENTS.md`, disagrees with the installed CLI, trust the CLI: check `astro <cmd> --help` (v1: `af <cmd> --help` or `astro dev <cmd> --help`).

In this skill nearly every v1 form is an `astro dev` command. v2 replaced `astro dev` with `astro local`, and `astro dev <x>` on v2 fails and names its replacement.

## Modes

| | v2 (`astro local`) | v1 (`astro dev`) |
|---|---|---|
| Default | **Standalone**: Airflow runs on your machine in `.venv/`, managed by `uv` | **Docker**: Airflow runs in containers |
| Other mode | `astro local start --docker` | Standalone (Airflow 3 + `uv`, not on Windows): `astro dev start --standalone` |
| Making it stick | No setting: pass `--docker` on each start. `restart` keeps the mode Airflow is running in | `astro config set dev.mode standalone`, or pass `--standalone` on **every** command (stop, kill, restart, bash, logs, ...). `astro dev run` hands its arguments to Airflow, so it works in standalone mode only with `dev.mode` set |

Standalone state lives in `.venv/` and `.astro/standalone/` (database and logs) on both versions; DAGs come from `dags/`.

---

## Start / Stop / Restart

```bash
astro local start      # Start local Airflow                    v1: astro dev start
astro local stop       # Stop it (keeps its data and .venv)     v1: astro dev stop
astro local restart    # Restart, picking up project changes    v1: astro dev restart
astro local status     # Is it running, and where               v1: astro dev ps
astro local open       # Open the Airflow UI                    v1: no command (astro dev start opens it)
astro local list       # Every local Airflow on this machine    v1: no equivalent
```

| v2 | Purpose | v1 |
|------|-------------|----|
| `astro local start --port <n>` | Preferred API server port | `astro dev start --standalone --port <n>` (standalone only) |
| `astro local start --docker` | Run in Docker | the default |
| no equivalent | Run in the foreground | `astro dev start --standalone --foreground` |

**Restart after changing** the project's dependencies: `pyproject.toml` on v2; `requirements.txt`, `packages.txt`, or the `Dockerfile` on v1.

**Credentials:** a v1 Docker environment logs in with `admin` / `admin`.

---

## Reverse Proxy

Both versions give each project a hostname like `<project-name>.localhost:6563`, so several projects run side by side without port conflicts.

| Task | v2 | v1 |
|---|---|---|
| This project's URL | `astro local open --print` (or `astro local status`) | printed by `astro dev start` |
| All projects and their URLs | `astro local list` | `astro dev proxy status`, or visit `http://localhost:6563` |
| Stop the proxy | no command | `astro dev proxy stop` (it restarts on the next `astro dev start`) |
| Change the proxy port | no equivalent: v2 uses 6563, or another free port when that one is taken | `astro config set proxy.port <port>` |
| Skip the proxy for one start | no equivalent | `astro dev start --no-proxy` |

---

## View Logs

```bash
astro local logs                # All logs             v1: astro dev logs
astro local logs -f             # Follow in real time  v1: astro dev logs -f
astro local logs --tail 200     # Last 200 lines       v1: no equivalent
```

```bash
astro local logs --component scheduler    # One component    v1: astro dev logs --scheduler
```

Components are `scheduler`, `api-server`, `dag-processor`, and `triggerer` (`webserver` on Airflow 2); v2 also labels its own lines `system`. v2 filters by component in both modes. v1 takes a flag per component (`--scheduler`, `--api-server`, `--dag-processor`, `--triggerer`, `--webserver`), and in v1 standalone mode the log is one stream with no filtering.

---

## Run Airflow CLI Commands

```bash
astro local shell                     # Shell with the Airflow environment   v1: astro dev bash
astro local run airflow info          # Run one Airflow CLI command          v1: astro dev run info
astro local run airflow dags list     #                                      v1: astro dev run dags list
```

v2 `astro local run` runs any command, so name the `airflow` program. v1 `astro dev run` adds `airflow` itself, so leave it out. In v1 standalone mode, `bash` opens a venv-activated shell and `run` executes in the venv (`run` needs `dev.mode` set to `standalone`, see Modes).

---

## Querying the Airflow API

`astro api airflow` speaks Airflow's REST API by operation ID. Prefer operation IDs over URL paths. For everyday queries, the **airflow** skill's `astro local af` commands are simpler.

- **v2:** `astro api airflow` targets deployments, so for the local Airflow pass `--url <url>`, with the URL `astro local open --print` prints written into each command (a shell variable doesn't survive between separate tool calls). `astro local api <path>` also reaches it, by path rather than operation ID.
- **v1:** it defaults to the local Airflow (`localhost:8080`, `admin`/`admin`), so **drop `--url <url>`** from every command below. `--api-url <base>/api/v2`, `--username`, and `--password` change the target.

### Discovery

```bash
# List all endpoints
astro api airflow --url <url> ls

# Filter by keyword
astro api airflow --url <url> ls dags
astro api airflow --url <url> ls task

# Show params and schema for an operation
astro api airflow --url <url> describe get_dag
```

### Key Flags

| Flag | Purpose |
|------|---------|
| `-p key=value` | Path parameters |
| `-F key=value` | Body/query fields (auto-converts booleans/numbers) |
| `-q` / `--jq` | jq filter on response |
| `--paginate` | Fetch all pages |
| `-X` / `--method` | Override HTTP method |
| `--generate` | Output curl command instead of executing |

### DAGs

```bash
# List all DAGs
astro api airflow --url <url> get_dags

# Filter by pattern (SQL LIKE — use % wildcards)
astro api airflow --url <url> get_dags -F dag_id_pattern=%etl%

# Get a specific DAG
astro api airflow --url <url> get_dag -p dag_id=my_dag

# Get full details (schedule, params, etc.)
astro api airflow --url <url> get_dag_details -p dag_id=my_dag

# Pause / unpause
astro api airflow --url <url> patch_dag -p dag_id=my_dag -F is_paused=true
astro api airflow --url <url> patch_dag -p dag_id=my_dag -F is_paused=false

# View DAG source code
astro api airflow --url <url> get_dag_source -p dag_id=my_dag

# Check import errors
astro api airflow --url <url> get_import_errors
```

### DAG Runs

```bash
# List runs for a DAG
astro api airflow --url <url> get_dag_runs -p dag_id=my_dag

# Trigger a run
astro api airflow --url <url> trigger_dag_run -p dag_id=my_dag

# Trigger with config
astro api airflow --url <url> trigger_dag_run -p dag_id=my_dag -F conf[key]=value

# Get a specific run
astro api airflow --url <url> get_dag_run -p dag_id=my_dag -p dag_run_id=manual__2026-04-07

# Clear (re-run) a DAG run: preview with dry_run=true, then, once the user agrees, dry_run=false
astro api airflow --url <url> clear_dag_run -p dag_id=my_dag -p dag_run_id=manual__2026-04-07 -F dry_run=true
astro api airflow --url <url> clear_dag_run -p dag_id=my_dag -p dag_run_id=manual__2026-04-07 -F dry_run=false
```

### Task Instances

```bash
# List task instances for a run
astro api airflow --url <url> get_task_instances -p dag_id=my_dag -p dag_run_id=manual__2026-04-07

# Use ~ as wildcard (all DAGs or all runs); quote it, or bash expands it to your home directory
astro api airflow --url <url> get_task_instances -p dag_id=my_dag -p 'dag_run_id=~'

# Get a specific task instance
astro api airflow --url <url> get_task_instance -p dag_id=my_dag -p dag_run_id=manual__2026-04-07 -p task_id=extract

# Clear/retry failed tasks: preview with dry_run=true, then, once the user agrees, dry_run=false
astro api airflow --url <url> post_clear_task_instances -p dag_id=my_dag \
  -F dag_run_id=manual__2026-04-07 -F only_failed=true -F dry_run=true
astro api airflow --url <url> post_clear_task_instances -p dag_id=my_dag \
  -F dag_run_id=manual__2026-04-07 -F only_failed=true -F dry_run=false

# Get task logs
astro api airflow --url <url> get_log -p dag_id=my_dag -p dag_run_id=manual__2026-04-07 \
  -p task_id=extract -p try_number=1
```

### Config & Connections

```bash
astro api airflow --url <url> get_connections
astro api airflow --url <url> get_variables
astro api airflow --url <url> get_config
```

### Filtering with jq

```bash
# List only DAG IDs
astro api airflow --url <url> get_dags -q '.dags[].dag_id'

# Get failed task IDs from a run
astro api airflow --url <url> get_task_instances -p dag_id=my_dag -p 'dag_run_id=~' \
  -q '[.task_instances[] | select(.state=="failed") | .task_id]'
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8080 in use | v2: `astro local start --port <n>`. v1: `astro config set api-server.port <n>` (`webserver.port` on Airflow 2), or in standalone mode `astro dev start --standalone --port <n>` |
| Airflow won't start | Reset (below), then start again |
| Package install failed | Check the dependencies: `pyproject.toml` (v1: `requirements.txt` syntax) |
| DAG not appearing | `astro local check` (v1: `astro dev parse`) to check for import errors |
| Out of disk space (Docker) | `docker system prune` |
| Standalone won't start | Ensure `uv` is on PATH (v1: and that the runtime is 3.x) |
| Proxy port conflict | v1: `astro config set proxy.port <port>`. v2 moves to a free port by itself |
| `.venv` corrupted | Reset (below), then start again |

### Reset Environment

When things are broken. This **deletes the local Airflow's data** (its database, logs, and environment; the project itself is untouched), so get the user's go-ahead first:

```bash
astro local reset --yes     # v1: astro dev kill
astro local start           # v1: astro dev start
```

Without `--yes`, `astro local reset` asks for confirmation, and fails in a non-interactive shell.

---

## Upgrade Airflow

| Step | v2 | v1 |
|---|---|---|
| Test compatibility first | no equivalent: v2 has no `upgrade-test`. After upgrading, run `astro local check` and the tests | `astro dev upgrade-test` |
| Change the version | `astro local upgrade airflow [version]` moves the project's Airflow pin (`--with-otto` starts Otto afterwards to update DAGs and providers) | Edit the `FROM` line in the `Dockerfile`, for example `FROM quay.io/astronomer/astro-runtime:13.0.0` |
| Apply it | `astro local restart` if it is running, `astro local start` if not | `astro dev kill` (deletes local data; ask first), then `astro dev start` |

---

## Related Skills

- **setting-up-astro-project**: Initialize projects and configure dependencies
- **authoring-dags**: Write DAGs (requires running Airflow)
- **testing-dags**: Test DAGs (requires running Airflow)
- **deploying-airflow**: Deploy DAGs to production (Astro, Docker Compose, Kubernetes)
