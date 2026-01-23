# Data Warehouse MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PyPI - Version](https://img.shields.io/pypi/v/astro-dwh-mcp.svg?color=blue)](https://pypi.org/project/astro-dwh-mcp)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/astronomer/agents/blob/main/LICENSE)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for data warehouse operations. Execute SQL queries, explore schemas, and run Python analysis against Snowflake, BigQuery, Databricks, and Redshift.

## Quickstart

### IDEs

<a href="https://insiders.vscode.dev/redirect?url=vscode://ms-vscode.vscode-mcp/install?%7B%22name%22%3A%22astro-dwh-mcp%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22astro-dwh-mcp%22%5D%7D"><img src="https://img.shields.io/badge/VS_Code-Install_Server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white" alt="Install in VS Code" height="32"></a>
<a href="https://cursor.com/en-US/install-mcp?name=astro-dwh-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJhc3Ryby1kd2gtbWNwIl19"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add to Cursor" height="32"></a>

<details>
<summary>Manual configuration</summary>

Add to your MCP settings (Cursor: `~/.cursor/mcp.json`, VS Code: `.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "warehouse": {
      "command": "uvx",
      "args": ["astro-dwh-mcp"]
    }
  }
}
```

</details>

### CLI Tools

<details>
<summary>Claude Code</summary>

```bash
claude mcp add warehouse -- uvx astro-dwh-mcp
```

</details>

<details>
<summary>Gemini CLI</summary>

```bash
gemini mcp add warehouse -- uvx astro-dwh-mcp
```

</details>

### Desktop Apps

<details>
<summary>Claude Desktop</summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "warehouse": {
      "command": "uvx",
      "args": ["astro-dwh-mcp"]
    }
  }
}
```

</details>

## Configuration

The server requires warehouse credentials at `~/.astro/ai/config/warehouse.yml`:

```yaml
my_warehouse:
  type: snowflake
  account: ${SNOWFLAKE_ACCOUNT}
  user: ${SNOWFLAKE_USER}
  auth_type: private_key
  private_key_path: ~/.ssh/snowflake_key.p8
  private_key_passphrase: ${SNOWFLAKE_PRIVATE_KEY_PASSPHRASE}
  warehouse: COMPUTE_WH
  role: ANALYST
  databases:
    - ANALYTICS
    - RAW
```

Store secrets in `~/.astro/ai/config/.env`:

```bash
SNOWFLAKE_ACCOUNT=xyz12345
SNOWFLAKE_USER=myuser
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=your-passphrase
```

**Supported warehouses:** Snowflake, BigQuery, Databricks, Redshift.

## Features

- **SQL Execution**: Run queries against configured data warehouses
- **Schema Discovery**: List databases, schemas, tables, and columns
- **Python Kernel**: Persistent Jupyter kernel for data analysis
- **Result Caching**: Query results saved as parquet files
- **Concept Learning**: Teach table mappings for faster future queries
- **Pattern Matching**: Save and reuse proven query strategies

## Available Tools

### SQL Tools

| Tool | Description |
|------|-------------|
| `run_sql` | Execute SQL query against the warehouse |
| `list_schemas` | List available schemas across databases |
| `list_tables` | List tables in a specific schema |
| `get_tables_info` | Get detailed column info for tables |

### Python Kernel Tools

| Tool | Description |
|------|-------------|
| `execute_python` | Run Python code in persistent kernel |
| `install_packages` | Install additional Python packages |
| `kernel_status` | Check kernel state |
| `restart_kernel` | Clear kernel state |

### Cache Tools

| Tool | Description |
|------|-------------|
| `lookup_concept` | Find table for business concept |
| `learn_concept` | Save concept → table mapping |
| `lookup_pattern` | Find proven query strategies |
| `learn_pattern` | Save successful query pattern |
| `cache_status` | View cache statistics |

## Development

```bash
# Setup development environment
uv sync --all-extras

# Run tests
uv run pytest

# Run the server locally
uv run astro-dwh-mcp
```
