# Airflow MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Apache Airflow that provides AI assistants (like Claude, Cursor, etc.) with access to Airflow's REST API. Built with [FastMCP](https://github.com/jlowin/fastmcp).

## Features

- **19 MCP Tools** for accessing Airflow data:
  - DAG management (list, get details, get source code, stats, warnings)
  - Task management (list, get details, get task instances)
  - Pool management (list, get details)
  - Variable management (list, get specific variables)
  - Plugin and provider information
  - Configuration and version details

- **Dual deployment modes**:
  - **Standalone server**: Run as an independent MCP server
  - **Airflow plugin**: Integrate directly into Airflow 3.x webserver

- **Authentication support**: Bearer token and Basic auth

## Installation

### Standalone Mode

Install the package:

```bash
pip install -e .
# or with uv
uv pip install -e .
```

### Airflow Plugin Mode

Install with the plugin extras:

```bash
pip install -e ".[plugin]"
# or with uv
uv pip install -e ".[plugin]"
```

This includes Apache Airflow and FastAPI dependencies required for plugin integration.

## Usage

### Standalone Server

Run the MCP server directly:

```bash
make run
# or
uv run python -m airflow_mcp
```

With authentication (using environment variables):

```bash
export AIRFLOW_API_URL=http://localhost:8080
export AIRFLOW_AUTH_TOKEN=your_token
# or
export AIRFLOW_USERNAME=admin
export AIRFLOW_PASSWORD=admin

make run
```

Or pass authentication via command-line flags:

```bash
# Using bearer token
uv run python -m airflow_mcp --airflow-url http://localhost:8080 --auth-token YOUR_TOKEN

# Using basic auth
uv run python -m airflow_mcp --airflow-url http://localhost:8080 \
  --auth-username admin --auth-password admin
```

**Transport modes:**

The server uses stdio transport by default for MCP communication. For HTTP transport (useful for Claude Code), add `--transport http`:

```bash
uv run python -m airflow_mcp --transport http --host localhost --port 8000
```

With HTTP transport, the server will be available at `http://localhost:8000/mcp`.

### Airflow Plugin Mode

The plugin automatically integrates with Airflow 3.x when installed.

1. **Install in Airflow environment**:
   ```bash
   pip install -e ".[plugin]"
   ```

2. **Verify plugin is loaded**:
   ```bash
   airflow plugins
   ```

3. **Access the MCP endpoints**:
   - MCP protocol endpoint: `http://your-airflow:8080/mcp/v1`
   - Available at Airflow webserver startup

### Using with MCP Clients

#### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uv",
      "args": ["run", "python", "-m", "airflow_mcp"],
      "env": {
        "AIRFLOW_API_URL": "http://localhost:8080",
        "AIRFLOW_AUTH_TOKEN": "your_token"
      }
    }
  }
}
```

#### Cursor

Configure in Cursor's MCP settings:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uv",
      "args": ["run", "python", "-m", "airflow_mcp"]
    }
  }
}
```

Or point to the plugin endpoint:

```json
{
  "mcpServers": {
    "airflow": {
      "url": "http://localhost:8080/mcp/v1"
    }
  }
}
```

## Available Tools

The MCP server provides the following tools:

| Tool | Description |
|------|-------------|
| `list_dags` | Get all DAGs and their metadata |
| `get_dag_details` | Get detailed info about a specific DAG |
| `get_dag_source` | Get the source code of a DAG |
| `get_dag_stats` | Get DAG run statistics |
| `list_dag_warnings` | Get DAG import warnings |
| `list_tasks` | Get all tasks in a DAG |
| `get_task` | Get details about a specific task |
| `get_task_instance` | Get task instance execution details |
| `list_pools` | Get all resource pools |
| `get_pool` | Get details about a specific pool |
| `list_variables` | Get all Airflow variables |
| `get_variable` | Get a specific variable by key |
| `list_plugins` | Get installed Airflow plugins |
| `list_providers` | Get installed provider packages |
| `get_airflow_config` | Get Airflow configuration |
| `get_airflow_version` | Get Airflow version information |
| `list_dag_runs` | Get DAG run history |
| `get_dag_run` | Get specific DAG run details |
| `get_health` | Get Airflow health status |

## Development

Quick start:

```bash
# Setup development environment
make setup

# Run tests
make test

# Run all checks
make check

# Run pre-commit hooks
make pre-commit
```

## Configuration

All tools use a global configuration that can be set via:

1. **Command-line flags** (standalone mode):
   - `--airflow-url`: Airflow webserver URL
   - `--auth-token`: Bearer token for authentication
   - `--auth-username`: Username for Basic auth
   - `--auth-password`: Password for Basic auth

2. **Environment variables**:
   - `AIRFLOW_API_URL`: Airflow webserver URL
   - `AIRFLOW_AUTH_TOKEN`: Bearer token
   - `AIRFLOW_USERNAME`: Username for Basic auth
   - `AIRFLOW_PASSWORD`: Password for Basic auth

## Requirements

- Python 3.10+
- FastMCP 0.1.0+
- Requests 2.31.0+
- Apache Airflow 3.0.0+ (for plugin mode)
- FastAPI 0.100.0+ (for plugin mode)

## Architecture

The server is built using [FastMCP](https://github.com/jlowin/fastmcp), which provides:
- Native MCP protocol support (SSE + JSON-RPC)
- Easy integration with FastAPI applications
- Automatic tool registration via decorators

In standalone mode, it runs as an independent ASGI application. In plugin mode, it's mounted into Airflow's FastAPI webserver using Airflow 3.x's plugin system.

## Contributing

Contributions welcome! Please ensure:
- All tests pass (`make test`)
- Code passes linting (`make check`)
- Pre-commit hooks pass (`make pre-commit`)
