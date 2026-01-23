# Airflow API Differences (v2 vs v3)

## Endpoint Paths

| Airflow 2.x | Airflow 3.x |
|-------------|-------------|
| `/api/v1/dags` | `/api/v2/dags` |
| `/api/v1/datasets` | `/api/v2/assets` |
| `/api/v1/dagRuns` | `/api/v2/dagRuns` |

## Field Name Changes

| Airflow 2.x | Airflow 3.x | Notes |
|-------------|-------------|-------|
| `execution_date` | `logical_date` | DAG run timing |
| `datasets` | `assets` | Data-aware scheduling |
| `consuming_dags` | `scheduled_dags` | Asset consumers |

## Authentication

| Airflow 2.x | Airflow 3.x |
|-------------|-------------|
| Basic auth | OAuth2/JWT |
| Username/password in header | Token from `/auth/token` |

## Endpoints Only in Airflow 3.x

- `dagStats` without required `dag_ids` parameter
- Enhanced task instance filtering

## Endpoints Changed in Airflow 3.x

- `dagSources/{dag_id}` - V3 uses dag_id directly, V2 needs file_token

## Handling Differences in Code

```python
# V2 adapter - normalize datasets to assets
def list_assets(self, ...) -> dict[str, Any]:
    data = self._call("datasets", ...)
    if "datasets" in data:
        data["assets"] = data.pop("datasets")
        for asset in data["assets"]:
            if "consuming_dags" in asset:
                asset["scheduled_dags"] = asset.pop("consuming_dags")
    return data

# V3 adapter - use native assets endpoint
def list_assets(self, ...) -> dict[str, Any]:
    return self._call("assets", ...)
```
