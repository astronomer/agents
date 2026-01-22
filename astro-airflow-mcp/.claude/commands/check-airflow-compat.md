---
description: Verify code works with both Airflow 2.x and 3.x
allowed-tools: Bash(grep:*), Bash(make test:*), Bash(make test-integration:*)
---

Check if recent code changes are compatible with both Airflow versions.

## Check for Issues

1. Look for hardcoded API paths outside adapters:
   !`grep -rn "api/v1\|api/v2" src/astro_airflow_mcp/*.py | grep -v adapters`

2. Check field normalization in adapters:
   !`grep -n "execution_date\|logical_date\|datasets\|assets" src/astro_airflow_mcp/adapters/*.py`

## Key Differences

| Airflow 2.x | Airflow 3.x |
|-------------|-------------|
| `/api/v1` | `/api/v2` |
| `execution_date` | `logical_date` |
| `datasets` | `assets` |
| Basic auth | OAuth2/JWT |

## Run Tests

```bash
make test
make test-integration-v2
make test-integration-v3
```
