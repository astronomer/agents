# Airflow MCP Server

[![CI](https://github.com/astronomer/astro-airflow-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/astronomer/astro-airflow-mcp/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI - Version](https://img.shields.io/pypi/v/astro-airflow-mcp.svg?color=blue)](https://pypi.org/project/astro-airflow-mcp)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/astronomer/astro-airflow-mcp/blob/main/LICENSE)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Apache Airflow that provides AI assistants with access to Airflow's REST API. Built with [FastMCP](https://github.com/jlowin/fastmcp).

## Quickstart

### IDEs

<a href="https://insiders.vscode.dev/redirect?url=vscode://ms-vscode.vscode-mcp/install?%7B%22name%22%3A%22astro-airflow-mcp%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22astro-airflow-mcp%22%2C%22--transport%22%2C%22stdio%22%5D%7D"><img src="https://img.shields.io/badge/VS_Code-Install_Server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white" alt="Install in VS Code" height="32"></a>
<a href="https://cursor.com/en-US/install-mcp?name=astro-airflow-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJhc3Ryby1haXJmbG93LW1jcCIsIi0tdHJhbnNwb3J0Iiwic3RkaW8iXX0"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add to Cursor" height="32"></a>

<details>
<summary>Manual configuration</summary>

Add to your MCP settings (Cursor: `~/.cursor/mcp.json`, VS Code: `.vscode/mcp.json`):

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uvx",
      "args": ["astro-airflow-mcp", "--transport", "stdio"]
    }
  }
}
```

</details>

### CLI Tools

<details>
<summary>Claude Code</summary>

```bash
claude mcp add airflow -- uvx astro-airflow-mcp --transport stdio
```

</details>

<details>
<summary>Gemini CLI</summary>

```bash
gemini mcp add airflow -- uvx astro-airflow-mcp --transport stdio
```

</details>

<details>
<summary>Codex CLI</summary>

```bash
codex mcp add airflow -- uvx astro-airflow-mcp --transport stdio
```

</details>

### Desktop Apps

<details>
<summary>Claude Desktop</summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uvx",
      "args": ["astro-airflow-mcp", "--transport", "stdio"]
    }
  }
}
```

</details>

### Other MCP Clients

<details>
<summary>Manual JSON Configuration</summary>

Add to your MCP configuration file:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uvx",
      "args": ["astro-airflow-mcp", "--transport", "stdio"]
    }
  }
}
```

Or connect to a running HTTP server: `"url": "http://localhost:8000/mcp"`

</details>

> **Note:** No installation required - `uvx` runs directly from PyPI. The `--transport stdio` flag is required because the server defaults to HTTP mode.

### Configuration

By default, the server connects to `http://localhost:8080` (Astro CLI default). Set environment variables for custom Airflow instances:

| Variable | Description |
|----------|-------------|
| `AIRFLOW_API_URL` | Airflow webserver URL |
| `AIRFLOW_USERNAME` | Username (Airflow 3.x uses OAuth2 token exchange) |
| `AIRFLOW_PASSWORD` | Password |
| `AIRFLOW_AUTH_TOKEN` | Bearer token (alternative to username/password) |

Example with auth (Claude Code):

```bash
claude mcp add airflow -e AIRFLOW_API_URL=https://your-airflow.example.com -e AIRFLOW_USERNAME=admin -e AIRFLOW_PASSWORD=admin -- uvx astro-airflow-mcp --transport stdio
```

## Features

- **Airflow 2.x and 3.x Support**: Automatic version detection with adapter pattern
- **MCP Tools** for accessing Airflow data:
  - DAG management (list, get details, get source code, stats, warnings, import errors, trigger, pause/unpause)
  - Task management (list, get details, get task instances, get logs)
  - Pool management (list, get details)
  - Variable management (list, get specific variables)
  - Connection management (list connections with credentials excluded)
  - Asset/Dataset management (unified naming across versions, data lineage)
  - Plugin and provider information
  - Configuration and version details
- **Consolidated Tools** for agent workflows:
  - `explore_dag`: Get comprehensive DAG information in one call
  - `diagnose_dag_run`: Debug failed DAG runs with task instance details
  - `get_system_health`: System overview with health, errors, and warnings
- **MCP Resources**: Static Airflow info exposed as resources (version, providers, plugins, config)
- **MCP Prompts**: Guided workflows for common tasks (troubleshooting, health checks, onboarding)
- **Dual deployment modes**:
  - **Standalone server**: Run as an independent MCP server
  - **Airflow plugin**: Integrate directly into Airflow 3.x webserver
- **Flexible Authentication**:
  - Bearer token (Airflow 2.x and 3.x)
  - Username/password with automatic OAuth2 token exchange (Airflow 3.x)
  - Basic auth (Airflow 2.x)


## Available Tools

### Consolidated Tools (Agent-Optimized)

| Tool | Description |
|------|-------------|
| `explore_dag` | Get comprehensive DAG info: metadata, tasks, recent runs, source code |
| `diagnose_dag_run` | Debug a DAG run: run details, failed task instances, logs |
| `get_system_health` | System overview: health status, import errors, warnings, DAG stats |

### Core Tools

| Tool | Description |
|------|-------------|
| `list_dags` | Get all DAGs and their metadata |
| `get_dag_details` | Get detailed info about a specific DAG |
| `get_dag_source` | Get the source code of a DAG |
| `get_dag_stats` | Get DAG run statistics (Airflow 3.x only) |
| `list_dag_warnings` | Get DAG import warnings |
| `list_import_errors` | Get import errors from DAG files that failed to parse |
| `list_dag_runs` | Get DAG run history |
| `get_dag_run` | Get specific DAG run details |
| `trigger_dag` | Trigger a new DAG run (start a workflow execution) |
| `pause_dag` | Pause a DAG to prevent new scheduled runs |
| `unpause_dag` | Unpause a DAG to resume scheduled runs |
| `list_tasks` | Get all tasks in a DAG |
| `get_task` | Get details about a specific task |
| `get_task_instance` | Get task instance execution details |
| `get_task_logs` | Get logs for a specific task instance execution |
| `list_pools` | Get all resource pools |
| `get_pool` | Get details about a specific pool |
| `list_variables` | Get all Airflow variables |
| `get_variable` | Get a specific variable by key |
| `list_connections` | Get all connections (credentials excluded for security) |
| `list_assets` | Get assets/datasets (unified naming across versions) |
| `list_plugins` | Get installed Airflow plugins |
| `list_providers` | Get installed provider packages |
| `get_airflow_config` | Get Airflow configuration |
| `get_airflow_version` | Get Airflow version information |

### MCP Resources

| Resource URI | Description |
|--------------|-------------|
| `airflow://version` | Airflow version information |
| `airflow://providers` | Installed provider packages |
| `airflow://plugins` | Installed Airflow plugins |
| `airflow://config` | Airflow configuration |

### MCP Prompts

| Prompt | Description |
|--------|-------------|
| `troubleshoot_failed_dag` | Guided workflow for diagnosing DAG failures |
| `daily_health_check` | Morning health check routine |
| `onboard_new_dag` | Guide for understanding a new DAG |

## Advanced Usage

### Running as Standalone Server

For HTTP-based integrations or connecting multiple clients to one server:

```bash
# Run server (HTTP mode is default)
uvx astro-airflow-mcp --airflow-url https://my-airflow.example.com --username admin --password admin
```

Connect MCP clients to: `http://localhost:8000/mcp`

### Airflow Plugin Mode

Install into your Airflow 3.x environment to expose MCP at `http://your-airflow:8080/mcp/v1`:

```bash
# Add to your Astro project
echo astro-airflow-mcp >> requirements.txt
```

### CLI Options

| Flag | Environment Variable | Default | Description |
|------|---------------------|---------|-------------|
| `--transport` | `MCP_TRANSPORT` | `stdio` | Transport mode (`stdio` or `http`) |
| `--host` | `MCP_HOST` | `localhost` | Host to bind to (HTTP mode only) |
| `--port` | `MCP_PORT` | `8000` | Port to bind to (HTTP mode only) |
| `--airflow-url` | `AIRFLOW_API_URL` | Auto-discovered or `http://localhost:8080` | Airflow webserver URL |
| `--airflow-project-dir` | `AIRFLOW_PROJECT_DIR` | `$PWD` | Astro project directory for auto-discovering Airflow URL from `.astro/config.yaml` |
| `--auth-token` | `AIRFLOW_AUTH_TOKEN` | `None` | Bearer token for authentication |
| `--username` | `AIRFLOW_USERNAME` | `None` | Username for authentication (Airflow 3.x uses OAuth2 token exchange) |
| `--password` | `AIRFLOW_PASSWORD` | `None` | Password for authentication |

## Architecture

The server is built using [FastMCP](https://github.com/jlowin/fastmcp) with an adapter pattern for Airflow version compatibility:

### Core Components

- **Adapters** (`adapters/`): Version-specific API implementations
  - `AirflowAdapter` (base): Abstract interface for all Airflow API operations
  - `AirflowV2Adapter`: Airflow 2.x API (`/api/v1`) with basic auth
  - `AirflowV3Adapter`: Airflow 3.x API (`/api/v2`) with OAuth2 token exchange
- **Version Detection**: Automatic detection at startup by probing API endpoints
- **Models** (`models.py`): Pydantic models for type-safe API responses

### Version Handling Strategy

1. **Major versions (2.x vs 3.x)**: Adapter pattern with runtime version detection
2. **Minor versions (3.1 vs 3.2)**: Runtime feature detection with graceful fallbacks
3. **New API parameters**: Pass-through `**kwargs` for forward compatibility

### Deployment Modes

- **Standalone**: Independent ASGI application with HTTP/SSE transport
- **Plugin**: Mounted into Airflow 3.x FastAPI webserver

## Development

```bash
# Setup development environment
make install-dev

# Run tests
make test

# Run all checks
make check

# Local testing with Astro CLI
astro dev start  # Start Airflow
make run         # Run MCP server (connects to localhost:8080)
```

## Contributing

Contributions welcome! Please ensure:
- All tests pass (`make test`)
- Code passes linting (`make check`)
- prek hooks pass (`make prek`)
