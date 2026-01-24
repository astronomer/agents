# agents

AI agent tooling for data engineering workflows. Extends code agents and IDEs like [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [Cursor](https://cursor.com) with specialized capabilities for working with Airflow and data warehouses.

Built by [Astronomer](https://www.astronomer.io/).

## Table of Contents

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Installation](#installation)
  - [Quick Start](#quick-start)
  - [Compatibility](#compatibility)
  - [Claude Code](#claude-code)
  - [Cursor](#cursor)
  - [Other MCP Clients](#other-mcp-clients)
- [Features](#features)
  - [MCP Server](#mcp-server)
  - [Skills](#skills)
  - [User Journeys](#user-journeys)
- [Configuration](#configuration)
  - [Warehouse Connections](#warehouse-connections)
  - [Airflow](#airflow)
- [Usage](#usage)
  - [Getting Started](#getting-started)
- [Development](#development)
  - [Local Development Setup](#local-development-setup)
  - [Adding Skills](#adding-skills)
- [Troubleshooting](#troubleshooting)
  - [Common Issues](#common-issues)
- [Contributing](#contributing)
- [License](#license)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Installation

### Quick Start

```bash
npx skills add astronomer/agents
```

This installs Astronomer skills into your project via [skills.sh](https://skills.sh). Works with Claude Code, Cursor, and other AI coding tools.

### Compatibility

**Skills:** Works with [25+ AI coding agents](https://github.com/vercel-labs/add-skill?tab=readme-ov-file#available-agents) including Claude Code, Cursor, VS Code (GitHub Copilot), Windsurf, Cline, and more.

**MCP Server:** Works with any [MCP-compatible client](https://modelcontextprotocol.io/clients) including Claude Desktop, VS Code, and others.

### Claude Code

```bash
# Add the marketplace and install the plugin
claude plugin marketplace add astronomer/agents
claude plugin install data@astronomer
```

The plugin includes the Airflow MCP server that runs via `uvx` from PyPI. Data warehouse queries are handled by the `analyzing-data` skill using a background Jupyter kernel.

### Cursor

Cursor supports both MCP servers and skills.

**MCP Server** - Click to install:

<a href="https://cursor.com/en-US/install-mcp?name=astro-airflow-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJhc3Ryby1haXJmbG93LW1jcCIsIi0tdHJhbnNwb3J0Iiwic3RkaW8iXX0"><img src="https://cursor.com/deeplink/mcp-install-dark.svg" alt="Add Airflow MCP to Cursor" height="32"></a>

**Skills** - Install to your project:

```bash
npx skills add astronomer/agents
```

This installs skills to `.cursor/skills/` in your project.

<details>
<summary>Manual MCP configuration</summary>

Add to `~/.cursor/mcp.json`:

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

<details>
<summary>Enable hooks (skill suggestions, session management)</summary>

Create `.cursor/hooks.json` in your project:

```json
{
  "version": 1,
  "hooks": {
    "beforeSubmitPrompt": [
      {
        "command": "$CURSOR_PROJECT_DIR/.cursor/skills/airflow/hooks/airflow-skill-suggester.sh",
        "timeout": 5
      }
    ],
    "stop": [
      {
        "command": "uv run $CURSOR_PROJECT_DIR/.cursor/skills/analyzing-data/scripts/cli.py stop",
        "timeout": 10
      }
    ]
  }
}
```

**What these hooks do:**
- `beforeSubmitPrompt`: Suggests data skills when you mention Airflow keywords
- `stop`: Cleans up kernel when session ends

</details>

### Other MCP Clients

For any MCP-compatible client (Claude Desktop, VS Code, etc.):

```bash
# Airflow MCP
uvx astro-airflow-mcp --transport stdio

# With remote Airflow
AIRFLOW_API_URL=https://your-airflow.example.com \
AIRFLOW_USERNAME=admin \
AIRFLOW_PASSWORD=admin \
uvx astro-airflow-mcp --transport stdio
```

## Features

The `data` plugin bundles an MCP server and skills into a single installable package.

### MCP Server

| Server | Description |
|--------|-------------|
| **[Airflow](https://github.com/astronomer/agents/tree/main/astro-airflow-mcp)** | Full Airflow REST API integration via [astro-airflow-mcp](https://github.com/astronomer/agents/tree/main/astro-airflow-mcp): DAG management, triggering, task logs, system health |

### Skills

#### Data Discovery & Analysis

| Skill | Description |
|-------|-------------|
| [init](./skills/init/) | Initialize schema discovery - generates `.astro/warehouse.md` for instant lookups |
| [analyzing-data](./skills/analyzing-data/) | SQL-based analysis to answer business questions (uses background Jupyter kernel) |
| [checking-freshness](./skills/checking-freshness/) | Check how current your data is |
| [profiling-tables](./skills/profiling-tables/) | Comprehensive table profiling and quality assessment |

#### Data Lineage

| Skill | Description |
|-------|-------------|
| [tracing-downstream-lineage](./skills/tracing-downstream-lineage/) | Analyze what breaks if you change something |
| [tracing-upstream-lineage](./skills/tracing-upstream-lineage/) | Trace where data comes from |

#### DAG Development

| Skill | Description |
|-------|-------------|
| [airflow](./skills/airflow/) | Main entrypoint - routes to specialized Airflow skills |
| [setting-up-astro-project](./skills/setting-up-astro-project/) | Initialize and configure new Astro/Airflow projects |
| [managing-astro-local-env](./skills/managing-astro-local-env/) | Manage local Airflow environment (start, stop, logs, troubleshoot) |
| [authoring-dags](./skills/authoring-dags/) | Create and validate Airflow DAGs with best practices |
| [testing-dags](./skills/testing-dags/) | Test and debug Airflow DAGs locally |
| [debugging-dags](./skills/debugging-dags/) | Deep failure diagnosis and root cause analysis |

#### Migration

| Skill | Description |
|-------|-------------|
| [migrating-airflow-2-to-3](./skills/migrating-airflow-2-to-3/) | Migrate DAGs from Airflow 2.x to 3.x |

### User Journeys

#### Data Analysis Flow

```
/data:init → /data:analyzing-data → /data:profiling-tables
                    ↓
            /data:checking-freshness
```

1. **Initialize** (`/data:init`) - One-time setup to generate `warehouse.md` with schema metadata
2. **Analyze** (`/data:analyzing-data`) - Answer business questions with SQL
3. **Profile** (`/data:profiling-tables`) - Deep dive into specific tables for statistics and quality
4. **Check freshness** (`/data:checking-freshness`) - Verify data is up to date before using

#### DAG Development Flow

```
/data:setting-up-astro-project → /data:authoring-dags → /data:testing-dags
           ↓                                                    ↓
/data:managing-astro-local-env                      /data:debugging-dags
```

1. **Setup** (`/data:setting-up-astro-project`) - Initialize project structure and dependencies
2. **Environment** (`/data:managing-astro-local-env`) - Start/stop local Airflow for development
3. **Author** (`/data:authoring-dags`) - Write DAG code following best practices
4. **Test** (`/data:testing-dags`) - Run DAGs and fix issues iteratively
5. **Debug** (`/data:debugging-dags`) - Deep investigation for complex failures

## Configuration

### Warehouse Connections

Configure data warehouse connections at `~/.astro/ai/config/warehouse.yml`:

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

Store credentials in `~/.astro/ai/config/.env`:

```bash
SNOWFLAKE_ACCOUNT=xyz12345
SNOWFLAKE_USER=myuser
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=your-passphrase-here  # Only required if using an encrypted private key
```

**Supported warehouses:** Snowflake.

### Airflow

The Airflow MCP auto-discovers your project when you run Claude Code from an Airflow project directory (contains `airflow.cfg` or `dags/` folder).

For remote instances, set environment variables:

| Variable | Description |
|----------|-------------|
| `AIRFLOW_API_URL` | Airflow webserver URL |
| `AIRFLOW_USERNAME` | Username |
| `AIRFLOW_PASSWORD` | Password |
| `AIRFLOW_AUTH_TOKEN` | Bearer token (alternative to username/password) |

## Usage

Skills are invoked automatically based on what you ask. You can also invoke them directly with `/data:<skill-name>`.

### Getting Started

1. **Initialize your warehouse** (recommended first step):
   ```
   /data:init
   ```
   This generates `.astro/warehouse.md` with schema metadata for faster queries.

2. **Ask questions naturally**:
   - "What tables contain customer data?"
   - "Show me revenue trends by product"
   - "Create a DAG that loads data from S3 to Snowflake daily"
   - "Why did my etl_pipeline DAG fail yesterday?"

## Development

See [CLAUDE.md](./CLAUDE.md) for plugin development guidelines.

### Local Development Setup

```bash
# Clone the repo
git clone https://github.com/astronomer/agents.git
cd agents

# Test with local plugin
claude --plugin-dir .

# Or install from local marketplace
claude plugin marketplace add .
claude plugin install data@astronomer
```

### Adding Skills

Create a new skill in `skills/<name>/SKILL.md` with YAML frontmatter:

```yaml
---
name: my-skill
description: When to invoke this skill
---

# Skill instructions here...
```

After adding skills, reinstall the plugin:
```bash
claude plugin uninstall data@astronomer && claude plugin install data@astronomer
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Skills not appearing | Reinstall plugin: `claude plugin uninstall data@astronomer && claude plugin install data@astronomer` |
| Warehouse connection errors | Check credentials in `~/.astro/ai/config/.env` and connection config in `warehouse.yml` |
| Airflow not detected | Ensure you're running from a directory with `airflow.cfg` or a `dags/` folder |

## Contributing

Contributions welcome! See [CLAUDE.md](./CLAUDE.md) for development guidelines.

## License

Apache 2.0

---

Made with :heart: by Astronomer
