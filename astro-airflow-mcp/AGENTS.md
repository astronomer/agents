# Agent Guidelines for astro-airflow-mcp

Guidelines for AI coding assistants contributing to this repository.

## Architecture

MCP server for Apache Airflow with adapter pattern for version compatibility:

```
src/astro_airflow_mcp/
├── server.py          # MCP tools, resources, prompts (FastMCP)
├── adapters/
│   ├── base.py        # Abstract adapter interface
│   ├── airflow_v2.py  # Airflow 2.x API (/api/v1)
│   └── airflow_v3.py  # Airflow 3.x API (/api/v2)
├── models.py          # Pydantic models (documentation/type reference)
└── plugin.py          # Airflow 3.x plugin integration
```

## Code Conventions

### HTTP Client

Use `httpx`, not `requests`. All HTTP calls should use `httpx.Client`:

```python
# Good
with httpx.Client(timeout=30.0) as client:
    response = client.get(url, headers=headers)

# Bad
response = requests.get(url, headers=headers)
```

### Adapter Pattern

All Airflow API calls go through adapters. Never call Airflow API directly from MCP tools:

```python
# Good - use adapter
adapter = _get_adapter()
data = adapter.list_dags(limit=100)

# Bad - direct API call
response = httpx.get(f"{url}/api/v2/dags")
```

When adding new API endpoints:
1. Add abstract method to `adapters/base.py`
2. Implement in both `airflow_v2.py` and `airflow_v3.py`
3. Handle API differences (field names, paths, availability)

### MCP Tools

Tools need descriptive docstrings for AI discovery:

```python
@mcp.tool()
def get_dag_details(dag_id: str) -> str:
    """Get detailed information about a specific DAG.

    Use this tool when the user asks about:
    - "Show me details for DAG X"
    - "What's the schedule for DAG Y?"

    Args:
        dag_id: The ID of the DAG

    Returns:
        JSON with DAG metadata
    """
```

### Error Handling

Adapters handle missing endpoints gracefully:

```python
try:
    return self._call("newEndpoint")
except NotFoundError:
    return self._handle_not_found(
        "newEndpoint",
        alternative="Use alternativeEndpoint instead"
    )
```

## Airflow Version Differences

| Feature | Airflow 2.x | Airflow 3.x |
|---------|-------------|-------------|
| API path | `/api/v1` | `/api/v2` |
| Auth | Basic auth | OAuth2/JWT |
| Assets | `datasets` | `assets` |
| DAG runs | `execution_date` | `logical_date` |

## Testing

- Mock adapters, not HTTP libraries
- Unit tests: `tests/`
- Integration tests: `tests/integration/` (require running Airflow)

```python
# Good - mock adapter
mock_adapter = mocker.Mock()
mock_adapter.list_dags.return_value = {"dags": [...]}
mocker.patch("astro_airflow_mcp.server._get_adapter", return_value=mock_adapter)

# Bad - mock HTTP library
mocker.patch("httpx.Client")
```

## Files to Know

- `server.py`: All MCP tools defined here
- `adapters/base.py`: Interface contract for both versions
- `models.py`: Type reference (not used for validation currently)
- `docker-compose.test.yml`: Test against real Airflow instances
