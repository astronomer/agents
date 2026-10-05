---
name: managing-astro-deployments
description: Manage Astronomer production deployments with Astro CLI. Use when the user wants to authenticate, switch workspaces, create/update/delete deployments, or deploy code to production.
---

# Astro Deployment Management

This skill helps you manage production Astronomer deployments using the Astro CLI.

> **For local development**, see the **managing-astro-local-env** skill.
> **For production troubleshooting**, see the **troubleshooting-astro-deployments** skill.

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

## Authentication

All deployment operations require authentication:

```bash
# Login to Astronomer (opens browser for OAuth)
astro login
```

Authentication tokens are stored locally for subsequent commands. Run this before any deployment operations.

---

## Workspace Management

Deployments are organized into workspaces:

```bash
# List all accessible workspaces
astro workspace list

# Switch to a specific workspace
astro workspace switch <WORKSPACE_ID>
```

Workspace context is maintained between sessions. Most deployment commands operate within the current workspace context.

---

## List and Inspect Deployments

```bash
# List deployments in current workspace
astro deployment list

# List deployments across all workspaces
astro deployment list --all

# Inspect specific deployment (detailed info)
astro deployment inspect <DEPLOYMENT_ID>

# Inspect by name (alternative to ID)
astro deployment inspect --deployment-name data-service-stg
```

### What `inspect` Shows

- Deployment status (HEALTHY, UNHEALTHY)
- Runtime version and Airflow version
- Executor type (CELERY, KUBERNETES, LOCAL)
- Scheduler configuration (size, count)
- Worker queue settings (min/max workers, concurrency, worker type)
- Resource quotas (CPU, memory)
- Environment variables
- Last deployment timestamp and current tag
- Webserver and API URLs
- High availability status

---

## Create Deployments

```bash
# Create with default settings
astro deployment create

# Create with specific executor
astro deployment create --name production --executor CeleryExecutor
astro deployment create --name staging --executor KubernetesExecutor

# Executor options:
#   - celery: Best for most production workloads
#   - kubernetes: Best for dynamic scaling, isolated tasks
#   - local: Best for development only
```

---

## Update Deployments

```bash
# Enable DAG-only deploys (faster iteration)
astro deployment update <DEPLOYMENT_ID> --dag-deploy enable

# Update other settings (use --help for full options)
astro deployment update <DEPLOYMENT_ID> --help
```

---

## Delete Deployments

```bash
# Delete a deployment (requires confirmation)
astro deployment delete <DEPLOYMENT_ID>
```

**Destructive**: This cannot be undone. All DAGs, task history, and metadata will be lost.

---

## Deploy Code to Production

### Full Deploy

Deploy both DAGs and Docker image (required when dependencies change):

```bash
astro deploy <DEPLOYMENT_ID>
```

Use when:
- Dependencies changed (`requirements.txt`, `packages.txt`, `Dockerfile`)
- First deployment of new project
- Significant infrastructure changes

### DAG-Only Deploy (Recommended for Iteration)

Deploy only DAG files, skip Docker image rebuild:

```bash
astro deploy <DEPLOYMENT_ID> --dags
```

Use when:
- Only DAG files changed (Python files in `dags/` directory)
- Quick iteration during development
- Much faster than full deploy (seconds vs minutes)

**Requires**: DAG-only deploys enabled on the deployment (`--dag-deploy enable`) (see Update Deployments)

### Image-Only Deploy

Deploy only Docker image, skip DAG sync:

```bash
astro deploy <DEPLOYMENT_ID> --image
```

Use when:
- Only dependencies changed
- Dockerfile or requirements updated
- No DAG changes

### Force Deploy

Bypass safety checks and deploy:

```bash
astro deploy <DEPLOYMENT_ID> --force
```

**Caution**: Skips validation that could prevent broken deployments.

---

## Deployment API Tokens

Manage API tokens for programmatic access to deployments:

```bash
# List tokens for a deployment
astro deployment token list --deployment-id <DEPLOYMENT_ID>

# Create a new token
astro deployment token create \
  --deployment-id <DEPLOYMENT_ID> \
  --name "CI/CD Pipeline" \
  --role DEPLOYMENT_ADMIN

# Create token with expiration
astro deployment token create \
  --deployment-id <DEPLOYMENT_ID> \
  --name "Temporary Access" \
  --role DEPLOYMENT_ADMIN \
  --expiry 30  # Days until expiration (0 = never expires)
```

**Roles**:
- `DEPLOYMENT_ADMIN`: Full access to deployment

**Note**: Token value is only shown at creation time. Store it securely.

---

## Common Workflows

### First-Time Production Deployment

```bash
# 1. Login
astro login

# 2. Switch to production workspace
astro workspace list
astro workspace switch <PROD_WORKSPACE_ID>

# 3. Create deployment
astro deployment create --name production --executor CeleryExecutor

# 4. Note the deployment ID, then deploy
astro deploy <DEPLOYMENT_ID>
```

### Iterative DAG Development

```bash
# 1. Enable fast deploys (one-time setup)
astro deployment update <DEPLOYMENT_ID> --dag-deploy enable

# 2. Make DAG changes locally

# 3. Deploy quickly
astro deploy <DEPLOYMENT_ID> --dags
```

### Promoting Code from Staging to Production

```bash
# 1. Deploy to staging first
astro workspace switch <STAGING_WORKSPACE_ID>
astro deploy <STAGING_DEPLOYMENT_ID>

# 2. Test in staging

# 3. Deploy same code to production
astro workspace switch <PROD_WORKSPACE_ID>
astro deploy <PROD_DEPLOYMENT_ID>
```

---

## Configuration Management

```bash
# View CLI configuration
astro config get

# Set configuration value
astro config set <KEY> <VALUE>

# Check CLI version
astro version

# Upgrade the CLI: there is no `astro upgrade` command; reinstall the CLI the way it was installed
# (for example `brew upgrade astro`)
```

---

## Tips

- Use `--dags` flag for fast iteration (seconds vs minutes)
- Always test in staging workspace before production
- Use `deployment inspect` to verify deployment health before deploying
- Deployment IDs are permanent, names can change
- Most commands work with deployment ID; `inspect` also accepts `--deployment-name`
- Enable DAG-only deploys (`--dag-deploy enable`) once per deployment for fast deploys
- Keep workspace context visible with `astro workspace list` (shows asterisk for current)

---

## Related Skills

- **troubleshooting-astro-deployments**: Investigate deployment issues, view logs, manage environment variables
- **managing-astro-local-env**: Manage local Airflow development environment
- **setting-up-astro-project**: Initialize and configure Astro projects
