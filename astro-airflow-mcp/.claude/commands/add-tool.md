---
description: Add a new MCP tool to server.py
argument-hint: [tool-name]
---

Add a new MCP tool named `$ARGUMENTS` to `src/astro_airflow_mcp/server.py`.

## Steps

1. If the tool needs a new adapter method, run `/add-adapter-method` first.

2. Create internal `_impl` function that calls the adapter:

```python
def _tool_name_impl(param: str) -> str:
    """Internal implementation."""
    try:
        adapter = _get_adapter()
        data = adapter.method_name(param)
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)
```

3. Create the MCP tool with descriptive docstring:

```python
@mcp.tool()
def tool_name(param: str) -> str:
    """One-line description.

    Use this tool when the user asks about:
    - "Example query 1"
    - "Example query 2"

    Args:
        param: Description

    Returns:
        JSON with response data
    """
    return _tool_name_impl(param=param)
```

4. Add the tool to README.md tools table.
