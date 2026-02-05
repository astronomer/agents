---
name: refactoring-dags
description: Review and refactor existing Airflow DAGs against best practices. Use when the user wants to improve, clean up, or modernize an existing DAG, review DAG code quality, or fix anti-patterns. For writing new DAGs from scratch, see the authoring-dags skill.
hooks:
  Stop:
    - hooks:
        - type: command
          command: "echo 'Remember to test your refactored DAG with the testing-dags skill'"
---

# DAG Refactoring Skill

This skill guides you through reviewing an existing Airflow DAG against best practices, identifying issues, and refactoring with user approval.

> **For writing new DAGs from scratch**, see the **authoring-dags** skill. For testing after refactoring, see the **testing-dags** skill.

---

## CRITICAL WARNING: Use MCP Tools, NOT CLI Commands

> **STOP! Before running ANY Airflow-related command, read this.**
>
> You MUST use MCP tools for ALL Airflow interactions. CLI commands like `astro dev run`, `airflow dags`, or shell commands to read logs are **FORBIDDEN**.
>
> **Why?** MCP tools provide structured, reliable output. CLI commands are fragile, produce unstructured text, and often fail silently.

---

## CLI vs MCP Quick Reference

**ALWAYS use Airflow MCP tools. NEVER use CLI commands.**

| DO NOT USE | USE INSTEAD |
|---------------|----------------|
| `astro dev run dags list` | `list_dags` MCP tool |
| `airflow dags list` | `list_dags` MCP tool |
| `astro dev run dags test` | `trigger_dag_and_wait` MCP tool |
| `airflow tasks test` | `trigger_dag_and_wait` MCP tool |
| `cat` / `grep` on Airflow logs | `get_task_logs` MCP tool |
| `find` in dags folder | `list_dags` or `explore_dag` MCP tool |
| Any `astro dev run ...` | Equivalent MCP tool |
| Any `airflow ...` CLI | Equivalent MCP tool |
| `ls` on `/usr/local/airflow/dags/` | `list_dags` or `explore_dag` MCP tool |
| `cat ... \| jq` to filter MCP results | Read the JSON directly from MCP response |

**Remember:**
- Airflow is ALREADY running — the MCP server handles the connection
- Do NOT attempt to start, stop, or manage the Airflow environment
- Do NOT use shell commands to check DAG status, logs, or errors
- Do NOT use bash to parse or filter MCP tool results — read the JSON directly
- Do NOT use `ls`, `find`, or `cat` on Airflow container paths (`/usr/local/airflow/...`)
- ALWAYS use MCP tools — they return structured JSON you can read directly

---

## Workflow Overview

```
┌─────────────────────────────────────┐
│ 1. IDENTIFY                         │
│    Locate the DAG to refactor       │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 2. AUDIT                            │
│    Review against best practices    │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 3. PROPOSE                          │
│    Present findings, get approval   │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 4. REFACTOR                         │
│    Apply approved changes           │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 5. VALIDATE                         │
│    Check import errors, warnings    │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ 6. TEST (with user consent)         │
│    Trigger, monitor, check logs     │
└─────────────────────────────────────┘
```

---

## Phase 1: Identify

Locate the DAG to review. If the user specified a DAG, find its source file. If not, help them pick one.

### Locate DAG Source

1. Use `list_dags` MCP tool to find available DAGs
2. Use `explore_dag(dag_id="target_dag")` to get metadata and **source code**
3. Use `Read` to open the DAG source file for detailed analysis

### Gather Context

Use MCP tools to understand the environment:

| Tool | Purpose |
|------|---------|
| `explore_dag` | Full DAG structure, tasks, dependencies, source |
| `get_dag_details` | Schedule, tags, config |
| `list_connections` | Available connections (for credential checks) |
| `get_airflow_version` | Version — determines which patterns apply |
| `list_providers` | Installed operators (for provider upgrade checks) |

---

## Phase 2: Audit

Review the DAG source code against the best practices reference. Check each category systematically.

**Reference:** See **[best-practices.md](../_shared/reference/best-practices.md)** for the full set of patterns and anti-patterns.

### Audit Checklist

Work through these categories and note every issue found:

**Structure & API:**
- [ ] Uses TaskFlow API (`@dag`, `@task` decorators) instead of classic operators where appropriate
- [ ] No top-level code that executes on every parse (hooks, queries, API calls outside tasks)
- [ ] Uses `@task_group` instead of SubDAGs
- [ ] Uses dynamic task mapping (`.expand()`) instead of loops where appropriate

**Credentials & Configuration:**
- [ ] No hard-coded credentials, connection strings, or secrets
- [ ] Uses Airflow connections (`BaseHook.get_connection` / `Connection`) and variables (`Variable.get`)
- [ ] Sensitive values use templating (`{{ var.value.x }}`) or runtime lookups, not top-level code

**Operators & Providers:**
- [ ] Uses provider operators (e.g., `SnowflakeOperator`) instead of generic `BashOperator`/`PythonOperator` for external systems
- [ ] Uses deferrable mode (`deferrable=True`) for sensors and long-running operators where available

**Data Handling:**
- [ ] Tasks are idempotent (safe to re-run: delete-before-insert, MERGE, etc.)
- [ ] Uses data intervals (`data_interval_start`/`data_interval_end`) instead of `datetime.now()` or `execution_date`
- [ ] Large data goes to external storage, XCom carries only references (paths/URIs)

**Resilience & Scaling:**
- [ ] Retries configured with exponential backoff
- [ ] Resource-constrained tasks use pools
- [ ] `max_active_runs` / `max_active_tasks` set appropriately

**Cleanup & Quality:**
- [ ] Uses setup/teardown for temporary resources
- [ ] Includes data quality checks where applicable
- [ ] No deprecated imports (`DummyOperator`, `execution_date` context key, `airflow.settings.Session`)
- [ ] No hard-coded file paths (uses `os.path.dirname(__file__)` or `AIRFLOW_HOME`)

**Airflow 3 Readiness (if applicable):**
- [ ] Uses `airflow.sdk` imports (or at least compatible Airflow 2 imports)
- [ ] Uses `logical_date` / `data_interval_start` instead of `execution_date`
- [ ] Uses Assets for cross-DAG data dependencies where appropriate

---

## Phase 3: Propose

Present the audit findings to the user **before making any changes**. Structure your findings as:

### Finding Report Format

For each issue found:
1. **Category** — Which checklist area (e.g., "Credentials", "Anti-Pattern")
2. **Location** — File path and line number(s)
3. **Issue** — What the current code does wrong
4. **Recommendation** — What the refactored code should look like
5. **Risk** — Low (style/modernization), Medium (correctness/reliability), High (security/data loss)

### Prioritization

Present findings ordered by risk:
1. **High risk** — Security issues (hard-coded credentials), data correctness (non-idempotent tasks)
2. **Medium risk** — Reliability (no retries, top-level code), deprecations that will break on upgrade
3. **Low risk** — Modernization (TaskFlow API migration, task groups, deferrable operators)

**Get user approval on which findings to address before proceeding.**

---

## Phase 4: Refactor

Apply only the approved changes. Follow these principles:

- **Preserve behavior** — Refactoring should not change what the DAG does, only how it does it
- **Incremental changes** — Apply one category of changes at a time when possible
- **Keep the DAG ID** — Changing `dag_id` creates a new DAG in Airflow and loses history
- **Preserve schedules** — Do not alter the schedule unless explicitly asked

---

## Phase 5: Validate

After refactoring, verify the DAG still works.

### Step 1: Check Import Errors

**MCP tool:** `list_import_errors`

- If the refactored file appears → **fix and retry**
- If no errors → **continue**

### Step 2: Verify DAG Still Exists

**MCP tool:** `get_dag_details(dag_id="your_dag_id")`

Confirm: same `dag_id`, correct schedule, tags preserved.

### Step 3: Check Warnings

**MCP tool:** `list_dag_warnings`

Verify no new warnings introduced. Existing deprecation warnings should decrease if migration patterns were applied.

### Step 4: Explore Refactored Structure

**MCP tool:** `explore_dag(dag_id="your_dag_id")`

Compare task count and dependency graph with the original to confirm structural equivalence.

---

## Phase 6: Test

> See the **testing-dags** skill for comprehensive testing guidance.

After validation passes:

1. **Get user consent** — Always ask before triggering
2. **Trigger and wait** — Use `trigger_dag_and_wait(dag_id, timeout=300)`
3. **Compare results** — Behavior should match pre-refactor runs
4. **Debug if needed** — Use `diagnose_dag_run` and `get_task_logs`

For the full test, debug, and fix loop, see **testing-dags**.

---

## MCP Tools Quick Reference

| Phase | Tool | Purpose |
|-------|------|---------|
| Identify | `list_dags` | Find available DAGs |
| Identify | `explore_dag` | Full DAG inspection + source |
| Identify | `get_dag_details` | DAG config and schedule |
| Audit | `get_airflow_version` | Determine applicable patterns |
| Audit | `list_providers` | Check available operators |
| Audit | `list_connections` | Verify connection usage |
| Validate | `list_import_errors` | Parse errors after refactor |
| Validate | `get_dag_details` | Confirm DAG preserved |
| Validate | `list_dag_warnings` | Check for new warnings |
| Validate | `explore_dag` | Compare structure |

> **Testing tools** — See the **testing-dags** skill for `trigger_dag_and_wait`, `diagnose_dag_run`, `get_task_logs`, etc.

---

## Related Skills

- **authoring-dags**: For writing new DAGs from scratch
- **testing-dags**: For testing DAGs, debugging failures, and the test, fix, retest loop
- **debugging-dags**: For troubleshooting failed DAGs
- **migrating-airflow-2-to-3**: For migrating DAGs to Airflow 3
