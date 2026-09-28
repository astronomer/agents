---
name: airflow
description: Queries, manages, and troubleshoots Apache Airflow using the Astro CLI (`astro local af`, `astro af`). Use when working with anything related to Airflow - a DAG, a DAG run, a task log, an import or parse error, a broken DAG, or any Airflow operation. Covers listing and triggering DAGs, retrying runs, reading task logs, diagnosing failures, debugging import and parse errors, checking connections, variables and pools, exploring the REST API, and monitoring health (for example "trigger a pipeline", "retry a run", "list connections", "check Airflow health", "why did my DAG fail"). This is the entrypoint that routes to sibling skills for authoring, testing, deploying, and migrating Airflow 2 to 3. Not for warehouse/SQL analytics on Airflow metadata tables (use analyzing-data); for deep root-cause reports use debugging-dags or airflow-investigation.
---

# Airflow Operations

Use `astro local af` (this project's Airflow) and `astro af` (a deployment) to query, manage, and troubleshoot Airflow workflows.

## Astro CLI

The [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview) is the recommended way to run Airflow locally and deploy to production. It provides a containerized Airflow environment that works out of the box:

```bash
# Initialize a new project
astro dev init

# Start local Airflow (webserver at http://localhost:8080)
astro dev start

# Parse DAGs to catch errors quickly (no need to start Airflow)
astro dev parse

# Run pytest against your DAGs
astro dev pytest

# Deploy to production
astro deploy            # Full deploy (image + DAGs)
astro deploy --dags     # DAG-only deploy (fast, no image build)
```

For more details:
- **New project?** See the **setting-up-astro-project** skill
- **Local environment?** See the **managing-astro-local-env** skill
- **Deploying?** See the **deploying-airflow** skill

---

## Running the CLI

These commands use the [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview). One command tree, `af` (alias `airflow`), reaches three kinds of Airflow:

| Target | Spelling |
|---|---|
| This project's local Airflow | `astro local af <cmd>` |
| A deployment the project links | `astro af <cmd> -d <link>` |
| Any other Airflow, by URL | `astro af <cmd> --url <url>` |

The examples below use `astro local af`. To run any of them against a deployment, swap `astro local af` for `astro af` and add `-d <link>`.

## Choosing Which Airflow

```bash
# See which deployments the project links, and pin the one bare `astro af` uses
astro use
astro use prod

# Link a deployment the project doesn't know yet
astro link add

# Act on one deployment for a single command
astro af dags list -d staging

# Reach an Airflow no project declares
ASTRO_AIRFLOW_TOKEN="$TOKEN" astro af dags list --url https://airflow.example.com
# Or username/password:
ASTRO_AIRFLOW_USERNAME=admin ASTRO_AIRFLOW_PASSWORD=admin astro af dags list --url http://localhost:8080
```

A bare `astro af <cmd>` resolves its deployment as `-d` > `ASTRO_DEPLOYMENT` > the `astro use` pin > the manifest's default link, and errors naming the options when none applies. It never falls back to the local Airflow: that one is always `astro local af`.

Two short flags differ from the standalone `af` CLI: `-d` is **deployment** and `-o` is **output**. Pass a DAG id positionally (or with `--dag-id`), and an offset with `--offset`.

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
| `astro local af runs list [dag_id]` | List DAG runs |
| `astro local af runs get <dag_id> <run_id>` | Get run details |
| `astro local af runs trigger <dag_id>` | Trigger a DAG run |
| `astro local af runs trigger-wait <dag_id>` | Trigger and wait for completion |
| `astro local af runs delete <dag_id> <run_id>` | Permanently delete a DAG run |
| `astro local af runs clear <dag_id> <run_id>` | Clear a run for re-execution (`--dry-run` to preview) |
| `astro local af runs diagnose <dag_id> <run_id>` | Diagnose failed run |
| `astro local af tasks list <dag_id>` | List tasks in DAG |
| `astro local af tasks get <dag_id> <task_id>` | Get task definition |
| `astro local af tasks instance <dag_id> <run_id> <task_id>` | Get task instance |
| `astro local af tasks logs <dag_id> <run_id> <task_id>` | Get task logs |
| `astro local af tasks clear <dag_id> <run_id> <task_id>...` | Clear task instances (`--dry-run` to preview) |
| `astro local af version` | Airflow version |
| `astro local af config` | Full configuration (needs `expose_config` on) |
| `astro local af connections list` | List connections (no passwords) |
| `astro local af connections get <conn_id>` | Get one connection |
| `astro local af variables list` | List variable keys (no values) |
| `astro local af variables get <key>` | Get specific variable and its value |
| `astro local af pools list` | List pools |
| `astro local af pools get <name>` | Get pool details |
| `astro local af plugins` | List plugins |
| `astro local af providers` | List installed providers |
| `astro local af assets list` | List assets/datasets |
| `astro local af assets events` | List asset updates and the runs they started |
| `astro local api <endpoint>` | Direct REST API access (`astro api airflow <endpoint> -d <link>` for a deployment) |
| `astro local api ls` | List available API endpoints |
| `astro local api ls --filter X` | List endpoints matching pattern |
| `af registry providers` | List providers in the Airflow Registry (standalone `af` only, see below) |
| `af registry modules <provider>` | List operators/hooks/sensors/transfers in a provider |
| `af registry parameters <provider>` | Constructor signatures (name, type, default, required) for a provider's classes |
| `af registry connections <provider>` | Connection types a provider exposes |

`runs delete`, `runs clear`, and `tasks clear` ask for confirmation, and fail in a non-interactive shell unless you pass `--yes`. Get the user's go-ahead first, then pass `--yes`.

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
- "Delete this run" / "Remove stuck run" -> `astro local af runs delete <dag_id> <run_id>`
- "Clear this run" / "Retry this run" / "Re-run this" -> `astro local af runs clear <dag_id> <run_id> --dry-run` to preview, then again with `--yes` instead of `--dry-run`
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
- "What version of Airflow?" -> `astro local af version`
- "What connections exist?" -> `astro local af connections list`
- "Are pools full?" -> `astro local af pools list`
- "Is Airflow healthy?" -> `astro local af health`

### API Exploration
- "What API endpoints are available?" -> `astro local api ls`
- "Find variable endpoints" -> `astro local api ls --filter variable`
- "Access XCom values" / "Get XCom" -> `astro local api xcom-entries -F dag_id=X -F task_id=Y`
- "Get event logs" / "Audit trail" -> `astro local api event-logs -F dag_id=X`
- "Create connection via API" -> `astro local api connections -X POST --body '{...}'`
- "Create variable via API" -> `astro local api variables -X POST -F key=name --raw-field value=val`

### Registry Discovery

The Astro CLI has no registry command, so these use the standalone `af` CLI (`uvx --from astro-airflow-mcp af registry ...` if `af` is not on PATH). They read the public Airflow Registry, not your Airflow, so no project or deployment is involved.

- "What operators does provider X have?" -> `af registry modules <provider>`
- "What are the constructor params for operator Y?" -> `af registry parameters <provider>`
- "What providers exist?" / "Is there a provider for Z?" -> `af registry providers`
- "What connection types does provider X expose?" -> `af registry connections <provider>`
- "Writing a DAG with a specific operator" -> use registry to verify current signature before copying examples

## Common Workflows

### Validate DAGs Before Deploying

If you're using the Astro CLI, you can validate DAGs without a running Airflow instance:

```bash
# Parse DAGs to catch import errors and syntax issues
astro dev parse

# Run unit tests
astro dev pytest
```

Otherwise, validate against a running instance:

```bash
astro local af dags errors     # Check for parse/import errors
astro local af dags warnings   # Check for deprecation warnings
```

### Discover Operator Signatures Before Writing Code

The Airflow Registry at `airflow.apache.org/registry` is the authoritative source for provider classes and their current constructor signatures. Prefer it over memory or stale documentation when authoring DAGs — the registry reflects the live provider release. The Astro CLI has no registry command; these use the standalone `af` CLI, whose output is a single JSON object (not NDJSON rows).

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
# 1. List recent runs to find failure
astro local af runs list my_dag

# 2. Diagnose the specific run
astro local af runs diagnose my_dag manual__2024-01-15T10:00:00+00:00

# 3. Get logs for failed task (from diagnose output)
astro local af tasks logs my_dag manual__2024-01-15T10:00:00+00:00 extract_data

# 4. After fixing, preview what clearing the run resets, then clear it to retry all tasks
astro local af runs clear my_dag manual__2024-01-15T10:00:00+00:00 --dry-run
astro local af runs clear my_dag manual__2024-01-15T10:00:00+00:00 --yes
```

### Morning Health Check

```bash
# 1. Overall system health
astro local af health

# 2. Check for broken DAGs
astro local af dags errors

# 3. Check pool utilization
astro local af pools list
```

### Understand a DAG

```bash
# Get comprehensive overview (metadata + tasks + source)
astro local af dags explore my_dag
```

### Check Why DAG Isn't Running

```bash
# Check if paused
astro local af dags get my_dag

# Check for import errors
astro local af dags errors

# Check recent runs
astro local af runs list my_dag
```

### Trigger and Monitor

```bash
# Option 1: Trigger and wait (blocking)
# Exit 0: run succeeded. 1: run failed (failed tasks are in the output). 2: timed out, run still going.
astro local af runs trigger-wait my_dag --timeout 1800

# Option 2: Trigger and check later
astro local af runs trigger my_dag
astro local af runs get my_dag <run_id>
```

## Output Format

Commands print a human-readable table by default. Pass `-o json` whenever you parse the output. A list prints NDJSON: one JSON object per line, with no `{total, items}` wrapper, and an empty list prints nothing:

```bash
astro local af dags list -o json
# {"dag_id":"example_dag","is_paused":false,"schedule":"@daily","owners":["airflow"],"tags":["demo"],...}
# {"dag_id":"other_dag",...}
```

Rows carry a curated set of fields (for example `schedule`, not `timetable_summary`, and `tags` as plain strings). A failure prints `{"error": ..., "code": ...}` and exits non-zero.

Use `jq -s` to collect the rows, or filter them one at a time:

```bash
# Find failed runs
astro local af runs list -o json | jq -s '.[] | select(.state == "failed")'

# Get DAG IDs only
astro local af dags list -o json | jq -r '.dag_id'

# Find paused DAGs
astro local af dags list -o json | jq -s '[.[] | select(.is_paused == true)]'
```

## Task Logs Options

```bash
# Get logs for specific retry attempt
astro local af tasks logs my_dag run_id task_id --try 2

# Get logs for mapped task index
astro local af tasks logs my_dag run_id task_id --map-index 5
```

## Direct API Access with `astro local api`

Use `astro local api` for endpoints not covered by high-level commands (XCom, event-logs, backfills, etc). For a deployment, `astro api airflow <endpoint> -d <link>` is the same idea.

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

**Field syntax**: `-F key=value` auto-converts types, `--raw-field key=value` keeps as string. A non-2xx response fails the command, so a script can branch on the exit code.

**Full reference**: See [api-reference.md](api-reference.md) for all options, common endpoints (XCom, event-logs, backfills), and examples.

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
