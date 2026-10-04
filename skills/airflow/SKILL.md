---
name: airflow
description: Queries, manages, and troubleshoots Apache Airflow using the Astro CLI (`astro local af`, `astro af`) or, on Astro CLI v1, the standalone `af` CLI. Use when working with anything related to Airflow - a DAG, a DAG run, a task log, an import or parse error, a broken DAG, or any Airflow operation. Covers listing and triggering DAGs, retrying runs, reading task logs, diagnosing failures, debugging import and parse errors, checking connections, variables and pools, exploring the REST API, and monitoring health (for example "trigger a pipeline", "retry a run", "list connections", "check Airflow health", "why did my DAG fail"). This is the entrypoint that routes to sibling skills for authoring, testing, deploying, and migrating Airflow 2 to 3. Not for warehouse/SQL analytics on Airflow metadata tables (use analyzing-data); for deep root-cause reports use debugging-dags or airflow-investigation.
---

# Airflow Operations

Query, manage, and troubleshoot Airflow from the command line.

## Astro CLI v1 or v2

Commands here are written for Astro CLI v2. Run `astro local af --help` once: it succeeds only on v2.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI (`uvx --from astro-airflow-mcp af` if `af` is not on PATH). Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is given beside it, marked `v1:`.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project: `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.

## Astro CLI

The [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview) is the recommended way to run Airflow locally and deploy to production:

```bash
astro init              # Initialize a new project              v1: astro dev init
astro local start       # Start local Airflow                   v1: astro dev start
astro local check       # Parse DAGs without starting Airflow   v1: astro dev parse
uv run pytest           # Run the project's tests               v1: astro dev pytest
astro deploy            # Full deploy (image + DAGs)
astro deploy --dags     # DAG-only deploy (fast, no image build)
```

For more details:
- **New project?** See the **setting-up-astro-project** skill
- **Local environment?** See the **managing-astro-local-env** skill
- **Deploying?** See the **deploying-airflow** skill

---

## Choosing Which Airflow

| Target | v2 | v1 |
|---|---|---|
| This project's local Airflow | `astro local af <cmd>` | `af <cmd>` |
| A deployment | `astro af <cmd> -d <link>` | `af instance use <name>`, then `af <cmd>` |
| Any Airflow, by URL | `ASTRO_AIRFLOW_TOKEN=<token> astro af <cmd> --url <url>` | `AIRFLOW_API_URL=<url> AIRFLOW_AUTH_TOKEN=<token> af <cmd>` |

The examples below use the local form. For a deployment on v2, swap `astro local af` for `astro af` and add `-d <link>`.

**v2.** `astro af` never falls back to the local Airflow; that one is always `astro local af`.

```bash
# See which deployments the project links, and pin the one bare `astro af` uses
astro use
astro use prod

# Link a deployment the project doesn't know yet. This writes the link into the
# project's committed pyproject.toml, so get the user's go-ahead first. Bare
# `astro link add` asks which deployment, but only in a terminal; a script names it.
astro link add prod --deployment <deployment-id>

# Reach an Airflow no project declares (or ASTRO_AIRFLOW_USERNAME + ASTRO_AIRFLOW_PASSWORD)
ASTRO_AIRFLOW_TOKEN="$TOKEN" astro af dags list --url https://airflow.example.com
```

A bare `astro af <cmd>` resolves its deployment as `-d` > `ASTRO_DEPLOYMENT` > the `astro use` pin > the manifest's default link, and errors naming the options when none applies.

**v1.** `af` acts on its *current instance*: the local Airflow at `http://localhost:8080` (instance `localhost:8080`) until `af instance use` picks another, so check `af instance current` before acting. For a one-off query against another Airflow, prefer the environment variables below, which change nothing.

```bash
af instance list
af instance current

# --local keeps it out of the committed .astro/config.yaml. The single quotes store the
# literal ${API_TOKEN}, which af reads from the environment each time, not the token itself.
af instance add prod --url https://airflow.example.com --token '${API_TOKEN}' --local

# `use` persists: every later `af` command, in any skill, hits prod until you switch back.
# The built-in localhost:8080 instance can vanish once another instance is configured,
# so register the local Airflow under a name before switching away from it.
af instance add local --url http://localhost:8080 --local
af instance use prod
af instance use local

# Preview discoverable Astro deployments and local Airflows. Without --dry-run,
# discover creates API tokens in Astro, so get the user's go-ahead first.
af instance discover --dry-run

# One command against another Airflow (or AIRFLOW_USERNAME + AIRFLOW_PASSWORD)
AIRFLOW_API_URL=https://airflow.example.com AIRFLOW_AUTH_TOKEN="$TOKEN" af dags list
```

Instances live in the project's `.astro/config.yaml` (committed) and `.astro/config.local.yaml` (gitignored), and in `~/.astro/config.yaml`. Inside a project, `add` writes the committed file unless you pass `--local` or `--global`; `use` writes the gitignored one.

**Use long flags.** `-d` and `-o` mean deployment and output in v2, but DAG id and offset in v1. `--dag-id`, `--offset`, `--limit`, `--state`, and `--timeout` mean the same in both.

## Quick Reference

| Command | Description |
|---------|-------------|
| `astro local af health` | System health check |
| `astro local af dags list` | List all DAGs |
| `astro local af dags get <dag_id>` | Get DAG details |
| `astro local af dags explore <dag_id>` | Full DAG investigation |
| `astro local af dags source <dag_id>` | Get DAG source code |
| `astro local af dags pause <dag_id>` | Pause DAG scheduling |
| `astro local af dags unpause <dag_id>` | Resume DAG scheduling |
| `astro local af dags errors` | List import errors |
| `astro local af dags warnings` | List DAG warnings |
| `astro local af dags stats` | DAG run statistics |
| `astro local af runs list --dag-id <dag_id>` | List DAG runs |
| `astro local af runs get <dag_id> <run_id>` | Get run details |
| `astro local af runs trigger <dag_id>` | Trigger a DAG run |
| `astro local af runs trigger-wait <dag_id>` | Trigger and wait for completion |
| `astro local af runs delete <dag_id> <run_id>` | Permanently delete a DAG run (see "Clearing and deleting") |
| `astro local af runs clear <dag_id> <run_id>` | Clear a run for re-execution (see "Clearing and deleting") |
| `astro local af runs diagnose <dag_id> <run_id>` | Diagnose failed run |
| `astro local af tasks list <dag_id>` | List tasks in DAG |
| `astro local af tasks get <dag_id> <task_id>` | Get task definition |
| `astro local af tasks instance <dag_id> <run_id> <task_id>` | Get task instance |
| `astro local af tasks logs <dag_id> <run_id> <task_id>` | Get task logs |
| `astro local af tasks clear <dag_id> <run_id> <task_id>...` | Clear task instances (differs in v1, see "Clearing and deleting") |
| `astro local af version` | Airflow version (v1: `af config version`) |
| `astro local af config` | Full configuration, if Airflow exposes it (v1: `af config show`) |
| `astro local af connections list` | List connections, no passwords (v1: `af config connections`) |
| `astro local af connections get <conn_id>` | Get one connection (v1: find it in `af config connections`) |
| `astro local af variables list` | List variables; v2 shows keys only (v1: `af config variables`) |
| `astro local af variables get <key>` | Get one variable and its value (v1: `af config variable <key>`) |
| `astro local af pools list` | List pools (v1: `af config pools`) |
| `astro local af pools get <name>` | Get pool details (v1: `af config pool <name>`) |
| `astro local af plugins` | List plugins (v1: `af config plugins`) |
| `astro local af providers` | List installed providers (v1: `af config providers`) |
| `astro local af assets list` | List assets/datasets |
| `astro local af assets events` | List asset updates and the runs they started |
| `astro local api <endpoint>` | Direct REST API access (see "Direct API Access") |
| `astro local api ls` | List available API endpoints |
| `astro local api ls --filter X` | List endpoints matching pattern |
| `af registry providers` | List providers in the Airflow Registry (standalone `af` on both versions, see below) |
| `af registry modules <provider>` | List operators/hooks/sensors/transfers in a provider |
| `af registry parameters <provider>` | Constructor signatures (name, type, default, required) for a provider's classes |
| `af registry connections <provider>` | Connection types a provider exposes |

### Clearing and deleting

Get the user's go-ahead before any of these, and preview first where you can:

| Action | v2 | v1 |
|---|---|---|
| Delete a run | `astro local af runs delete <dag_id> <run_id> --yes` | `af runs delete <dag_id> <run_id> --yes` |
| Clear a run | `astro local af runs clear <dag_id> <run_id> --dry-run`, then `--yes` instead of `--dry-run` | `af runs clear <dag_id> <run_id> --dry-run`, then `--yes` instead of `--dry-run` |
| Clear tasks | `astro local af tasks clear <dag_id> <run_id> <id> <id> --dry-run`, then `--yes` instead of `--dry-run` | `af tasks clear <dag_id> <run_id> <id>,<id> --dry-run`, then `--no-dry-run` instead of `--dry-run` |

`runs delete` and `runs clear` prompt on both versions, and fail in a non-interactive shell without `--yes`. `tasks clear` differs: v2 clears unless `--dry-run` and prompts unless `--yes`; v1 only previews unless `--no-dry-run`, never prompts, takes comma-separated task ids, and has no `--yes`.

## User Intent Patterns

### Getting Started
- "How do I run Airflow locally?" / "Set up Airflow" -> use the **managing-astro-local-env** skill (uses Astro CLI)
- "Create a new Airflow project" / "Initialize project" -> use the **setting-up-astro-project** skill (uses Astro CLI)
- "How do I install Airflow?" / "Get started with Airflow" -> use the **setting-up-astro-project** skill

### DAG Operations
- "What DAGs exist?" / "List all DAGs" -> `astro local af dags list`
- "Tell me about DAG X" / "What is DAG Y?" -> `astro local af dags explore <dag_id>`
- "What's the schedule for DAG X?" -> `astro local af dags get <dag_id>`
- "Show me the code for DAG X" -> `astro local af dags source <dag_id>`
- "Stop DAG X" / "Pause this workflow" -> `astro local af dags pause <dag_id>`
- "Resume DAG X" -> `astro local af dags unpause <dag_id>`
- "Are there any DAG errors?" -> `astro local af dags errors`
- "Create a new DAG" / "Write a pipeline" -> use the **authoring-dags** skill

### Run Operations
- "What runs have executed?" -> `astro local af runs list`
- "Run DAG X" / "Trigger the pipeline" -> `astro local af runs trigger <dag_id>`
- "Run DAG X and wait" -> `astro local af runs trigger-wait <dag_id>`
- "Why did this run fail?" -> `astro local af runs diagnose <dag_id> <run_id>`
- "Delete this run" / "Remove stuck run" / "Clear this run" / "Retry this run" / "Re-run this" -> see "Clearing and deleting" above
- "Test this DAG and fix if it fails" -> use the **testing-dags** skill

### Task Operations
- "What tasks are in DAG X?" -> `astro local af tasks list <dag_id>`
- "Get task logs" / "Why did task fail?" -> `astro local af tasks logs <dag_id> <run_id> <task_id>`
- "Full root cause analysis" / "Diagnose and fix" -> use the **debugging-dags** skill

### Data Operations
- "Is the data fresh?" / "When was this table last updated?" -> use the **checking-freshness** skill
- "Where does this data come from?" -> use the **tracing-upstream-lineage** skill
- "What depends on this table?" / "What breaks if I change this?" -> use the **tracing-downstream-lineage** skill

### Deployment Operations
- "Deploy my DAGs" / "Push to production" -> use the **deploying-airflow** skill
- "Set up CI/CD" / "Automate deploys" -> use the **deploying-airflow** skill
- "Deploy to Kubernetes" / "Set up Helm" -> use the **deploying-airflow** skill
- "astro deploy" / "DAG-only deploy" -> use the **deploying-airflow** skill

### System Operations
- "What version of Airflow?" -> `astro local af version` (v1: `af config version`)
- "What connections exist?" -> `astro local af connections list` (v1: `af config connections`)
- "Are pools full?" -> `astro local af pools list` (v1: `af config pools`)
- "Is Airflow healthy?" -> `astro local af health`

### API Exploration
- "What API endpoints are available?" -> `astro local api ls`
- "Find variable endpoints" -> `astro local api ls --filter variable`
- "Access XCom values" / "Get XCom" -> `astro local api dags/<dag_id>/dagRuns/<run_id>/taskInstances/<task_id>/xcomEntries` (`astro local api ls --filter xcom` lists the XCom paths; v1 `af api ls` prints them with the `/api/v2` prefix, which you drop when calling `af api`)
- "Get event logs" / "Audit trail" -> `astro local api eventLogs -F dag_id=X`
- "Create connection via API" -> `astro local api connections -X POST --body '{...}'`
- "Create variable via API" -> `astro local api variables -X POST -F key=name --raw-field value=val`

### Registry Discovery

These use the standalone `af` CLI on both versions (`uvx --from astro-airflow-mcp af registry ...` if `af` is not on PATH). They read the public Airflow Registry, not your Airflow, so no project or deployment is involved.

- "What operators does provider X have?" -> `af registry modules <provider>`
- "What are the constructor params for operator Y?" -> `af registry parameters <provider>`
- "What providers exist?" / "Is there a provider for Z?" -> `af registry providers`
- "What connection types does provider X expose?" -> `af registry connections <provider>`
- "Writing a DAG with a specific operator" -> use registry to verify current signature before copying examples

## Common Workflows

### Validate DAGs Before Deploying

Without a running Airflow:

```bash
astro local check     # Parse DAGs: import errors, syntax issues   v1: astro dev parse
uv run pytest         # Run the project's tests                    v1: astro dev pytest
```

Against a running Airflow:

```bash
astro local af dags errors     # Check for parse/import errors
astro local af dags warnings   # Check for deprecation warnings
```

### Discover Operator Signatures Before Writing Code

The Airflow Registry at `airflow.apache.org/registry` is the authoritative source for provider classes and their current constructor signatures. Prefer it over memory or stale documentation when authoring DAGs — the registry reflects the live provider release. `af registry` is the same on both versions and prints one JSON object.

```bash
# List all providers and pick the one you need
af registry providers | jq '.providers[] | {id, name, version}'

# List every operator / hook / sensor in a provider (e.g. standard, amazon, google)
af registry modules standard \
  | jq '.modules[] | {name, type, import_path, docs_url}'

# Get the current constructor signature for a specific class
af registry parameters standard \
  | jq '.classes["airflow.providers.standard.operators.hitl.ApprovalOperator"].parameters'

# Filter modules by substring (useful when you know the concept but not the class)
af registry modules standard \
  | jq '.modules[] | select(.import_path | test("hitl"))'
```

Results are cached locally: 1 hour for the latest version, 30 days for pinned versions (which are immutable). Add `--version X.Y.Z` to any `modules` / `parameters` / `connections` call to target a specific release.

### Investigate a Failed Run

```bash
# 1. Find the failed run
astro local af runs list --dag-id my_dag --state failed

# 2. Diagnose the specific run
astro local af runs diagnose my_dag manual__2024-01-15T10:00:00+00:00

# 3. Get logs for failed task (from diagnose output)
astro local af tasks logs my_dag manual__2024-01-15T10:00:00+00:00 extract_data

# 4. After fixing, preview what clearing the run resets, then, once the user agrees, clear it
astro local af runs clear my_dag manual__2024-01-15T10:00:00+00:00 --dry-run
astro local af runs clear my_dag manual__2024-01-15T10:00:00+00:00 --yes
```

### Morning Health Check

```bash
astro local af health         # 1. Overall system health
astro local af dags errors    # 2. Check for broken DAGs
astro local af pools list     # 3. Check pool utilization   v1: af config pools
```

### Understand a DAG

```bash
# Get comprehensive overview (metadata + tasks + source)
astro local af dags explore my_dag
```

### Check Why DAG Isn't Running

```bash
astro local af dags get my_dag              # Is it paused?
astro local af dags errors                  # Import errors?
astro local af runs list --dag-id my_dag    # Recent runs
```

### Trigger and Monitor

```bash
# Option 1: Trigger and wait (blocking). The testing-dags skill explains reading the result.
astro local af runs trigger-wait my_dag --timeout 1800

# Option 2: Trigger and check later
astro local af runs trigger my_dag
astro local af runs get my_dag <run_id>
```

## Output Format

**v2** prints a table by default. Pass `-o json` whenever you parse the output: a list prints NDJSON, one JSON object per line with no wrapper, and an empty list prints nothing. Rows carry a curated set of fields (for example `schedule`, not `timetable_summary`, and `tags` as plain strings). A list returns one page, 100 rows by default, and with `-o json` it is cut at the cap with no sign that it was, so filter (`--dag-id`, `--state`) or pass `--limit <n>` when you need more.

**v1** always prints JSON, and wraps a list in an object with its count: `{"total_dags": 5, "returned_count": 5, "dags": [...]}` (the key is `dag_runs`, `pools`, `variables`, ... for other lists).

So a `jq` filter needs the form for your version:

```bash
# DAG ids
astro local af dags list -o json | jq -r '.dag_id'
# v1: af dags list | jq -r '.dags[].dag_id'

# Paused DAGs, as one array
astro local af dags list --paused -o json | jq -s '.'
# v1: af dags list --paused | jq '.dags'
```

## Task Logs Options

```bash
# Get logs for specific retry attempt
astro local af tasks logs my_dag run_id task_id --try 2

# Get logs for mapped task index
astro local af tasks logs my_dag run_id task_id --map-index 5
```

## Direct API Access with `astro local api`

Use `astro local api` (v1: `af api`) for endpoints not covered by high-level commands (XCom, event logs, backfills, etc).

```bash
# Discover available endpoints
astro local api ls
astro local api ls --filter variable

# Basic usage
astro local api dags
astro local api dags -F limit=10 -F only_active=true
astro local api variables -X POST -F key=my_var --raw-field value="my value"
astro local api variables/old_var -X DELETE
```

**Field syntax**: `-F key=value` auto-converts types, `--raw-field key=value` keeps as string.

**Full reference**: See [api-reference.md](api-reference.md) for all options, deployments, common endpoints (XCom, event logs, backfills), and examples.

## Related Skills

| Skill | Use when... |
|-------|-------------|
| **authoring-dags** | Creating or editing DAG files with best practices |
| **testing-dags** | Iterative test -> debug -> fix -> retest cycles |
| **debugging-dags** | Deep root cause analysis and failure diagnosis |
| **checking-freshness** | Checking if data is up to date or stale |
| **tracing-upstream-lineage** | Finding where data comes from |
| **tracing-downstream-lineage** | Impact analysis -- what breaks if something changes |
| **deploying-airflow** | Deploying DAGs to production (Astro, Docker Compose, Kubernetes) |
| **migrating-airflow-2-to-3** | Upgrading DAGs from Airflow 2.x to 3.x |
| **managing-astro-local-env** | Starting, stopping, or troubleshooting local Airflow |
| **setting-up-astro-project** | Initializing a new Astro/Airflow project |
| **airflow-state-store** | Per-task checkpointing, watermarks, crash-safe operators (Airflow 3.3+) |
| **airflow-hitl** | Pausing a DAG for human approval or input (Airflow 3.1+) |
