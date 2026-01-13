# data Plugin Scaffolding Plan

## Overview

`data` is a **dual-platform plugin** for [Claude Code](https://claude.ai/claude-code) and [OpenCode](https://opencode.ai) that provides AI-assisted data engineering workflows. It bundles MCP servers for Jupyter kernel execution, data warehouse discovery, and Airflow integration.

**Key Insight**: MCP servers are distributed via PyPI and run with `uvx` (no installation required). The plugin just configures which servers to use.

---

## Architecture

```
data-ai-plugins/
├── packages/                           # MCP servers (PyPI packages)
│   ├── data-jupyter/                   # Jupyter kernel MCP server
│   │   ├── pyproject.toml
│   │   └── src/data_jupyter/
│   │       ├── __init__.py
│   │       ├── __main__.py
│   │       ├── server.py               # FastMCP server
│   │       └── kernel.py               # Kernel lifecycle
│   └── data-warehouse/                 # Warehouse discovery MCP server
│       ├── pyproject.toml
│       └── src/data_warehouse/
│           ├── __init__.py
│           ├── __main__.py
│           ├── server.py               # FastMCP server
│           └── connectors/
│               ├── base.py
│               ├── snowflake.py
│               ├── bigquery.py
│               ├── databricks.py
│               └── redshift.py
│
├── claude-code-plugin/                 # Claude Code plugin
│   ├── .claude-plugin/
│   │   ├── plugin.json                 # Plugin manifest
│   │   └── marketplace.json            # Distribution config
│   ├── .mcp.json                       # MCP server registration
│   ├── commands/                       # Slash commands
│   │   ├── explore.md
│   │   ├── query.md
│   │   └── dag.md
│   └── skills/                         # Agent skills
│       ├── warehouse-exploration/
│       │   └── SKILL.md
│       └── pipeline-authoring/
│           └── SKILL.md
│
├── opencode-plugin/                    # OpenCode plugin
│   ├── package.json
│   ├── opencode.json
│   └── src/index.ts
│
└── README.md
```

---

## MCP Servers

### Existing: astro-airflow-mcp

Already published to PyPI. Provides Airflow REST API integration.

```bash
uvx astro-airflow-mcp --transport stdio
```

**Tools**: `list_dags`, `get_dag_details`, `trigger_dag`, `get_task_logs`, `explore_dag`, `diagnose_dag_run`, `get_system_health`, etc.

### New: data-jupyter

Manages a Jupyter kernel for executing Python and SQL code.

```bash
uvx data-jupyter --transport stdio
```

**Tools:**
| Tool | Description |
|------|-------------|
| `start_kernel` | Start a new Jupyter kernel |
| `stop_kernel` | Stop the running kernel |
| `execute_python` | Execute Python code |
| `execute_sql` | Execute SQL via active connection |
| `get_variables` | List kernel namespace variables |

**Implementation Pattern** (following astro-airflow-mcp):
```python
from fastmcp import FastMCP

mcp = FastMCP("data-jupyter")

@mcp.tool()
def execute_python(code: str) -> str:
    """Execute Python code in the Jupyter kernel."""
    ...
```

### New: data-warehouse

Warehouse discovery and query execution.

```bash
uvx data-warehouse --transport stdio
```

**Tools:**
| Tool | Description |
|------|-------------|
| `list_connections` | List configured warehouses |
| `connect` | Connect to a warehouse |
| `list_schemas` | List schemas |
| `list_tables` | List tables in schema |
| `get_table_info` | Get column info and stats |
| `run_query` | Execute SQL query |
| `explore_schema` | Consolidated schema exploration |

---

## Claude Code Plugin

### Plugin Manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "data",
  "version": "0.1.0",
  "description": "Data engineering plugin - warehouse exploration, pipeline authoring, Airflow integration",
  "author": {
    "name": "Astronomer",
    "email": "support@astronomer.io"
  },
  "homepage": "https://github.com/astronomer/data-ai-plugins",
  "repository": "https://github.com/astronomer/data-ai-plugins",
  "keywords": ["data-engineering", "airflow", "snowflake", "bigquery", "jupyter", "astronomer"]
}
```

### MCP Registration (`.mcp.json`)

```json
{
  "mcpServers": {
    "data-jupyter": {
      "command": "uvx",
      "args": ["data-jupyter", "--transport", "stdio"],
      "env": {
        "ASTRO_AI_CONFIG": "~/.astro/ai/config/"
      }
    },
    "data-warehouse": {
      "command": "uvx",
      "args": ["data-warehouse", "--transport", "stdio"],
      "env": {
        "ASTRO_AI_CONFIG": "~/.astro/ai/config/"
      }
    },
    "airflow": {
      "command": "uvx",
      "args": ["astro-airflow-mcp", "--transport", "stdio"]
    }
  }
}
```

### Skills

Skills teach Claude how to use the tools effectively.

**Warehouse Exploration** (`skills/warehouse-exploration/SKILL.md`):
- When to explore schemas
- How to navigate systematically
- Query best practices (LIMIT, sampling)

**Pipeline Authoring** (`skills/pipeline-authoring/SKILL.md`):
- TaskFlow API patterns
- DAG best practices
- Testing workflow with Astro CLI

### Commands

Slash commands for common workflows:
- `/data:explore` - Start warehouse exploration
- `/data:query` - Run ad-hoc SQL
- `/data:dag` - Create/edit Airflow DAG

---

## Configuration

Uses existing Astro CLI config directory (`~/.astro/ai/config/`).

### Directory Structure

```
~/.astro/ai/
├── config/
│   ├── warehouse.yml    # Warehouse connections
│   └── .env             # Secrets
├── kernel_venv/         # Jupyter kernel virtualenv
└── sessions/            # Session history
```

### Warehouse Config (`~/.astro/ai/config/warehouse.yml`)

```yaml
dwh:
  type: snowflake
  auth_type: private_key
  account: ${SNOWFLAKE_ACCOUNT}
  user: ${SNOWFLAKE_USER}
  private_key: ${SNOWFLAKE_PRIVATE_KEY}
  warehouse: COMPUTE_WH
  role: ANALYST
  databases:
    - ANALYTICS
    - RAW
```

---

## Implementation Phases

### Phase 1: Plugin Shell (Current)
- [x] Create Claude Code plugin structure
- [x] Add astro-airflow-mcp to .mcp.json
- [x] Create initial skills and commands
- [ ] Test plugin with `claude --plugin-dir ./claude-code-plugin`

### Phase 2: data-warehouse MCP Server
- [ ] Create package structure
- [ ] Implement Snowflake connector
- [ ] Create discovery tools
- [ ] Publish to PyPI
- [ ] Update plugin to use published package

### Phase 3: data-jupyter MCP Server
- [ ] Create package structure
- [ ] Implement kernel lifecycle
- [ ] Create execution tools
- [ ] Publish to PyPI
- [ ] Update plugin to use published package

### Phase 4: Additional Warehouses
- [ ] BigQuery connector
- [ ] Databricks connector
- [ ] Redshift connector

### Phase 5: OpenCode Plugin
- [ ] Create OpenCode plugin structure
- [ ] Configure MCP servers
- [ ] Test with OpenCode CLI

### Phase 6: Distribution
- [ ] Create Claude Code marketplace.json
- [ ] Publish to Astronomer marketplace
- [ ] Documentation and tutorials

---

## Distribution

### MCP Servers (PyPI)

```bash
# Users run directly with uvx (no install needed)
uvx data-jupyter --transport stdio
uvx data-warehouse --transport stdio
uvx astro-airflow-mcp --transport stdio
```

### Claude Code Plugin

```bash
# Add Astronomer marketplace
/plugin marketplace add astronomer/data-ai-plugins

# Install plugin
/plugin install data@astronomer
```

### OpenCode Plugin

```bash
# Add to opencode.json
bun add @astronomer/data-opencode
```

---

## Resources

- [astro-airflow-mcp](https://github.com/astronomer/astro-airflow-mcp) - Reference implementation
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [Claude Code Plugins](https://claude.ai/docs/claude-code/plugins)
- [OpenCode Plugins](https://opencode.ai/docs/plugins/)
