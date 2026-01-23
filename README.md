# agents

AI agent tooling for data engineering workflows. Extends AI coding assistants like [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [Cursor](https://cursor.com) with specialized capabilities for working with Airflow and data warehouses.

Built by [Astronomer](https://www.astronomer.io/).

## Table of Contents

- [Installation](#installation)
- [Features](#features)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Installation

### Quick Start

```bash
npx skills add astronomer/agents
```

This installs Astronomer skills into your project via [skills.sh](https://skills.sh). Works with Claude Code, Cursor, and other AI coding tools.

### Compatibility

| Client | MCP Server | Skills |
|--------|------------|--------|
| Claude Code | Yes | Yes (13 skills) |
| Cursor | Yes | Yes (via Claude Code) |
| VS Code (Cline) | Yes | No |
| Claude Desktop | Yes | No |

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

**Skills** - Cursor auto-discovers skills from Claude Code plugins:

1. Install the Claude Code plugin (see above)
2. Open Cursor Settings > **Features** > **Claude Code**
3. Enable **"Include third-party skills"**

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

### VS Code / Cline

VS Code with Cline supports MCP servers (not skills).

<a href="https://insiders.vscode.dev/redirect?url=vscode://ms-vscode.vscode-mcp/install?%7B%22name%22%3A%22astro-airflow-mcp%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22astro-airflow-mcp%22%2C%22--transport%22%2C%22stdio%22%5D%7D"><img src="https://img.shields.io/badge/VS_Code-Install_Airflow_MCP-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white" alt="Install in VS Code" height="32"></a>

<details>
<summary>Manual configuration</summary>

Add to `.vscode/mcp.json`:

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

### Claude Desktop

Claude Desktop supports MCP servers (not skills).

Add to your config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

### Generic MCP Clients

For any MCP-compatible client:

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
| [initializing-warehouse](./skills/initializing-warehouse/) | Initialize schema discovery - generates `.astro/warehouse.md` for instant lookups |
| [analyzing-data](./skills/analyzing-data/) | SQL-based analysis to answer business questions (uses background Jupyter kernel) |
| [checking-freshness](./skills/checking-freshness/) | Check how current your data is |
| [discovering-data](./skills/discovering-data/) | Discover what data exists for a concept or domain |
| [profiling-tables](./skills/profiling-tables/) | Comprehensive table profiling and quality assessment |

#### Data Lineage

| Skill | Description |
|-------|-------------|
| [tracing-downstream-lineage](./skills/tracing-downstream-lineage/) | Analyze what breaks if you change something |
| [tracing-upstream-lineage](./skills/tracing-upstream-lineage/) | Trace where data comes from |

#### DAG Development

| Skill | Description |
|-------|-------------|
| [managing-astro-local-env](./skills/managing-astro-local-env/) | Manage local Airflow environment (start, stop, logs, troubleshoot) |
| [setting-up-astro-project](./skills/setting-up-astro-project/) | Initialize and configure new Astro/Airflow projects |
| [authoring-dags](./skills/authoring-dags/) | Create and validate Airflow DAGs with best practices |
| [debugging-dags](./skills/debugging-dags/) | Debug failed DAG runs and find root causes |
| [testing-dags](./skills/testing-dags/) | Test and debug Airflow DAGs locally |

#### Migration

| Skill | Description |
|-------|-------------|
| [migrating-airflow-2-to-3](./skills/migrating-airflow-2-to-3/) | Migrate DAGs from Airflow 2.x to 3.x |

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
   /data:initializing-warehouse
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
