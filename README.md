# agents

AI agent tooling for data engineering workflows. Built by [Astronomer](https://www.astronomer.io/).

This repo contains MCP servers, skills, and plugins that extend AI coding assistants (Claude Code, OpenCode) with specialized data engineering capabilities.

---

## Table of Contents

- [Features](#features)
  - [MCP Servers](#mcp-servers)
  - [Skills](#skills)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Claude Code](#claude-code)
  - [OpenCode](#opencode)
- [Configuration](#configuration)
  - [Warehouse Connections](#warehouse-connections)
  - [Airflow](#airflow)
- [Usage](#usage)
  - [Getting Started](#getting-started)
  - [Example Prompts](#example-prompts)
- [Development](#development)
  - [Repo Structure](#repo-structure)
  - [Adding Skills](#adding-skills)
  - [Testing Skills](#testing-skills)
- [License](#license)

---

## Features

The `data` plugin bundles everything in this repo into a single installable package for Claude Code or OpenCode.

### MCP Servers

| Server | Description |
|--------|-------------|
| **Airflow** | Full Airflow REST API integration via [astro-airflow-mcp](https://github.com/astronomer/astro-airflow-mcp): DAG management, triggering, task logs, system health |
| [**Data Warehouse**](./packages/data-warehouse/) | SQL queries against configured warehouses (Snowflake, BigQuery, etc.), schema discovery, persistent Python kernel for analysis |

### Skills

| Skill | Command | Description |
|-------|---------|-------------|
| [init-warehouse](./shared-skills/init-warehouse/) | `/data:init-warehouse` | Initialize schema discovery - generates `.astro/warehouse.md` for instant lookups |
| [analyzing-data](./shared-skills/analyzing-data/) | `/data:analyzing-data` | SQL-based analysis to answer business questions using cache and schema reference |
| [dag-authoring](./shared-skills/dag-authoring/) | `/data:dag-authoring` | Create and validate Airflow DAGs with best practices |
| [dag-testing](./shared-skills/dag-testing/) | `/data:dag-testing` | Test and debug Airflow DAGs locally |
| [debug-dag](./shared-skills/debug-dag/) | `/data:debug-dag` | Debug failed DAG runs and find root causes |
| [discover-data](./shared-skills/discover-data/) | `/data:discover-data` | Discover what data exists for a concept or domain |
| [check-freshness](./shared-skills/check-freshness/) | `/data:check-freshness` | Check how current your data is |
| [profile-table](./shared-skills/profile-table/) | `/data:profile-table` | Comprehensive table profiling and quality assessment |
| [upstream-lineage](./shared-skills/upstream-lineage/) | `/data:upstream-lineage` | Trace upstream lineage - where does this data come from? |
| [downstream-lineage](./shared-skills/downstream-lineage/) | `/data:downstream-lineage` | Analyze downstream dependencies - what breaks if I change this? |
| [astro-project-setup](./shared-skills/astro-project-setup/) | `/data:astro-project-setup` | Initialize and configure new Astro/Airflow projects |
| [astro-local-env](./shared-skills/astro-local-env/) | `/data:astro-local-env` | Manage local Airflow environment (start, stop, logs, troubleshoot) |
| [airflow-2-to-3-migration](./shared-skills/airflow-2-to-3-migration/) | `/data:airflow-2-to-3-migration` | Migrate DAGs from Airflow 2.x to 3.x |

---

## Installation

> **Note:** These instructions require cloning the repo locally. We're working on simpler installation via a published package.

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI (v1.0.33+) or [OpenCode](https://opencode.ai)
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

---

## Configuration

### Warehouse Connections

Configure data warehouse connections at `~/.astro/ai/config/warehouse.yml`:

```yaml
my_warehouse:
  type: snowflake
  account: ${SNOWFLAKE_ACCOUNT}
  user: ${SNOWFLAKE_USER}
  private_key_path: ~/.ssh/snowflake_key.p8
  warehouse: COMPUTE_WH
  role: ANALYST
  databases:
    - ANALYTICS
    - RAW
```

Store credentials in `~/.astro/ai/config/.env`:

```bash
SNOWFLAKE_ACCOUNT=xyz12345.us-east-1
SNOWFLAKE_USER=myuser
```

**Supported warehouses:** Snowflake, BigQuery, Databricks, Redshift.

### Airflow

The Airflow MCP auto-discovers your project when you run Claude Code from an Airflow project directory (contains `airflow.cfg` or `dags/` folder).

---

## Usage

Once installed, skills are invoked automatically based on what you ask. You can also invoke them directly:

```
/data:init-warehouse     # Initialize schema discovery (run once per project)
/data:analyzing-data     # Analyze data with SQL
/data:dag-authoring      # Start guided DAG creation
/data:discover-data      # Discover available data
/data:debug-dag          # Debug a failed DAG run
```

### Getting Started

1. **Initialize your warehouse** (recommended first step):
   ```
   /data:init-warehouse
   ```
   This generates `.astro/warehouse.md` with schema metadata and offers to add a Quick Reference to your CLAUDE.md for fastest query performance.

2. **Ask questions naturally**:
   - "What tables contain customer data?"
   - "Who uses HITLOperator the most?"
   - "Show me ARR trends by product"

3. **Work with Airflow**:
   - "Create a DAG that loads data from S3 to Snowflake daily"
   - "Why did my etl_pipeline DAG fail yesterday?"
   - "Test my DAG locally"

---

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

---

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

---

## Contributing

We welcome contributions! Please see [CLAUDE.md](./CLAUDE.md) for development guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `make install` to test locally
5. Submit a pull request

---

## License

Apache 2.0

---

Made with ❤️ by Astronomer
