# Adapter Implementation Patterns

## Basic Pattern

```python
# In base.py
@abstractmethod
def get_thing(self, thing_id: str) -> dict[str, Any]:
    """Get a thing by ID."""
    pass

# In airflow_v2.py and airflow_v3.py
def get_thing(self, thing_id: str) -> dict[str, Any]:
    return self._call(f"things/{thing_id}")
```

## Handling Missing Endpoints

```python
def new_feature(self, param: str) -> dict[str, Any]:
    try:
        return self._call(f"newFeature/{param}")
    except NotFoundError:
        return self._handle_not_found(
            "newFeature",
            alternative="This feature requires Airflow 3.x"
        )
```

## Field Normalization

When field names differ between versions, normalize in V2 to match V3:

```python
# V2 adapter
def get_dag_run(self, dag_id: str, run_id: str) -> dict[str, Any]:
    data = self._call(f"dags/{dag_id}/dagRuns/{run_id}")
    # Normalize execution_date to logical_date
    if "execution_date" in data and "logical_date" not in data:
        data["logical_date"] = data["execution_date"]
    return data
```

## POST/PATCH Operations

```python
def trigger_dag_run(self, dag_id: str, conf: dict | None = None) -> dict[str, Any]:
    json_body: dict[str, Any] = {}
    if conf:
        json_body["conf"] = conf
    return self._post(f"dags/{dag_id}/dagRuns", json_data=json_body)

def pause_dag(self, dag_id: str) -> dict[str, Any]:
    return self._patch(f"dags/{dag_id}", json_data={"is_paused": True})
```

## Password Filtering

Always filter passwords from connection data:

```python
def list_connections(self, ...) -> dict[str, Any]:
    data = self._call("connections", ...)
    return self._filter_passwords(data)  # Base class method
```

## Testing Adapters

```python
def test_new_method(self, mocker):
    adapter = AirflowV2Adapter("http://localhost:8080", "2.9.0")

    mock_response = mocker.Mock()
    mock_response.json.return_value = {"result": "data"}
    mock_response.status_code = 200

    mock_client = mocker.Mock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__ = mocker.Mock(return_value=mock_client)
    mock_client.__exit__ = mocker.Mock(return_value=False)

    mocker.patch("httpx.Client", return_value=mock_client)

    result = adapter.new_method("param")
    assert result == {"result": "data"}
```
