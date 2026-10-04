# astro local api Reference

Direct REST API access for Airflow endpoints not covered by high-level commands.

These are written for Astro CLI v2. On v1 (see "Astro CLI v1 or v2" in the airflow skill), write `af api` for `astro local api`; the flags below are the same, except where a `v1:` form is given.

| Target | v2 | v1 |
|---|---|---|
| This project's local Airflow | `astro local api <endpoint>` | `af api <endpoint>` |
| A deployment | `astro api airflow <endpoint> -d <link>` | `af instance use <name>`, then `af api <endpoint>` |

`astro api airflow` takes the same `-X`, `-F`, `--raw-field`, `-H`, and `-i` flags, but has no `--body` or `--root`: pass a body with `--input <file>` (`-` for stdin).

## Endpoint Discovery

```bash
# List all available endpoints
astro local api ls

# Filter endpoints by pattern. v1 `af api ls` prints paths with the `/api/v2`
# (or `/api/v1`) prefix: drop it when you pass a path to `af api`, which adds it
astro local api ls --filter variable
astro local api ls --filter xcom

# Get full OpenAPI spec (for detailed method/parameter info)
astro local api spec

# Get details for specific endpoint
astro local api spec | jq '.paths["/api/v2/variables"]'
```

## HTTP Methods

```bash
# GET (default) - retrieve resources
astro local api dags
astro local api dags/my_dag
astro local api dags -F limit=10 -F only_active=true

# POST - create resources
astro local api variables -X POST -F key=my_var --raw-field value="my value"

# PATCH - update resources
astro local api dags/my_dag -X PATCH -F is_paused=false

# DELETE - remove resources
astro local api variables/old_var -X DELETE
```

## Field Syntax

| Flag | Behavior | Use When |
|------|----------|----------|
| `-F key=value` | Auto-converts: `true`/`false` → bool, numbers → int/float, `null` → null | Most cases |
| `--raw-field key=value` | Keeps value as raw string | Values that look like numbers but should be strings |
| `--body '{}'` | Raw JSON body | Complex nested objects |
| `-F key=@file` | Read value from file | Large values, configs |

```bash
# Type conversion examples
astro local api dags -F limit=10 -F only_active=true
# Sends: params limit=10 (int), only_active=true (bool)

# Raw string (no conversion)
astro local api variables -X POST -F key=port --raw-field value=8080
# Sends: {"key": "port", "value": "8080"} (string, not int)
```

## Common Endpoints

### XCom Values
```bash
astro local api dags/my_dag/dagRuns/manual__2024-01-15/taskInstances/my_task/xcomEntries
```

### Event Logs / Audit Trail
```bash
astro local api eventLogs -F dag_id=my_dag -F limit=50
astro local api eventLogs -F event=trigger
```

### Backfills (Airflow 3+)
```bash
# Create backfill
astro local api backfills -X POST --body '{
  "dag_id": "my_dag",
  "from_date": "2024-01-01T00:00:00Z",
  "to_date": "2024-01-31T00:00:00Z"
}'

# List backfills
astro local api backfills -F dag_id=my_dag
```

### Task Instances for a Run
```bash
astro local api dags/my_dag/dagRuns/manual__2024-01-15/taskInstances
```

### Connections (passwords exposed)
```bash
# Warning: use 'astro local af connections list' (v1: 'af config connections') for output without passwords
astro local api connections
astro local api connections/my_conn
```

## Debugging

```bash
# Include HTTP status and headers
astro local api dags -i

# A path outside the API version prefix, given from the server root (Airflow 2's /health;
# Airflow 3 serves health inside the prefix, as monitor/health)
astro local api --root /health
# v1: af api health --raw
```

## When to Use astro local api

| Task | Use |
|------|-----|
| List/get DAGs, runs, tasks | `astro local af dags`, `astro local af runs`, `astro local af tasks` |
| Trigger and monitor runs | `astro local af runs trigger-wait` |
| Delete or clear runs | `astro local af runs delete`, `astro local af runs clear` |
| Diagnose failures | `astro local af runs diagnose` |
| XCom, event logs, backfills | `astro local api` |
| Create/update variables, connections | `astro local api` |
| Any endpoint not in high-level CLI | `astro local api` |
