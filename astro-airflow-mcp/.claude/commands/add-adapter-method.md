---
description: Add a new method to both Airflow adapters
argument-hint: [method-name]
---

Add method `$ARGUMENTS` to both V2 and V3 adapters.

## Steps

1. Add abstract method to `adapters/base.py`:

```python
@abstractmethod
def method_name(self, param: str) -> dict[str, Any]:
    pass
```

2. Implement in `adapters/airflow_v2.py`:

```python
def method_name(self, param: str) -> dict[str, Any]:
    return self._call(f"endpoint/{param}")
```

3. Implement in `adapters/airflow_v3.py`:

```python
def method_name(self, param: str) -> dict[str, Any]:
    return self._call(f"endpoint/{param}")
```

## Version Differences

| Feature | Airflow 2.x | Airflow 3.x |
|---------|-------------|-------------|
| API path | `/api/v1` | `/api/v2` |
| Assets | `datasets` | `assets` |
| DAG runs | `execution_date` | `logical_date` |

Normalize V2 responses to match V3 field names when they differ.
