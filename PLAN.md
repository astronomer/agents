# cc-for-data Plugin Scaffolding Plan

## Overview

This document outlines the plan for building `cc-for-data` as a Claude Code plugin. Based on the Claude Code plugin architecture, we'll leverage:

- **MCP Servers** for Jupyter kernel management, data warehouse discovery, and Airflow integration
- **Skills** for data engineering workflows (pipeline authoring, ad-hoc exploration)
- **Commands** for common data engineering tasks
- **Hooks** for automated formatting and validation

---

## Plugin Architecture

```
cc-for-data/
├── .claude-plugin/
│   ├── plugin.json              # Plugin manifest
│   └── marketplace.json         # For distribution
├── commands/                    # Slash commands
│   ├── explore.md               # /cc-for-data:explore - Start warehouse exploration
│   ├── query.md                 # /cc-for-data:query - Run ad-hoc query
│   ├── dag.md                   # /cc-for-data:dag - Create/edit Airflow DAG
│   └── connect.md               # /cc-for-data:connect - Connect to warehouse
├── skills/                      # Agent skills
│   ├── warehouse-exploration/
│   │   └── SKILL.md             # Ad-hoc data exploration skill
│   ├── pipeline-authoring/
│   │   └── SKILL.md             # Airflow DAG authoring skill
│   └── data-quality/
│       └── SKILL.md             # Data quality checks (future)
├── mcp-servers/                 # Custom MCP server implementations
│   ├── jupyter-kernel/          # Jupyter kernel manager
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts         # MCP server entry point
│   │       ├── kernel.ts        # Kernel lifecycle management
│   │       └── tools/
│   │           ├── execute-python.ts
│   │           └── execute-sql.ts
│   ├── warehouse-discovery/     # Data warehouse discovery tools
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   │       ├── index.ts         # MCP server entry point
│   │       ├── connectors/      # Warehouse-specific connectors
│   │       │   ├── snowflake.ts
│   │       │   ├── bigquery.ts
│   │       │   ├── databricks.ts
│   │       │   └── redshift.ts
│   │       └── tools/
│   │           ├── list-schemas.ts
│   │           ├── list-tables.ts
│   │           ├── get-table-info.ts
│   │           └── run-query.ts
│   └── airflow/                 # Airflow MCP (may already exist)
│       └── ...
├── hooks/
│   └── hooks.json               # Auto-format SQL, validate DAGs
├── config/
│   └── schema.json              # Config file JSON schema
├── scripts/
│   ├── install.sh               # Post-install setup
│   └── validate-config.sh       # Config validation
├── .mcp.json                    # MCP server registration
├── README.md
├── package.json                 # Root package for monorepo
└── tsconfig.json
```

---

## Component Details

### 1. Plugin Manifest (`.claude-plugin/plugin.json`)

```json
{
  "name": "cc-for-data",
  "version": "0.1.0",
  "description": "Claude Code plugin for data engineering workflows",
  "author": {
    "name": "Astronomer",
    "email": "support@astronomer.io"
  },
  "homepage": "https://github.com/astronomer/cc-for-data",
  "repository": "https://github.com/astronomer/cc-for-data",
  "keywords": ["data-engineering", "airflow", "snowflake", "bigquery", "jupyter"]
}
```

### 2. MCP Servers

#### A. Jupyter Kernel MCP Server

Manages a Jupyter kernel for executing Python and SQL code.

**Tools:**
| Tool | Description |
|------|-------------|
| `start_kernel` | Start a new Jupyter kernel |
| `stop_kernel` | Stop the running kernel |
| `kernel_status` | Get kernel status |
| `execute_python` | Execute Python code in the kernel |
| `execute_sql` | Execute SQL code (via sqlalchemy/connectors) |
| `get_variables` | List variables in kernel namespace |

**Implementation Notes:**
- Use `zeromq` for kernel communication (Jupyter protocol)
- Consider using `jupyter-kernel-gateway` or raw kernel management
- Kernel state persists across tool calls within a session
- Support for `ipykernel` with data science packages pre-loaded

#### B. Warehouse Discovery MCP Server

Provides tools for exploring data warehouse schemas.

**Tools:**
| Tool | Description |
|------|-------------|
| `list_connections` | List configured warehouse connections |
| `connect` | Connect to a specific warehouse |
| `list_schemas` | List schemas in connected warehouse |
| `list_tables` | List tables in a schema |
| `get_table_info` | Get column info, types, stats for a table |
| `get_table_sample` | Get sample rows from a table |
| `run_query` | Execute arbitrary SQL query |
| `get_query_plan` | Get execution plan for a query |

**Warehouse Connectors:**
- **Snowflake**: `snowflake-connector-python`
- **BigQuery**: `google-cloud-bigquery`
- **Databricks**: `databricks-sql-connector`
- **Redshift**: `redshift_connector`

**Implementation Notes:**
- Queries execute through the Jupyter kernel (shared connection state)
- Tools are wrappers around common SQL patterns (e.g., `INFORMATION_SCHEMA` queries)
- Connection pooling for efficiency
- Query result caching for repeated calls

#### C. Airflow MCP Server

Integration with Astro CLI / local Airflow.

**Tools:**
| Tool | Description |
|------|-------------|
| `list_dags` | List DAGs in the Airflow instance |
| `get_dag` | Get DAG details and structure |
| `trigger_dag` | Trigger a DAG run |
| `list_dag_runs` | List runs for a DAG |
| `get_task_logs` | Get logs for a task instance |
| `test_task` | Test a single task |
| `parse_dags` | Parse DAGs and check for errors |

**Implementation Notes:**
- Communicates with Airflow REST API (localhost when Astro CLI running)
- Falls back to CLI commands (`astro dev run`, `astro dev pytest`)
- Auto-detects Astro CLI running status

### 3. Skills

#### A. Warehouse Exploration Skill (`skills/warehouse-exploration/SKILL.md`)

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

#### B. Pipeline Authoring Skill (`skills/pipeline-authoring/SKILL.md`)

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

### 4. Commands

#### `/cc-for-data:explore` - Start warehouse exploration session

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

#### `/cc-for-data:query` - Run ad-hoc query

```markdown
---
description: Run an ad-hoc SQL query against your warehouse
---

Execute this SQL query against the connected warehouse:

```sql
$ARGUMENTS
```

Show the results and offer to help analyze them.
```

#### `/cc-for-data:dag` - Create or edit Airflow DAG

```markdown
---
description: Create or modify an Airflow DAG
---

Help me create or modify an Airflow DAG.

$ARGUMENTS

Follow the pipeline-authoring skill guidelines. If creating a new DAG, gather requirements first. If editing, understand the current structure before making changes.
```

### 5. Configuration

#### Config File Schema (`~/.cc-for-data/config.yaml`)

```yaml
# Warehouse connections
warehouses:
  production-snowflake:
    type: snowflake
    account: abc12345.us-east-1
    user: ${SNOWFLAKE_USER}  # Supports env var interpolation
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
```

### 6. MCP Server Registration (`.mcp.json`)

```json
{
  "mcpServers": {
    "cc-for-data-jupyter": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/jupyter-kernel/dist/index.js"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    },
    "cc-for-data-warehouse": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/warehouse-discovery/dist/index.js"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    },
    "cc-for-data-airflow": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/mcp-servers/airflow/dist/index.js"],
      "env": {
        "CC_FOR_DATA_CONFIG": "~/.cc-for-data/config.yaml"
      }
    }
  }
}
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Set up monorepo structure with TypeScript
- [ ] Create plugin manifest
- [ ] Implement basic config file loading
- [ ] Create Jupyter kernel MCP server with `execute_python` tool
- [ ] Test with `claude --plugin-dir ./`

### Phase 2: Warehouse Discovery
- [ ] Implement Snowflake connector
- [ ] Create discovery tools (list schemas, list tables, get table info)
- [ ] Add `execute_sql` tool that routes through Jupyter kernel
- [ ] Create warehouse exploration skill
- [ ] Add `/cc-for-data:explore` command

### Phase 3: Additional Warehouses
- [ ] Implement BigQuery connector
- [ ] Implement Databricks connector
- [ ] Implement Redshift connector
- [ ] Abstract common patterns across connectors

### Phase 4: Airflow Integration
- [ ] Integrate existing Airflow MCP (or build new)
- [ ] Create pipeline authoring skill
- [ ] Add `/cc-for-data:dag` command
- [ ] Add hooks for DAG validation

### Phase 5: Polish & Distribution
- [ ] Create marketplace.json for distribution
- [ ] Write comprehensive documentation
- [ ] Add installation scripts
- [ ] Create demo/tutorial content
- [ ] Publish to marketplace

---

## Technical Decisions

### Why TypeScript for MCP Servers?
- Official MCP SDK is TypeScript-first (`@modelcontextprotocol/sdk`)
- Better tooling and type safety
- Easy to bundle and distribute

### Why Jupyter Kernel vs Direct Execution?
- Persistent state across tool calls (loaded DataFrames, connections)
- Standard protocol with good library support
- Users familiar with Jupyter workflows
- Can extend to notebook integration later

### Why Config File vs Environment Variables?
- Multiple warehouse connections need structured config
- Environment variables can supplement for secrets
- Easier to manage and version (without secrets)

---

## Dependencies

### MCP Server Dependencies
```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "zeromq": "^6.0.0",
    "uuid": "^9.0.0",
    "yaml": "^2.3.0"
  }
}
```

### Python Dependencies (for Jupyter kernel)
```
ipykernel
pandas
numpy
sqlalchemy
snowflake-connector-python
google-cloud-bigquery
databricks-sql-connector
redshift_connector
```

---

## Open Questions

1. **Kernel management**: Should we use a long-running kernel per session, or spin up/down per command?
2. **Connection pooling**: Share connections across kernel and discovery tools, or keep separate?
3. **Authentication**: Support OAuth flows for warehouses, or just config-based credentials?
4. **Airflow MCP**: Reuse existing Astronomer Airflow MCP or build fresh?
5. **Distribution**: npm package, GitHub release, or Anthropic marketplace?
