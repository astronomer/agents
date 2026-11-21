---
name: authoring-dags
description: Workflow and best practices for writing Apache Airflow DAGs. Use when creating a new DAG, write pipeline code, handling questions about DAG patterns and conventions or extending an existing DAG with a follow-up/downstream task. ANY request shaped like 'add a DAG named X', 'write a pipeline', 'add a task that runs after Y', or 'extend the DAG'. For testing and debugging DAGs, see the testing-dags skill.
hooks:
  Stop:
    - hooks:
        - type: command
          command: "echo 'Remember to test your DAG with the testing-dags skill'"
---

# DAG Authoring Skill

This skill guides you through creating and validating Airflow DAGs using best practices and Airflow CLI commands.

> **For testing and debugging DAGs**, see the **testing-dags** skill which covers the full test -> debug -> fix -> retest workflow.

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

---

## Workflow Overview

```
+-----------------------------------------+
| 1. DISCOVER                             |
|    Understand codebase & environment    |
+-----------------------------------------+
                 |
+-----------------------------------------+
| 2. PLAN                                 |
|    Propose structure, get approval      |
+-----------------------------------------+
                 |
+-----------------------------------------+
| 3. IMPLEMENT                            |
|    Write DAG following patterns         |
+-----------------------------------------+
                 |
+-----------------------------------------+
| 4. VALIDATE                             |
|    Check import errors, warnings        |
+-----------------------------------------+
                 |
+-----------------------------------------+
| 5. TEST (with user consent)             |
|    Trigger, monitor, check logs         |
+-----------------------------------------+
                 |
+-----------------------------------------+
| 6. ITERATE                              |
|    Fix issues, re-validate              |
+-----------------------------------------+
```

---

## Phase 1: Discover

Before writing code, understand the context.

### Explore the Codebase

Use file tools to find existing patterns:
- `Glob` for `**/dags/**/*.py` to find existing DAGs
- `Read` similar DAGs to understand conventions
- Check `requirements.txt` for available packages

### Query the Airflow Environment

Use these commands to understand what's available:

```bash
# What external systems are configured
astro local af connections list
# v1: af config connections

# What configuration values exist (v2 lists keys only; `variables get <key>` reads one)
astro local af variables list
# v1: af config variables

# What operator packages are installed
astro local af providers
# v1: af config providers

# Version constraints and features
astro local af version
# v1: af config version

# Existing DAGs and naming conventions
astro local af dags list

# Resource pools for concurrency
astro local af pools list
# v1: af config pools
```

**Example discovery questions:**
- "Is there a Snowflake connection?" -> `astro local af connections list`
- "What Airflow version?" -> `astro local af version`
- "Are S3 operators available?" -> `astro local af providers`

---

## Phase 2: Plan

Based on discovery, propose:

1. **DAG structure** - Tasks, dependencies, schedule
2. **Operators to use** - Based on available providers
3. **Connections needed** - Existing or to be created
4. **Variables needed** - Existing or to be created
5. **Packages needed** - Additions to requirements.txt

**Get user approval before implementing.**

---

## Phase 3: Implement

Write the DAG following best practices (see below). Key steps:

1. Create DAG file in appropriate location
2. Update `requirements.txt` if needed
3. Save the file

---

## Phase 4: Validate

**Use the Airflow CLI as a feedback loop to validate your DAG.**

### Step 1: Check Import Errors

After saving, check for parse errors (Airflow will have already parsed the file):

```bash
astro local af dags errors
```

- If your file appears -> **fix and retry**
- If no errors -> **continue**

Common causes: missing imports, syntax errors, missing packages.

### Step 2: Verify DAG Exists

```bash
astro local af dags get <dag_id>
```

Check: DAG exists, schedule correct, tags set, paused status.

### Step 3: Check Warnings

```bash
astro local af dags warnings
```

Look for deprecation warnings or configuration issues.

### Step 4: Explore DAG Structure

```bash
astro local af dags explore <dag_id>
```

Returns in one call: metadata, tasks, dependencies, source code.

### On Astro

If you're running on Astro, you can also validate locally before deploying:

- **Parse check**: Run this to catch import errors and DAG-level issues without starting a full Airflow environment:
  ```bash
  astro local check
  # v1: astro dev parse
  ```
- **DAG-only deploy**: Once validated, use `astro deploy --dags` for fast DAG-only deploys that skip the Docker image build — ideal for iterating on DAG code

---

## Phase 5: Test

> See the **testing-dags** skill for comprehensive testing guidance.

Once validation passes, test the DAG using the workflow in the **testing-dags** skill:

1. **Get user consent** -- Always ask before triggering
2. **Trigger and wait** -- `astro local af runs trigger-wait <dag_id> --timeout 300`
3. **Analyze results** -- Check success/failure status (see "Response Interpretation" in **testing-dags**: the two versions report it differently)
4. **Debug if needed** -- `astro local af runs diagnose <dag_id> <run_id>` and `astro local af tasks logs <dag_id> <run_id> <task_id>`

### Quick Test (Minimal)

```bash
# Ask user first, then:
astro local af runs trigger-wait <dag_id> --timeout 300
```

For the full test -> debug -> fix -> retest loop, see **testing-dags**.

---

## Phase 6: Iterate

If issues found:
1. Fix the code
2. Check for import errors: `astro local af dags errors`
3. Re-validate (Phase 4)
4. Re-test using the **testing-dags** skill workflow (Phase 5)

---

## CLI Quick Reference

| Phase | Command | Purpose |
|-------|---------|---------|
| Discover | `astro local af connections list` | Available connections |
| Discover | `astro local af variables list` | Configuration values |
| Discover | `astro local af providers` | Installed operators |
| Discover | `astro local af version` | Version info |
| Validate | `astro local af dags errors` | Parse errors (check first!) |
| Validate | `astro local af dags get <dag_id>` | Verify DAG config |
| Validate | `astro local af dags warnings` | Configuration warnings |
| Validate | `astro local af dags explore <dag_id>` | Full DAG inspection |

**v1:** the four Discover commands are named differently; their v1 forms are under "Query the Airflow Environment" above.

> **Testing commands** -- See the **testing-dags** skill for `astro local af runs trigger-wait`, `astro local af runs diagnose`, `astro local af tasks logs`, etc.

---

## Best Practices & Anti-Patterns

For code patterns and anti-patterns, see **[reference/best-practices.md](reference/best-practices.md)**.

**Read this reference when writing new DAGs or reviewing existing ones.** It covers what patterns are correct (including Airflow 3-specific behavior) and what to avoid.

---

## Related Skills

- **testing-dags**: For testing DAGs, debugging failures, and the test -> fix -> retest loop
- **debugging-dags**: For troubleshooting failed DAGs
- **deploying-airflow**: For deploying DAGs to production (Astro or open-source)
- **migrating-airflow-2-to-3**: For migrating DAGs to Airflow 3
