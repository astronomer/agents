# cc-for-data Plugin Scaffolding Plan

## Overview

This document outlines the plan for building `cc-for-data` as a **dual-platform plugin** for both [Claude Code](https://claude.ai/claude-code) and [OpenCode](https://opencode.ai). The core functionality is implemented as shared MCP (Model Context Protocol) servers, with thin platform-specific wrappers for each CLI tool.

**Key Components:**
- **MCP Servers (Python)** - Shared core functionality for Jupyter kernel, data warehouse discovery, and Airflow integration
- **Claude Code Plugin** - Skills, commands, and hooks for Claude Code
- **OpenCode Plugin** - TypeScript hooks and tool wrappers for OpenCode

---

## Repository Architecture

```
cc-for-data/
├── mcp-servers/                        # SHARED - Python MCP servers (FastMCP)
│   ├── pyproject.toml                  # Monorepo Python package config
│   ├── src/
│   │   └── cc_for_data/
│   │       ├── __init__.py
│   │       ├── config.py               # Shared config loading
│   │       ├── jupyter/                # Jupyter kernel MCP server
│   │       │   ├── __init__.py
│   │       │   ├── server.py           # FastMCP server entry point
│   │       │   ├── kernel.py           # Kernel lifecycle management
│   │       │   └── tools.py            # execute_python, execute_sql, etc.
│   │       ├── warehouse/              # Warehouse discovery MCP server
│   │       │   ├── __init__.py
│   │       │   ├── server.py           # FastMCP server entry point
│   │       │   ├── connectors/         # Warehouse-specific connectors
│   │       │   │   ├── __init__.py
│   │       │   │   ├── base.py         # Abstract connector interface
│   │       │   │   ├── snowflake.py
│   │       │   │   ├── bigquery.py
│   │       │   │   ├── databricks.py
│   │       │   │   └── redshift.py
│   │       │   └── tools.py            # list_schemas, list_tables, etc.
│   │       └── airflow/                # Airflow MCP server
│   │           ├── __init__.py
│   │           ├── server.py           # FastMCP server entry point
│   │           └── tools.py            # list_dags, trigger_dag, etc.
│   └── tests/
│       └── ...
│
├── claude-code-plugin/                 # Claude Code platform wrapper
│   ├── .claude-plugin/
│   │   ├── plugin.json                 # Plugin manifest
│   │   └── marketplace.json            # For distribution
│   ├── commands/                       # Slash commands (markdown)
│   │   ├── explore.md                  # /cc-for-data:explore
│   │   ├── query.md                    # /cc-for-data:query
│   │   ├── dag.md                      # /cc-for-data:dag
│   │   └── connect.md                  # /cc-for-data:connect
│   ├── skills/                         # Agent skills (markdown)
│   │   ├── warehouse-exploration/
│   │   │   └── SKILL.md
│   │   ├── pipeline-authoring/
│   │   │   └── SKILL.md
│   │   └── data-quality/
│   │       └── SKILL.md
│   ├── hooks/
│   │   └── hooks.json                  # Auto-format SQL, validate DAGs
│   └── .mcp.json                       # MCP server registration
│
├── opencode-plugin/                    # OpenCode platform wrapper
│   ├── package.json                    # npm package for OpenCode
│   ├── tsconfig.json
│   ├── opencode.json                   # OpenCode config (MCP registration)
│   └── src/
│       ├── index.ts                    # Plugin entry point
│       ├── hooks.ts                    # Event hooks (tool.execute.*, session.*)
│       └── tools.ts                    # Optional convenience tool wrappers
│
├── config/
│   └── schema.json                     # JSON schema for config validation
├── scripts/
│   ├── install.sh                      # Cross-platform install script
│   └── dev-setup.sh                    # Development environment setup
├── README.md
└── PLAN.md
```

---

## Shared MCP Servers (Python)

All core functionality lives in Python MCP servers using [FastMCP](https://github.com/jlowin/fastmcp). These servers are consumed by both Claude Code and OpenCode.

### Why Python for MCP Servers?

| Factor | Python | TypeScript |
|--------|--------|------------|
| **Data engineering fit** | Excellent - native ecosystem | Moderate - wrapping Python libs |
| **Warehouse connectors** | First-class (snowflake-connector-python, google-cloud-bigquery) | Requires bridging |
| **Jupyter kernel** | Native - same runtime | Cross-language complexity |
| **FastMCP maturity** | Production-ready (2.13+) | Good but less data-focused |
| **Target audience** | Data engineers know Python | Less familiar |
| **MCP server examples** | Most database MCP servers are Python | Growing |

### MCP Server: Jupyter Kernel (`cc_for_data.jupyter`)

Manages a Jupyter kernel for executing Python and SQL code with persistent state.

**Tools:**
| Tool | Description |
|------|-------------|
| `start_kernel` | Start a new Jupyter kernel |
| `stop_kernel` | Stop the running kernel |
| `kernel_status` | Get kernel status (running, idle, busy) |
| `execute_python` | Execute Python code in the kernel |
| `execute_sql` | Execute SQL code (via active warehouse connection) |
| `get_variables` | List variables in kernel namespace |
| `clear_namespace` | Clear kernel namespace |

**Implementation:**
```python
from mcp.server.fastmcp import FastMCP
from jupyter_client import KernelManager

mcp = FastMCP("cc-for-data-jupyter")

@mcp.tool()
async def execute_python(code: str) -> str:
    """Execute Python code in the Jupyter kernel."""
    # Implementation using jupyter_client
    ...

@mcp.tool()
async def execute_sql(query: str, warehouse: str | None = None) -> str:
    """Execute SQL against the connected warehouse."""
    # Routes through kernel with active connection
    ...
```

**Key Design Decisions:**
- Use `jupyter_client` for kernel management (standard Jupyter protocol)
- Kernel persists for session duration (state preserved across tool calls)
- Pre-load common data science packages (pandas, numpy)
- SQL execution uses the warehouse connection established in the kernel

### MCP Server: Warehouse Discovery (`cc_for_data.warehouse`)

Provides tools for exploring data warehouse schemas across multiple platforms.

**Tools:**
| Tool | Description |
|------|-------------|
| `list_connections` | List configured warehouse connections |
| `connect` | Connect to a specific warehouse |
| `disconnect` | Disconnect from current warehouse |
| `list_schemas` | List schemas in connected warehouse |
| `list_tables` | List tables in a schema |
| `get_table_info` | Get column info, types, statistics |
| `get_table_sample` | Get sample rows from a table |
| `run_query` | Execute arbitrary SQL query |
| `get_query_plan` | Get execution plan for a query |

**Warehouse Connectors:**

```python
from abc import ABC, abstractmethod
from typing import Any

class WarehouseConnector(ABC):
    """Abstract base class for warehouse connectors."""

    @abstractmethod
    async def connect(self, config: dict) -> None: ...

    @abstractmethod
    async def list_schemas(self) -> list[str]: ...

    @abstractmethod
    async def list_tables(self, schema: str) -> list[dict]: ...

    @abstractmethod
    async def get_table_info(self, schema: str, table: str) -> dict: ...

    @abstractmethod
    async def execute(self, query: str) -> list[dict]: ...


class SnowflakeConnector(WarehouseConnector):
    """Snowflake connector using snowflake-connector-python."""
    ...

class BigQueryConnector(WarehouseConnector):
    """BigQuery connector using google-cloud-bigquery."""
    ...

class DatabricksConnector(WarehouseConnector):
    """Databricks connector using databricks-sql-connector."""
    ...

class RedshiftConnector(WarehouseConnector):
    """Redshift connector using redshift_connector."""
    ...
```

**Implementation:**
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cc-for-data-warehouse")

@mcp.tool()
async def list_schemas() -> list[str]:
    """List all schemas in the connected warehouse."""
    connector = get_active_connector()
    return await connector.list_schemas()

@mcp.tool()
async def get_table_info(schema: str, table: str) -> dict:
    """Get detailed information about a table including columns and statistics."""
    connector = get_active_connector()
    return await connector.get_table_info(schema, table)
```

### MCP Server: Airflow (`cc_for_data.airflow`)

Integration with Astro CLI / local Airflow development.

**Tools:**
| Tool | Description |
|------|-------------|
| `airflow_status` | Check if Airflow is running (Astro CLI) |
| `list_dags` | List DAGs in the Airflow instance |
| `get_dag` | Get DAG details and task structure |
| `trigger_dag` | Trigger a DAG run |
| `list_dag_runs` | List runs for a DAG |
| `get_task_logs` | Get logs for a task instance |
| `test_task` | Test a single task locally |
| `parse_dags` | Parse DAGs and check for errors |

**Implementation:**
```python
from mcp.server.fastmcp import FastMCP
import httpx

mcp = FastMCP("cc-for-data-airflow")

AIRFLOW_API = "http://localhost:8080/api/v1"

@mcp.tool()
async def list_dags() -> list[dict]:
    """List all DAGs in the Airflow instance."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AIRFLOW_API}/dags")
        return response.json()["dags"]

@mcp.tool()
async def trigger_dag(dag_id: str, conf: dict | None = None) -> dict:
    """Trigger a DAG run with optional configuration."""
    ...
```

---

## Claude Code Plugin

The Claude Code wrapper provides skills, commands, and hooks that leverage the shared MCP servers.

### Plugin Manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "cc-for-data",
  "version": "0.1.0",
  "description": "Data engineering plugin for Claude Code - warehouse exploration, pipeline authoring, and Airflow integration",
  "author": {
    "name": "Astronomer",
    "email": "support@astronomer.io"
  },
  "homepage": "https://github.com/astronomer/cc-for-data",
  "repository": "https://github.com/astronomer/cc-for-data",
  "keywords": ["data-engineering", "airflow", "snowflake", "bigquery", "jupyter", "astronomer"]
}
```

### MCP Registration (`.mcp.json`)

```json
{
  "mcpServers": {
    "cc-for-data-jupyter": {
      "command": "python",
      "args": ["-m", "cc_for_data.jupyter.server"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    },
    "cc-for-data-warehouse": {
      "command": "python",
      "args": ["-m", "cc_for_data.warehouse.server"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    },
    "cc-for-data-airflow": {
      "command": "python",
      "args": ["-m", "cc_for_data.airflow.server"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    }
  }
}
```

### Skills

#### Warehouse Exploration (`skills/warehouse-exploration/SKILL.md`)

```markdown
---
name: warehouse-exploration
description: Use this skill when the user wants to explore data in their warehouse, understand schema, find tables, or run ad-hoc queries.
allowed_tools:
  - mcp__cc-for-data-warehouse__*
  - mcp__cc-for-data-jupyter__execute_sql
---

When exploring a data warehouse:

1. **Start by understanding the context**
   - Ask which warehouse/connection to use if not specified
   - Check what schemas are available

2. **Navigate systematically**
   - List schemas → List tables → Get table info
   - Use sampling to understand data shape before large queries

3. **Query best practices**
   - Always use LIMIT for exploratory queries
   - Prefer COUNT(*) before SELECT * for large tables
   - Use query plans to understand performance

4. **Document findings**
   - Summarize schema structure when asked
   - Note data quality issues observed
   - Suggest follow-up explorations
```

#### Pipeline Authoring (`skills/pipeline-authoring/SKILL.md`)

```markdown
---
name: pipeline-authoring
description: Use this skill when the user wants to create, modify, or debug Airflow DAGs and data pipelines.
allowed_tools:
  - mcp__cc-for-data-airflow__*
  - mcp__cc-for-data-jupyter__execute_python
  - Write
  - Edit
  - Read
---

When authoring Airflow pipelines:

1. **Understand the requirements**
   - What data sources and destinations?
   - What schedule/triggers?
   - What dependencies between tasks?

2. **Follow Airflow best practices**
   - Use TaskFlow API (@task decorator) for Python tasks
   - Keep DAGs idempotent
   - Use XComs sparingly, prefer external storage for large data
   - Set appropriate retries and timeouts

3. **Testing workflow**
   - Parse DAGs to check for syntax errors
   - Test individual tasks before full runs
   - Check task logs for debugging

4. **Astro CLI integration**
   - Use `astro dev start` for local development
   - Use `astro dev pytest` for DAG tests
```

### Commands

#### `/cc-for-data:explore`

```markdown
---
description: Start an interactive data warehouse exploration session
---

I'll help you explore your data warehouse. Let me check your configured connections.

$ARGUMENTS

Use the warehouse discovery tools to:
1. List available connections
2. Connect to the specified warehouse (or ask which one)
3. Begin interactive exploration based on user goals
```

#### `/cc-for-data:query`

```markdown
---
description: Run an ad-hoc SQL query against your warehouse
---

Execute this SQL query against the connected warehouse:

```sql
$ARGUMENTS
```

Show the results in a readable format and offer to help analyze them.
```

#### `/cc-for-data:dag`

```markdown
---
description: Create or modify an Airflow DAG
---

Help me create or modify an Airflow DAG.

$ARGUMENTS

Follow the pipeline-authoring skill guidelines. If creating a new DAG, gather requirements first. If editing, understand the current structure before making changes.
```

---

## OpenCode Plugin

The OpenCode wrapper provides TypeScript hooks and tool configurations that leverage the same shared MCP servers.

### Package Configuration (`package.json`)

```json
{
  "name": "cc-for-data-opencode",
  "version": "0.1.0",
  "description": "Data engineering plugin for OpenCode",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch"
  },
  "dependencies": {
    "zod": "^3.22.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0"
  }
}
```

### OpenCode Config (`opencode.json`)

```json
{
  "mcp": {
    "servers": {
      "cc-for-data-jupyter": {
        "command": "python",
        "args": ["-m", "cc_for_data.jupyter.server"],
        "env": {
          "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
        }
      },
      "cc-for-data-warehouse": {
        "command": "python",
        "args": ["-m", "cc_for_data.warehouse.server"],
        "env": {
          "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
        }
      },
      "cc-for-data-airflow": {
        "command": "python",
        "args": ["-m", "cc_for_data.airflow.server"],
        "env": {
          "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
        }
      }
    }
  },
  "plugin": ["cc-for-data-opencode"]
}
```

### Plugin Implementation (`src/index.ts`)

```typescript
import type { PluginContext } from "opencode";

export const CCForDataPlugin = async ({ project, client, $ }: PluginContext) => {
  // Log plugin initialization
  client.app.log({
    level: "info",
    message: "cc-for-data plugin loaded"
  });

  return {
    // Hook: Log tool executions for debugging
    "tool.execute.before": async (event: { tool: string; args: unknown }) => {
      if (event.tool.startsWith("cc-for-data")) {
        client.app.log({
          level: "debug",
          message: `Executing ${event.tool}`,
          data: event.args
        });
      }
    },

    // Hook: Format SQL results nicely
    "tool.execute.after": async (event: { tool: string; result: unknown }) => {
      // Post-processing if needed
    },

    // Hook: Add data context to session compaction
    "session.compacted": async (event: { summary: string }) => {
      // Preserve warehouse connection state in compacted context
    }
  };
};
```

---

## Configuration

### Config File (`~/.cc-for-data/config.yaml`)

```yaml
# Warehouse connections
warehouses:
  production-snowflake:
    type: snowflake
    account: abc12345.us-east-1
    user: ${SNOWFLAKE_USER}
    password: ${SNOWFLAKE_PASSWORD}
    warehouse: COMPUTE_WH
    database: ANALYTICS
    role: ANALYST

  dev-bigquery:
    type: bigquery
    project: my-project-123
    credentials_file: ~/.config/gcloud/application_default_credentials.json
    location: US

  staging-databricks:
    type: databricks
    host: adb-1234567890.azuredatabricks.net
    http_path: /sql/1.0/warehouses/abc123
    token: ${DATABRICKS_TOKEN}

  local-redshift:
    type: redshift
    host: localhost
    port: 5439
    database: dev
    user: ${REDSHIFT_USER}
    password: ${REDSHIFT_PASSWORD}

# Default warehouse for queries
default_warehouse: production-snowflake

# Jupyter kernel settings
jupyter:
  python_path: /usr/local/bin/python3
  startup_script: |
    import pandas as pd
    import numpy as np
    pd.set_option('display.max_columns', None)
  packages:
    - pandas
    - numpy
    - sqlalchemy

# Airflow settings
airflow:
  dags_folder: ./dags
  astro_project_path: .
  api_url: http://localhost:8080/api/v1
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Set up Python monorepo with `pyproject.toml` (using `uv` or `poetry`)
- [ ] Implement shared config loading (`cc_for_data.config`)
- [ ] Create Jupyter kernel MCP server with basic tools
- [ ] Test MCP server standalone with `mcp dev`

### Phase 2: Warehouse Discovery
- [ ] Implement `WarehouseConnector` abstract base class
- [ ] Implement Snowflake connector
- [ ] Create warehouse discovery MCP server with tools
- [ ] Test end-to-end with Claude Code

### Phase 3: Claude Code Plugin
- [ ] Create Claude Code plugin structure
- [ ] Write warehouse exploration skill
- [ ] Write pipeline authoring skill
- [ ] Add slash commands
- [ ] Test with `claude --plugin-dir ./claude-code-plugin`

### Phase 4: Additional Warehouses
- [ ] Implement BigQuery connector
- [ ] Implement Databricks connector
- [ ] Implement Redshift connector
- [ ] Abstract common SQL patterns (INFORMATION_SCHEMA queries)

### Phase 5: Airflow Integration
- [ ] Create Airflow MCP server
- [ ] Integrate with Astro CLI detection
- [ ] Add DAG parsing and validation tools
- [ ] Extend pipeline authoring skill

### Phase 6: OpenCode Plugin
- [ ] Create OpenCode plugin structure
- [ ] Configure MCP servers in `opencode.json`
- [ ] Implement TypeScript hooks
- [ ] Test with OpenCode CLI

### Phase 7: Polish & Distribution
- [ ] Create Claude Code marketplace.json
- [ ] Publish Python package to PyPI (for MCP servers)
- [ ] Publish OpenCode plugin to npm
- [ ] Write comprehensive documentation
- [ ] Create demo/tutorial content

---

## Dependencies

### Python (MCP Servers)

```toml
[project]
name = "cc-for-data"
version = "0.1.0"
dependencies = [
    "mcp>=1.0.0",              # MCP SDK (includes FastMCP)
    "jupyter-client>=8.0.0",   # Jupyter kernel management
    "pyyaml>=6.0",             # Config file parsing
    "pydantic>=2.0",           # Data validation
    "httpx>=0.25.0",           # Async HTTP client (Airflow API)
]

[project.optional-dependencies]
snowflake = ["snowflake-connector-python>=3.0.0"]
bigquery = ["google-cloud-bigquery>=3.0.0"]
databricks = ["databricks-sql-connector>=3.0.0"]
redshift = ["redshift-connector>=2.0.0"]
all = [
    "cc-for-data[snowflake,bigquery,databricks,redshift]"
]

[project.scripts]
cc-for-data-jupyter = "cc_for_data.jupyter.server:main"
cc-for-data-warehouse = "cc_for_data.warehouse.server:main"
cc-for-data-airflow = "cc_for_data.airflow.server:main"
```

### TypeScript (OpenCode Plugin)

```json
{
  "dependencies": {
    "zod": "^3.22.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0"
  }
}
```

---

## Open Questions

1. **Kernel lifecycle**: Long-running kernel per session, or spin up/down on demand?
   - *Recommendation*: Long-running, with explicit `stop_kernel` tool for cleanup

2. **Connection sharing**: Should warehouse connections be shared between MCP servers?
   - *Recommendation*: Establish in Jupyter kernel, share connection string/pool

3. **Authentication**: Support OAuth for warehouses beyond config-based credentials?
   - *Recommendation*: Start with config-based, add OAuth later for BigQuery/Databricks

4. **Airflow MCP**: Reuse existing Astronomer Airflow MCP or build fresh?
   - *Recommendation*: Build fresh with same patterns, ensure consistency

5. **Distribution**: PyPI + npm, or single GitHub release with both?
   - *Recommendation*: PyPI for MCP servers (required for `python -m`), npm for OpenCode plugin, GitHub marketplace for Claude Code plugin

---

## Resources

- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [Claude Code Plugins](https://claude.ai/docs/claude-code/plugins)
- [OpenCode MCP Servers](https://opencode.ai/docs/mcp-servers/)
- [OpenCode Plugins](https://opencode.ai/docs/plugins/)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Astro CLI Documentation](https://www.astronomer.io/docs/astro/cli/overview)
