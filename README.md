<p align="center">
  <img height="150" alt="apache-airflow" src="https://github.com/user-attachments/assets/9996b91c-8abb-46e5-920a-6dbfd27e8d7d" />
</p>

# Airflow MCP Server

[![CI](https://github.com/astronomer/astro-airflow-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/astronomer/astro-airflow-mcp/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Apache Airflow that provides AI assistants (like Claude, Cursor, etc.) with access to Airflow's REST API. Built with [FastMCP](https://github.com/jlowin/fastmcp).

## Features

- **MCP Tools** for accessing Airflow data:
  - DAG management (list, get details, get source code, stats, warnings)
  - Task management (list, get details, get task instances)
  - Pool management (list, get details)
  - Variable management (list, get specific variables)
  - Plugin and provider information
  - Configuration and version details

- **Dual deployment modes**:
  - **Standalone server**: Run as an independent MCP server
  - **Airflow plugin**: Integrate directly into Airflow 3.x webserver

- **Authentication support**: Bearer token authentication


## Installation

We recommend installing astro-airflow-mcp with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install astro-airflow-mcp
```

## Usage

### Running the Server

After installation, start the MCP server:

```bash
astro-airflow-mcp
```

By default, this will:
- Start an HTTP server on `localhost:8000`
- Connect to Airflow at `http://localhost:8080` (`astro dev start`)
- Expose MCP protocol endpoints at `http://localhost:8000/mcp`

The server provides a set of tools that AI assistants can use to interact with your Airflow instance through the REST API. No authentication is required by default, but you can configure it using environment variables or command-line flags (see [Configuration](#configuration)).

**Custom configuration:**

```bash
# Connect to a different Airflow instance
astro-airflow-mcp --airflow-url https://my-airflow.example.com --auth-token my_token

# Use a different port
astro-airflow-mcp --port 9000

# Use stdio mode (for Claude Desktop)
astro-airflow-mcp --transport stdio
```

### Using with MCP Clients

#### Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "astro-airflow-mcp",
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
      "command": "astro-airflow-mcp",
      "args": [
        "--transport",
        "stdio"
      ]
    }
  }
}
```

**Or connect to the standalone server endpoint**:

```json
{
  "mcpServers": {
    "airflow": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**Or connect to the Airflow plugin endpoint**:

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

### Quick Start

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

### Local Testing with Astro CLI

The easiest way to test the MCP server locally is with [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview):

```bash
# Start a local Airflow instance locally with an astro project (optional but recommended)
astro dev start

# In another terminal, run the MCP server
# It will automatically connect to http://localhost:8080
make run
```

The default configuration (`http://localhost:8080`) matches Astro CLI's default Airflow webserver URL, so `make run` works out of the box with no additional configuration needed.

## Configuration

All tools use a global configuration that can be set via:

1. **Command-line flags** (standalone mode):
   - `--airflow-url`: Airflow webserver URL
   - `--auth-token`: Bearer token for authentication

2. **Environment variables**:
   - `AIRFLOW_API_URL`: Airflow webserver URL
   - `AIRFLOW_AUTH_TOKEN`: Bearer token

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
