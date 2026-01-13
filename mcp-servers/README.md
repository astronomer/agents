# data-plugin

MCP servers for data engineering workflows. Built by [Astronomer](https://www.astronomer.io/).

## Overview

`data-plugin` provides Model Context Protocol (MCP) servers that extend AI coding assistants (Claude Code, OpenCode) with specialized capabilities for data practitioners.

## Features

### Jupyter Kernel (`data-jupyter`)

Execute Python code in a managed Jupyter kernel with persistent state.

**Tools:**
- `execute_python` - Execute Python code with timeout control
- `install_packages` - Install additional packages via uv
- `start_kernel` / `stop_kernel` / `restart_kernel` - Lifecycle control
- `kernel_status` - Get current kernel state

**Pre-installed packages:** polars, pandas, numpy, matplotlib, seaborn

## Installation

```bash
# Install with uv
uv pip install -e .

# Or with pip
pip install -e .
```

## Usage

### Run the Jupyter MCP Server

```bash
# Via module
python -m data_plugin.jupyter.server

# Or via installed script
data-jupyter
```

### Claude Code Integration

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "data-jupyter": {
      "command": "python",
      "args": ["-m", "data_plugin.jupyter.server"]
    }
  }
}
```

### OpenCode Integration

Add to your `opencode.json`:

```json
{
  "mcp": {
    "servers": {
      "data-jupyter": {
        "command": "python",
        "args": ["-m", "data_plugin.jupyter.server"]
      }
    }
  }
}
```

## Configuration

The plugin uses the Astro CLI AI config directory (`~/.astro/ai/config/`).

### Warehouse Configuration (`~/.astro/ai/config/warehouse.yml`)

```yaml
my-warehouse:
  type: snowflake
  auth_type: private_key
  account: ${SNOWFLAKE_ACCOUNT}
  user: ${SNOWFLAKE_USER}
  private_key: ${SNOWFLAKE_PRIVATE_KEY}
  warehouse: COMPUTE_WH
  databases:
    - ANALYTICS
```

### Environment Secrets (`~/.astro/ai/config/.env`)

```bash
SNOWFLAKE_ACCOUNT=xyz.us-east-1
SNOWFLAKE_USER=my_user
SNOWFLAKE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----...
```

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (for environment management)

## License

Apache-2.0

