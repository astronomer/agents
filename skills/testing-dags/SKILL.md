---
name: testing-dags
description: Complex DAG testing workflows with debugging and fixing cycles. Use for multi-step testing requests like "test this dag and fix it if it fails", "test and debug", "run the pipeline and troubleshoot issues". For simple test requests ("test dag", "run dag"), the airflow entrypoint skill handles it directly. This skill is for iterative test-debug-fix cycles.
---

# DAG Testing Skill

Use the Airflow CLI to test, debug, and fix DAGs in iterative cycles.

## Astro CLI v1 or v2

Commands here are written for Astro CLI v2. Run `astro local af --help` once: it succeeds only on v2.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI (`uvx --from astro-airflow-mcp af` if `af` is not on PATH). Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` (`af` always prints JSON). Where a command needs more than that, its v1 form is given beside it, marked `v1:`.
- If a v2 command reports an Astro v1 project, use the v1 forms. Upgrading the project (`astro init`) is the user's call.

To test against a deployment instead of the local Airflow, see "Choosing Which Airflow" in the **airflow** skill.

---

## Quick Validation with Astro CLI

These give fast feedback without a running Airflow instance:

```bash
# Parse DAGs to catch import errors, syntax issues, and DAG-level problems
astro local check     # v1: astro dev parse

# Run the project's tests (tests/ directory)
uv run pytest         # v1: astro dev pytest
```

Use these for quick validation during development. For full end-to-end testing against a live Airflow instance, continue to the trigger-and-wait workflow below.

---

## FIRST ACTION: Just Trigger the DAG

When the user asks to test a DAG, your **FIRST AND ONLY action** should be:

```bash
astro local af runs trigger-wait <dag_id>
```

**DO NOT:**
- Call `astro local af dags list` first
- Call `astro local af dags get` first
- Call `astro local af dags errors` first
- Use `grep` or `ls` or any other bash command
- Do any "pre-flight checks"

**Just trigger the DAG.** If it fails, THEN debug.

---

## Testing Workflow Overview

```
┌─────────────────────────────────────┐
│ 1. TRIGGER AND WAIT                 │
│    Run DAG, wait for completion     │
└─────────────────────────────────────┘
                 ↓
        ┌───────┴───────┐
        ↓               ↓
   ┌─────────┐    ┌──────────┐
   │ SUCCESS │    │ FAILED   │
   │ Done!   │    │ Debug... │
   └─────────┘    └──────────┘
                       ↓
        ┌─────────────────────────────────────┐
        │ 2. DEBUG (only if failed)           │
        │    Get logs, identify root cause    │
        └─────────────────────────────────────┘
                       ↓
        ┌─────────────────────────────────────┐
        │ 3. FIX AND RETEST                   │
        │    Apply fix, restart from step 1   │
        └─────────────────────────────────────┘
```

**Philosophy: Try first, debug on failure.** Don't waste time on pre-flight checks — just run the DAG and diagnose if something goes wrong.

---

## Phase 1: Trigger and Wait

Use `astro local af runs trigger-wait` to test the DAG:

### Primary Method: Trigger and Wait

```bash
astro local af runs trigger-wait <dag_id> --timeout 300
```

**Example:**

```bash
astro local af runs trigger-wait my_dag --timeout 300
```

**Why this is the preferred method:**
- Single command handles trigger + monitoring
- Returns immediately when DAG completes (success or failure)
- Includes failed task details if run fails
- No manual polling required

### Response Interpretation

Read the JSON the command prints (v2: add `-o json`). The two versions shape it differently:

| | v2 | v1 |
|---|---|---|
| Run state | top-level `state` | `dag_run.state` |
| Timed out | `timed_out: true` | `timed_out: true`, and `state` at the top level |
| Failed tasks | `failed_tasks` | `failed_tasks` |
| Exit status | 0 succeeded, 1 failed (or the command itself failed, e.g. DAG not found), 2 timed out | 0 whenever the wait finished or timed out; 1 only when the command itself failed |

| Result | Next step |
|------|-----------|
| State `success` | Summarize and stop |
| State `failed` | Read `failed_tasks`, then go to Phase 2 |
| `timed_out: true` | The run is **still going**; see "If Timed Out" below |
| Error JSON, no run (e.g. DAG not found) | See "Check Import Errors" below |

Don't chain the next command with `&&` after `trigger-wait`: on v2 a failed run exits 1, and that is exactly when the debugging commands need to run.

**Success (v2):**
```json
{
  "dag_id": "my_dag",
  "dag_run_id": "manual__2025-01-14T...",
  "state": "success",
  "start_date": "...",
  "end_date": "...",
  "duration_seconds": 44,
  "unpaused": false,
  "timed_out": false,
  "elapsed_seconds": 45.2
}
```

**Failure (v2; v1 has the same fields under `dag_run`, with `timed_out`, `elapsed_seconds`, and `failed_tasks` beside it):**
```json
{
  "dag_id": "my_dag",
  "dag_run_id": "manual__2025-01-14T...",
  "state": "failed",
  "timed_out": false,
  "elapsed_seconds": 30.1,
  "failed_tasks": [
    {
      "task_id": "extract_data",
      "state": "failed",
      "try_number": 2
    }
  ]
}
```

**Timeout (both versions):**
```json
{
  "dag_id": "my_dag",
  "dag_run_id": "manual__...",
  "state": "running",
  "timed_out": true,
  "elapsed_seconds": 300.0
}
```

### Alternative: Trigger and Monitor Separately

Use this only when you need more control:

```bash
# Step 1: Trigger
astro local af runs trigger my_dag -o json
# Returns: {"dag_id": "my_dag", "dag_run_id": "manual__...", "state": "queued", ...}

# Step 2: Check status
astro local af runs get my_dag manual__2025-01-14T...
# Returns current state
```

---

## Handling Results

### If Success

The DAG ran successfully. Summarize for the user:
- Total elapsed time
- Number of tasks completed
- Any notable outputs (if visible in logs)

**You're done!**

### If Timed Out

The DAG is still running (stopping the wait does not stop the run). Options:
1. Check current status: `astro local af runs get <dag_id> <dag_run_id>`
2. Ask user if they want to continue waiting
3. Increase timeout and try again

### If Failed

Move to Phase 2 (Debug) to identify the root cause.

---

## Phase 2: Debug Failures (Only If Needed)

When a DAG run fails, use these commands to diagnose:

### Get Comprehensive Diagnosis

```bash
astro local af runs diagnose <dag_id> <dag_run_id>
```

Returns in one call:
- Run metadata (state, timing)
- All task instances with states
- Summary of failed tasks
- State counts (success, failed, skipped, etc.)

### Get Task Logs

```bash
astro local af tasks logs <dag_id> <dag_run_id> <task_id>
```

**Example:**

```bash
astro local af tasks logs my_dag manual__2025-01-14T... extract_data
```

**For specific retry attempt:**

```bash
astro local af tasks logs my_dag manual__2025-01-14T... extract_data --try 2
```

**Look for:**
- Exception messages and stack traces
- Connection errors (database, API, S3)
- Permission errors
- Timeout errors
- Missing dependencies

### Check Upstream Tasks

If a task shows `upstream_failed`, the root cause is in an upstream task. Use `astro local af runs diagnose` to find which task actually failed.

### Check Import Errors (If DAG Didn't Run)

If the trigger failed because the DAG doesn't exist:

```bash
astro local af dags errors
```

This reveals syntax errors or missing dependencies that prevented the DAG from loading.

---

## Phase 3: Fix and Retest

Once you identify the issue:

### Common Fixes

| Issue | Fix |
|-------|-----|
| Missing import | Add to DAG file |
| Missing package | Add to `requirements.txt` |
| Connection error | Check `astro local af connections list` (v1: `af config connections`), verify credentials |
| Variable missing | Check `astro local af variables list` (v2 shows keys only; `variables get <key>` reads one) (v1: `af config variables`), create if needed |
| Timeout | Increase task timeout or optimize query |
| Permission error | Check credentials in connection |

### After Fixing

1. Save the file
2. **Retest:** `astro local af runs trigger-wait <dag_id>`

**Repeat the test → debug → fix loop until the DAG succeeds.**

---

## CLI Quick Reference

| Phase | Command | Purpose |
|-------|---------|---------|
| Test | `astro local af runs trigger-wait <dag_id>` | **Primary test method — start here** |
| Test | `astro local af runs trigger <dag_id>` | Start run (alternative) |
| Test | `astro local af runs get <dag_id> <run_id>` | Check run status |
| Debug | `astro local af runs diagnose <dag_id> <run_id>` | Comprehensive failure diagnosis |
| Debug | `astro local af tasks logs <dag_id> <run_id> <task_id>` | Get task output/errors |
| Debug | `astro local af dags errors` | Check for parse errors (if DAG won't load) |
| Debug | `astro local af dags get <dag_id>` | Verify DAG config |
| Debug | `astro local af dags explore <dag_id>` | Full DAG inspection |
| Config | `astro local af connections list` (v1: `af config connections`) | List connections |
| Config | `astro local af variables list` (v1: `af config variables`) | List variables |

---

## Testing Scenarios

### Scenario 1: Test a DAG (Happy Path)

```bash
astro local af runs trigger-wait my_dag
# Success! Done.
```

### Scenario 2: Test a DAG (With Failure)

```bash
# 1. Run and wait
astro local af runs trigger-wait my_dag
# Failed...

# 2. Find failed tasks
astro local af runs diagnose my_dag manual__2025-01-14T...

# 3. Get error details
astro local af tasks logs my_dag manual__2025-01-14T... extract_data

# 4. [Fix the issue in DAG code]

# 5. Retest
astro local af runs trigger-wait my_dag
```

### Scenario 3: DAG Doesn't Exist / Won't Load

```bash
# 1. Trigger fails - DAG not found
astro local af runs trigger-wait my_dag
# Error: DAG not found

# 2. Find parse error
astro local af dags errors

# 3. [Fix the issue in DAG code]

# 4. Retest
astro local af runs trigger-wait my_dag
```

### Scenario 4: Debug a Failed Scheduled Run

```bash
# 1. Get failure summary
astro local af runs diagnose my_dag scheduled__2025-01-14T...

# 2. Get error from failed task
astro local af tasks logs my_dag scheduled__2025-01-14T... failed_task_id

# 3. [Fix the issue]

# 4. Retest
astro local af runs trigger-wait my_dag
```

### Scenario 5: Test with Custom Configuration

```bash
astro local af runs trigger-wait my_dag --conf '{"env": "staging", "batch_size": 100}' --timeout 600
```

### Scenario 6: Long-Running DAG

```bash
# Wait up to 1 hour
astro local af runs trigger-wait my_dag --timeout 3600

# If timed out, check current state
astro local af runs get my_dag manual__2025-01-14T...
```

---

## Debugging Tips

### Common Error Patterns

**Connection Refused / Timeout:**
- Check `astro local af connections list` (v1: `af config connections`) for correct host/port
- Verify network connectivity to external system
- Check if connection credentials are correct

**ModuleNotFoundError:**
- Package missing from `requirements.txt`
- After adding, may need environment restart

**PermissionError:**
- Check IAM roles, database grants, API keys
- Verify connection has correct credentials

**Task Timeout:**
- Query or operation taking too long
- Consider adding timeout parameter to task
- Optimize underlying query/operation

### Reading Task Logs

Task logs typically show:
1. Task start timestamp
2. Any print/log statements from task code
3. Return value (for @task decorated functions)
4. Exception + full stack trace (if failed)
5. Task end timestamp and duration

**Focus on the exception at the bottom of failed task logs.**

### On Astro

Astro deployments support environment promotion, which helps structure your testing workflow:

- **Dev deployment**: Test DAGs freely with `astro deploy --dags` for fast iteration
- **Staging deployment**: Run integration tests against production-like data
- **Production deployment**: Deploy only after validation in lower environments
- Use separate Astro deployments for each environment and promote code through them

---

## Related Skills

- **authoring-dags**: For creating new DAGs (includes validation before testing)
- **debugging-dags**: For general Airflow troubleshooting
- **deploying-airflow**: For deploying DAGs to production after testing
