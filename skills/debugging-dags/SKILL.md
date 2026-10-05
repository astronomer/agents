---
name: debugging-dags
description: Comprehensive DAG failure diagnosis and root-cause analysis  with structured investigation and prevention recommendations. Use when deep failure investigation is needed, a DAG fails to import/parse or 'airflow dags list' errors on a file; a task or run is failing and must be diagnosed and fixed; requests like 'why did X fail', 'my dag keeps failing — find and fix it', or fixing a broken DAG so it loads cleanly. For simple 'why did it fail / show logs', the airflow skill handles it directly.
---

# DAG Diagnosis

You are a data engineer debugging a failed Airflow DAG. Follow this systematic approach to identify the root cause and provide actionable remediation.

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

To debug a deployment instead of the local Airflow, see "Choosing Which Airflow" in the **airflow** skill.

---

## Step 1: Identify the Failure

If a specific DAG was mentioned:
- Run `astro local af runs diagnose <dag_id> <dag_run_id>` (if run_id is provided)
- If no run_id specified, run `astro local af dags stats` to find recent failures

If no DAG was specified:
- Run `astro local af health` to find recent failures across all DAGs
- Check for import errors with `astro local af dags errors`
- Show DAGs with recent failures
- Ask which DAG to investigate further

## Step 2: Get the Error Details

Once you have identified a failed task:

1. **Get task logs** using `astro local af tasks logs <dag_id> <dag_run_id> <task_id>`
2. **Look for the actual exception** - scroll past the Airflow boilerplate to find the real error
3. **Categorize the failure type**:
   - **Data issue**: Missing data, schema change, null values, constraint violation
   - **Code issue**: Bug, syntax error, import failure, type error
   - **Infrastructure issue**: Connection timeout, resource exhaustion, permission denied
   - **Dependency issue**: Upstream failure, external API down, rate limiting

## Step 3: Check Context

Gather additional context to understand WHY this happened:

1. **Recent changes**: Was there a code deploy? Check git history if available
2. **Package version changes**: Was a package upgraded — in the image, in a venv-style operator, or at the index? See [Package version changes](#package-version-changes) below.
3. **Data volume**: Did data volume spike? Run a quick count on source tables
4. **Upstream health**: Did upstream tasks succeed but produce unexpected data?
5. **Historical pattern**: Is this a recurring failure? Check if same task failed before
6. **Timing**: Did this fail at an unusual time? (resource contention, maintenance windows)

Use `astro local af runs get <dag_id> <dag_run_id>` to compare the failed run against recent successful runs.

### Package version changes

A common cause of failures with no git activity is dependency drift — the user's code didn't change, but a package they depend on did. Check in this order:

1. **Worker image diff** (preferred when available). Every Astro deploy = new image tag, so the registry has a "before" and "after". Diff `pip freeze` between current and previous image — that's ground truth for what changed:
   ```
   docker run --rm <current_image> pip freeze > /tmp/now.txt
   docker run --rm <previous_image> pip freeze > /tmp/prev.txt
   diff /tmp/prev.txt /tmp/now.txt
   ```
   Also compare `docker run --rm <image> python --version` between the two — a Python minor-version bump (3.11 → 3.12, or even a patch) can break wheel compatibility even when `pip freeze` looks identical. This lists currently installed provider versions, useful for cross-checking against modules named in the traceback:
   ```bash
   astro local af providers
   # v1: af config providers
   ```

2. **Venv-style operators bypass the worker image.** `@task.virtualenv`, `PythonVirtualenvOperator`, `ExternalPythonOperator`, and `KubernetesPodOperator` build their environment per task run, so an image diff won't catch failures inside them. If the failed task is one of these, read its `requirements` / `image` / `python_version` / `python` args directly:
   - Unbounded specifier (e.g. `pandas>=2.0.0` with no upper bound, or no specifier at all) → a new upstream release is the prime suspect.
   - `image="foo:latest"` or no tag → the image moved underneath you.
   - `python_version="3.11"` (on `@task.virtualenv` / `PythonVirtualenvOperator`) or a `python` path (on `ExternalPythonOperator`) resolving to a different interpreter than it used to — a Python minor-version change can break wheel compatibility for unchanged `requirements`. Same vector applies to the worker image itself if the base Python changed there.

   Fix is to pin: `pandas>=2.0.0,<3.0.0`, a lockfile, a specific image SHA, or a fully-qualified Python version (`python_version="3.11.7"` instead of `"3.11"`).

3. **Index lookup** when image diff isn't conclusive (no image history, or a venv-style operator). Identify the configured index first — it may not be PyPI:
   - Env vars: `UV_INDEX_URL`, `PIP_INDEX_URL`, `PIP_EXTRA_INDEX_URL`
   - `pyproject.toml` → `[[tool.uv.index]]`
   - `~/.pip/pip.conf`, `/etc/pip.conf`
   - `Dockerfile` `--index-url` flags

   Then query for releases of the suspect package since the first failure started. PyPI:
   ```
   curl -s https://pypi.org/pypi/<pkg>/json | jq '.releases | to_entries | map({version: .key, uploaded: .value[0].upload_time}) | sort_by(.uploaded) | reverse | .[:5]'
   ```
   Private indexes usually expose the same `/pypi/<pkg>/json` shape; fall back to the Simple API (`/simple/<pkg>/`) or ask the user if neither works.

A release timestamp landing between the last green run and the first red run, for a package named in the traceback, is the answer.

### On Astro

If you're running on Astro, these additional tools can help with diagnosis:

- **Deployment activity log**: Check the Astro UI for recent deploys — a failed deploy or recent code change is often the cause of sudden failures
- **Astro alerts**: Configure alerts in the Astro UI for proactive failure monitoring (DAG failure, task duration, SLA miss)
- **Observability**: Use the Astro [observability dashboard](https://www.astronomer.io/docs/astro/airflow-alerts) to track DAG health trends and spot recurring issues

### On OSS Airflow

- **Airflow UI**: Use the DAGs page, Graph view, and task logs to inspect recent runs and failures

## Step 4: Provide Actionable Output

Structure your diagnosis as:

### Root Cause
What actually broke? Be specific - not "the task failed" but "the task failed because column X was null in 15% of rows when the code expected 0%".

### Impact Assessment
- What data is affected? Which tables didn't get updated?
- What downstream processes are blocked?
- Is this blocking production dashboards or reports?

### Immediate Fix
Specific steps to resolve RIGHT NOW:
1. If it's a data issue: SQL to fix or skip bad records
2. If it's a code issue: The exact code change needed
3. If it's infra: Who to contact or what to restart

### Prevention
How to prevent this from happening again:
- Add data quality checks?
- Add better error handling?
- Add alerting for edge cases?
- Update documentation?
- Pin dependencies (constraints file, lockfile, or upper-bound specifiers on venv/external/pod operators) to avoid silent upstream drift?

### Quick Commands
Provide ready-to-use commands, for the version the user has. Get the user's go-ahead before running any of them, and preview first:

```bash
# Clear and rerun the entire DAG run: preview, then run it
astro local af runs clear <dag_id> <run_id> --dry-run
astro local af runs clear <dag_id> <run_id> --yes

# Clear and rerun specific failed tasks: preview, then run it
astro local af tasks clear <dag_id> <run_id> <task_id> <task_id> --dry-run
# v1: af tasks clear <dag_id> <run_id> <task_id>,<task_id> --dry-run
astro local af tasks clear <dag_id> <run_id> <task_id> <task_id> --yes
# v1: af tasks clear <dag_id> <run_id> <task_id>,<task_id> --no-dry-run

# Delete a stuck or unwanted run
astro local af runs delete <dag_id> <run_id> --yes
```

**v1:** `tasks clear` never prompts.
