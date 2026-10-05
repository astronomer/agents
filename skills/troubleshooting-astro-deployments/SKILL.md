---
name: troubleshooting-astro-deployments
description: Troubleshoot Astronomer production deployments with Astro CLI. Use when investigating deployment issues, viewing production logs, analyzing failures, or managing deployment environment variables and Environment Manager variables.
---

# Astro Deployment Troubleshooting

This skill helps you diagnose and troubleshoot production Astronomer deployments using the Astro CLI.

> **For deployment management**, see the **managing-astro-deployments** skill.
> **For local development**, see the **managing-astro-local-env** skill.

---

## Quick Health Check

Start with these commands to get an overview:

```bash
# 1. List deployments to find target
astro deployment list

# 2. Get deployment overview
astro deployment inspect <DEPLOYMENT_ID>

# 3. Check for errors
astro deployment logs <DEPLOYMENT_ID> --error -c 50
```

---

## Viewing Deployment Logs

Use `-c` to control log count (default: 500). Log flags cannot be combined — use one component or level flag per command.

### Component-Specific Logs

View logs from specific Airflow components:

```bash
# Scheduler logs (DAG processing, task scheduling)
astro deployment logs <DEPLOYMENT_ID> --scheduler -c 50

# Worker logs (task execution)
astro deployment logs <DEPLOYMENT_ID> --workers -c 30

# Webserver logs (UI access, health checks)
astro deployment logs <DEPLOYMENT_ID> --webserver -c 30

# Triggerer logs (deferrable operators)
astro deployment logs <DEPLOYMENT_ID> --triggerer -c 30
```

### Log Level Filtering

Filter by severity:

```bash
# Error logs only (most useful for troubleshooting)
astro deployment logs <DEPLOYMENT_ID> --error -c 30

# Warning logs
astro deployment logs <DEPLOYMENT_ID> --warn -c 50

# Info-level logs
astro deployment logs <DEPLOYMENT_ID> --info -c 50
```

### Search Logs

Search for specific keywords:

```bash
# Search for specific error
astro deployment logs <DEPLOYMENT_ID> --keyword "ConnectionError"

# Search for specific DAG
astro deployment logs <DEPLOYMENT_ID> --keyword "my_dag_name" -c 100

# Find import errors
astro deployment logs <DEPLOYMENT_ID> --error --keyword "ImportError"

# Find task failures
astro deployment logs <DEPLOYMENT_ID> --error --keyword "Task failed"
```

---

## Complete Investigation Workflow

### Step 1: Identify the Problem

```bash
# List deployments with status
astro deployment list

# Get deployment details
astro deployment inspect <DEPLOYMENT_ID>
```

Look for:
- Status: HEALTHY vs UNHEALTHY
- Runtime version compatibility
- Resource limits (CPU, memory)
- Recent deployment timestamp

### Step 2: Check Error Logs

```bash
# Start with errors
astro deployment logs <DEPLOYMENT_ID> --error -c 50
```

Look for:
- Recurring error patterns
- Specific DAGs failing repeatedly
- Import errors or syntax errors
- Connection or credential errors

### Step 3: Review Scheduler Logs

```bash
# Check DAG processing
astro deployment logs <DEPLOYMENT_ID> --scheduler -c 30
```

Look for:
- DAG parse errors
- Scheduling delays
- Task queueing issues

### Step 4: Check Worker Logs

```bash
# Check task execution
astro deployment logs <DEPLOYMENT_ID> --workers -c 30
```

Look for:
- Task execution failures
- Resource exhaustion
- Timeout errors

### Step 5: Verify Configuration

```bash
# Check environment variables: the deployment's own, then the Environment Manager's (see Environment Variables Management)
astro deployment variable list --deployment-id <DEPLOYMENT_ID>
astro env variable list --deployment-id <DEPLOYMENT_ID> --resolve-linked

# Check Environment Manager connections that reach the deployment
astro env connection list --deployment-id <DEPLOYMENT_ID> --resolve-linked

# Verify deployment settings
astro deployment inspect <DEPLOYMENT_ID>
```

Look for:
- Missing or incorrect environment variables
- Secrets configuration (AIRFLOW__SECRETS__BACKEND)
- Connection configuration

---

## Common Investigation Patterns

### Recurring DAG Failures

Follow the complete investigation workflow above, then narrow to the specific DAG:

```bash
astro deployment logs <DEPLOYMENT_ID> --keyword "my_dag_name" -c 100
```

### Resource Issues

```bash
# 1. Check deployment resource allocation
astro deployment inspect <DEPLOYMENT_ID>
# Look for: resource_quota_cpu, resource_quota_memory
# Worker queue: max_worker_count, worker_type

# 2. Check for worker scaling issues
astro deployment logs <DEPLOYMENT_ID> --workers -c 50

# 3. Look for out-of-memory errors
astro deployment logs <DEPLOYMENT_ID> --error --keyword "memory"
```

### Configuration Problems

```bash
# 1. Review environment variables, in both places they can live
astro deployment variable list --deployment-id <DEPLOYMENT_ID>
astro env variable list --deployment-id <DEPLOYMENT_ID> --resolve-linked

# 2. Check for secrets backend configuration
# Look for: AIRFLOW__SECRETS__BACKEND, AIRFLOW__SECRETS__BACKEND_KWARGS

# 3. Verify deployment settings
astro deployment inspect <DEPLOYMENT_ID>

# 4. Check webserver logs for auth issues
astro deployment logs <DEPLOYMENT_ID> --webserver -c 30
```

### Import Errors

```bash
# 1. Find import errors
astro deployment logs <DEPLOYMENT_ID> --error --keyword "ImportError"

# 2. Check scheduler for parse failures
astro deployment logs <DEPLOYMENT_ID> --scheduler --keyword "Failed to import" -c 50

# 3. Verify dependencies were deployed
astro deployment inspect <DEPLOYMENT_ID>
# Check: current_tag, last deployment timestamp
```

---

## Environment Variables Management

Astro keeps a deployment's variables in two separate places, and each has its own commands:

| | Deployment environment variables | Environment Manager variables |
|---|---|---|
| Stored | on the deployment itself | as Environment Manager objects, owned by a workspace or by one deployment. A workspace object reaches a deployment through a link, or through auto-link, which reaches every deployment in the workspace |
| Commands | `astro deployment variable list`, `create`, `update` | `astro env variable list`, `get`, `set`, `delete`, `export`, `link` |
| Delete from the CLI | no: use the Astro UI | yes |

The Environment Manager also holds connections and Airflow variables (`astro env connection ...`, `astro env airflow-variable ...`), with the same scope flags, verbs, and delete rules as `astro env variable`.

The `astro env` commands differ between CLI versions. The commands below are written for Astro CLI v2, and a `v1:` note gives the Astro CLI v1 form where it differs. v2 spells create-or-update as `set <KEY>`. v1 has `create --key <KEY>` and `update <KEY>`, and v1's `update` also creates a missing key. In a v2 project, `--deployment-id` on `astro env` commands also accepts a link name.

### Find Where a Variable Lives

```bash
# Deployment environment variables
astro deployment variable list --deployment-id <DEPLOYMENT_ID>
astro deployment variable list --deployment-id <DEPLOYMENT_ID> --key AWS_REGION

# Environment Manager variables that reach the deployment, including workspace variables linked into it
astro env variable list --deployment-id <DEPLOYMENT_ID> --resolve-linked

# Only the Environment Manager variables the deployment itself owns, with their IDs
astro env variable list --deployment-id <DEPLOYMENT_ID> --resolve-linked=false
```

`--resolve-linked` is on by default. A key that shows up with `--resolve-linked` but not with `--resolve-linked=false` is a workspace variable linked into the deployment. To see how it is linked, list its links in the deployment's workspace (find the workspace ID with `astro workspace list`):

```bash
astro env variable link list --variable-key <KEY> --workspace-id <WORKSPACE_ID>
```

The output shows `AUTO-LINK` (true when the variable reaches every deployment in the workspace), the deployments it is explicitly linked to with any per-deployment override, and the deployments excluded from it.

To save the deployment environment variables to a file, add `--save --env .env.backup` to `astro deployment variable list`. For Environment Manager variables, `astro env variable export --deployment-id <DEPLOYMENT_ID> > .env.backup` writes the same `KEY=VALUE` form; secret values are left blank unless you pass `--include-secrets`, which the organization's policy must allow.

### Create or Update Variables

Deployment environment variables take `KEY=VALUE` arguments:

```bash
# Create (a key that already exists is skipped)
astro deployment variable create API_ENDPOINT=https://api.example.com --deployment-id <DEPLOYMENT_ID>

# Create as a secret (masked in the UI and logs)
astro deployment variable create API_KEY=<VALUE> --deployment-id <DEPLOYMENT_ID> --secret

# Update (creates the key if it is missing; a secret stays secret)
astro deployment variable update API_KEY=<NEW_VALUE> --deployment-id <DEPLOYMENT_ID>
```

Environment Manager variables, on one deployment or on the workspace:

```bash
# On one deployment, creating it if it does not exist   v1: astro env variable update API_KEY --deployment-id <DEPLOYMENT_ID> --value <VALUE> --secret
astro env variable set API_KEY --deployment-id <DEPLOYMENT_ID> --value <VALUE> --secret

# On the workspace, reaching every deployment in it   v1: astro env variable update LOG_LEVEL --workspace-id <WORKSPACE_ID> --value INFO --auto-link
astro env variable set LOG_LEVEL --workspace-id <WORKSPACE_ID> --value INFO --auto-link
```

`--secret` applies only when the variable is created; to change it later, delete and re-create the variable. Omit `--value` to be prompted for the value with echo off, which keeps a secret out of the shell history.

### Delete Variables

Find which kind the variable is first (see Find Where a Variable Lives), then ask the user to confirm the exact key, kind, and scope before running any delete.

**Deployment environment variable.** No CLI command deletes one: `astro deployment variable` has only `list`, `create`, and `update`. Remove it in the Astro UI, from the deployment's environment variables.

**Environment Manager variable owned by the deployment** (listed with `--resolve-linked=false`):

```bash
astro env variable delete <KEY> --deployment-id <DEPLOYMENT_ID> --yes
```

This deletes the deployment's own variable only. Run with `--deployment-id`, delete looks the key up among the deployment's own variables, so for a workspace variable linked into the deployment it fails with `environment object not found` and deletes nothing.

**Workspace variable linked into the deployment.** To stop it reaching this one deployment, remove the link and leave the workspace variable in place:

```bash
# Explicitly linked (the deployment appears under the variable's links)
astro env variable link delete --variable-key <KEY> --workspace-id <WORKSPACE_ID> --deployment-id <DEPLOYMENT_ID>

# Auto-linked (AUTO-LINK is true): exclude the deployment instead   v1: astro env variable link create ... --exclude
astro env variable link set --variable-key <KEY> --workspace-id <WORKSPACE_ID> --deployment-id <DEPLOYMENT_ID> --exclude
```

`link delete --exclude` removes an exclude again. Deleting the workspace variable itself removes it from **every** deployment that links it, so do it only when the user asks for that outcome, after showing them `astro env variable link list` for it:

```bash
astro env variable delete <KEY> --workspace-id <WORKSPACE_ID> --yes
```

Pass a key, not an ID, to `astro env variable delete`. An ID is deleted directly, whatever `--workspace-id` or `--deployment-id` says, so a workspace variable's ID deletes the workspace variable even when run with `--deployment-id`.

`astro env connection` and `astro env airflow-variable` delete the same way. Their links are managed with `--connection-key` and `--airflow-variable-key` in v2; v1 has no `link` commands for them, so manage those links in the Astro UI.

**Note**: Both kinds reach DAGs as environment variables, and neither needs a redeploy. Environment Manager changes reach the deployment within a few minutes; tasks already running keep the old value.

---

## Key Metrics from `deployment inspect`

Focus on these fields when troubleshooting:

- **status**: HEALTHY vs UNHEALTHY
- **runtime_version**: Airflow version compatibility
- **scheduler_size/scheduler_count**: Scheduler capacity
- **executor**: CELERY, KUBERNETES, or LOCAL
- **worker_queues**: Worker scaling limits and types
  - `min_worker_count`, `max_worker_count`
  - `worker_concurrency`
  - `worker_type` (resource class)
- **resource_quota_cpu/memory**: Overall resource limits
- **dag_deploy_enabled**: Whether DAG-only deploys work
- **current_tag**: Last deployment version
- **is_high_availability**: Redundancy enabled

---

## Investigation Best Practices

1. **Always start with error logs** - Most obvious failures appear here
2. **Check error logs for patterns** - Same DAG failing repeatedly? Timing patterns?
3. **Component-specific troubleshooting**:
   - Worker logs → task execution details
   - Scheduler logs → DAG processing and scheduling
   - Webserver logs → UI issues and health checks
   - Triggerer logs → deferrable operator issues
4. **Use `--keyword` for targeted searches** - More efficient than reading all logs
5. **The `inspect` command is your health dashboard** - Check it first
6. **Environment variables in `inspect` output** - May reveal configuration issues
7. **Log count default is 500** - Adjust with `-c` based on needs
8. **Don't forget to check deployment time** - Recent deploy might have introduced issue

---

## Troubleshooting Quick Reference

| Symptom | Command |
|---------|---------|
| Deployment shows UNHEALTHY | `astro deployment inspect <ID>` + `--error` logs |
| DAG not appearing | `--error` logs for import errors, check `--scheduler` logs |
| Tasks failing | `--workers` logs + search for DAG with `--keyword` |
| Slow scheduling | `--scheduler` logs + check `inspect` for scheduler resources |
| UI not responding | `--webserver` logs |
| Connection issues | `astro env connection list --deployment-id <ID>`, check variables, search logs for connection name |
| Import errors | `--error --keyword "ImportError"` + `--scheduler` logs |
| Out of memory | `inspect` for resources + `--workers --keyword "memory"` |

---

## Related Skills

- **managing-astro-deployments**: Create, update, delete deployments, deploy code
- **managing-astro-local-env**: Manage local Airflow development environment
- **setting-up-astro-project**: Initialize and configure Astro projects
