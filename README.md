# agents

AI agent tooling for data engineering workflows. Extends [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [Cursor](https://cursor.com), and [OpenCode](https://opencode.ai) with specialized capabilities for working with Airflow and data warehouses.

Built by [Astronomer](https://www.astronomer.io/).

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

The `data` plugin bundles MCP servers and skills into a single installable package.

### MCP Servers

| Server | Description |
|--------|-------------|
| **Airflow** | Full Airflow REST API integration via [astro-airflow-mcp](https://github.com/astronomer/astro-airflow-mcp): DAG management, triggering, task logs, system health |
| [**Data Warehouse**](./packages/data-warehouse/) | SQL queries against configured warehouses (Snowflake, BigQuery, etc.), schema discovery, persistent Python kernel for analysis |

### Skills

#### Setup & Configuration

| Skill | Description |
|-------|-------------|
| [initializing-warehouse](./shared-skills/initializing-warehouse/) | Initialize schema discovery - generates `.astro/warehouse.md` for instant lookups |
| [managing-astro-local-env](./shared-skills/managing-astro-local-env/) | Manage local Airflow environment (start, stop, logs, troubleshoot) |
| [setting-up-astro-project](./shared-skills/setting-up-astro-project/) | Initialize and configure new Astro/Airflow projects |

#### Data Discovery & Analysis

| Skill | Description |
|-------|-------------|
| [analyzing-data](./shared-skills/analyzing-data/) | SQL-based analysis to answer business questions |
| [checking-freshness](./shared-skills/checking-freshness/) | Check how current your data is |
| [discovering-data](./shared-skills/discovering-data/) | Discover what data exists for a concept or domain |
| [profiling-tables](./shared-skills/profiling-tables/) | Comprehensive table profiling and quality assessment |

#### Data Lineage

| Skill | Description |
|-------|-------------|
| [tracing-downstream-lineage](./shared-skills/tracing-downstream-lineage/) | Analyze what breaks if you change something |
| [tracing-upstream-lineage](./shared-skills/tracing-upstream-lineage/) | Trace where data comes from |

#### DAG Development

| Skill | Description |
|-------|-------------|
| [authoring-dags](./shared-skills/authoring-dags/) | Create and validate Airflow DAGs with best practices |
| [debugging-dags](./shared-skills/debugging-dags/) | Debug failed DAG runs and find root causes |
| [testing-dags](./shared-skills/testing-dags/) | Test and debug Airflow DAGs locally |

#### Migration

| Skill | Description |
|-------|-------------|
| [migrating-airflow-2-to-3](./shared-skills/migrating-airflow-2-to-3/) | Migrate DAGs from Airflow 2.x to 3.x |

## Installation

> **Note:** These instructions require cloning the repo locally. We're working on simpler installation via a published package.

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI (v1.0.33+), [OpenCode](https://opencode.ai), or [Cursor](https://cursor.com)
- [uv](https://docs.astral.sh/uv/) package manager
- [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) (for Airflow features)

### Claude Code

```bash
# Clone the repo
git clone https://github.com/astronomer/agents.git
cd agents

# Install local MCP servers
make install

# Add the marketplace and install the plugin
claude plugin marketplace add ./claude-code-plugin
claude plugin install data@astronomer
```

Or test without installing:
```bash
claude --plugin-dir ./claude-code-plugin
```

### OpenCode

```bash
# Clone and install
git clone https://github.com/astronomer/agents.git
cd agents
make install

# Run from the opencode directory
cd opencode
opencode
```

### Cursor

Cursor uses the same MCP configuration format as Claude Code. After following the Claude Code installation above, copy the MCP config to Cursor's location:

```bash
# Copy MCP config to Cursor (after Claude Code plugin install)
cp claude-code-plugin/.mcp.json .cursor/mcp.json
```

Alternatively, create a symlink to keep them in sync:
```bash
mkdir -p .cursor
ln -s ../claude-code-plugin/.mcp.json .cursor/mcp.json
```

> **Note:** Skills are not yet supported in Cursor, but MCP servers (Airflow, Data Warehouse) will work. [Cursor Docs](https://cursor.com/docs/context/skills)

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

**Supported warehouses:** Snowflake, BigQuery, Databricks, Redshift.

### Airflow

The Airflow MCP auto-discovers your project when you run Claude Code from an Airflow project directory (contains `airflow.cfg` or `dags/` folder).

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

### Adding Skills

Create a new skill in `shared-skills/<name>/SKILL.md` with YAML frontmatter:

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

### Testing Skills

The repo includes a testing framework for iterating on skills without hitting real warehouses:

```bash
# Enable dry-run mode with mock responses
export DRY_RUN_MODE=true
export MOCK_RESPONSES_FILE=tests/mocks/hitl-mocks.yaml

# Test a query
claude --plugin-dir ./claude-code-plugin "Find HITL customers"
```

See [`docs/skill-testing.md`](./docs/skill-testing.md) for the full framework documentation including:
- DRY_RUN mode for mock responses
- Flow tracing and comparison
- Ralph Loop for automated iteration
- A/B testing configurations

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| MCP server not connecting | Run `make install` to ensure local packages are installed |
| Skills not appearing | Reinstall plugin: `claude plugin uninstall data@astronomer && claude plugin install data@astronomer` |
| Warehouse connection errors | Check credentials in `~/.astro/ai/config/.env` and connection config in `warehouse.yml` |
| Airflow not detected | Ensure you're running from a directory with `airflow.cfg` or a `dags/` folder |

### Verifying Installation

```bash
# Check MCP servers are available (OpenCode)
cd opencode && opencode mcp list

# Check skills are discovered (OpenCode)
cd opencode && opencode debug skill
```

## Contributing

Contributions welcome! See [CLAUDE.md](./CLAUDE.md) for development guidelines.

## License

Apache 2.0

---

Made with ❤️ by Astronomer
