# agents

AI agent tooling for data engineering workflows. Built by [Astronomer](https://www.astronomer.io/).

This repo contains MCP servers, skills, and plugins that extend AI coding assistants (Claude Code, OpenCode) with specialized data engineering capabilities.

## data plugin

The `data` plugin bundles everything in this repo into a single installable package for Claude Code or OpenCode.

### Features

**MCP Servers:**
- **Airflow** - Full Airflow REST API integration via [astro-airflow-mcp](https://github.com/astronomer/astro-airflow-mcp): DAG management, triggering, task logs, system health
- **Data Warehouse** - SQL queries against configured warehouses (Snowflake, BigQuery, etc.), schema discovery, persistent Python kernel for analysis

**Skills:**
| Skill | Description |
|-------|-------------|
| `init-warehouse` | Initialize schema discovery - generates `.astro/warehouse.md` and optionally adds Quick Reference to CLAUDE.md |
| `data-analysis` | SQL-based analysis to answer business questions (uses CLAUDE.md Quick Reference + cache for fast lookups) |
| `dag-authoring` | Create and validate Airflow DAGs with best practices |
| `dag-testing` | Test and debug Airflow DAGs locally |
| `airflow-2-to-3-migration` | Migrate DAGs from Airflow 2.x to 3.x |
| `discover-data` | Discover what data exists for a concept or domain |
| `check-freshness` | Check how current your data is |
| `profile-table` | Comprehensive table profiling and quality assessment |
| `upstream-lineage` | Trace upstream lineage - where does this data come from? |
| `downstream-lineage` | Analyze downstream dependencies - what breaks if I change this? |
| `debug-dag` | Debug failed DAG runs and find root causes |

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

Supported warehouses: Snowflake, BigQuery, Databricks, Redshift.

### Airflow

The Airflow MCP auto-discovers your project when you run Claude Code from an Airflow project directory (contains `airflow.cfg` or `dags/` folder).

## Usage

Once installed, skills are invoked automatically based on what you ask. You can also invoke them directly:

```
/data:init-warehouse     # Initialize schema discovery (run once per project)
/data:data-analysis      # Analyze data with SQL
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

Example prompts:
- "Create a DAG that loads data from S3 to Snowflake daily"
- "What tables contain customer data?"
- "Why did my etl_pipeline DAG fail yesterday?"
- "Profile the orders table and check data quality"
- "What downstream jobs depend on the users table?"

## Development

See [CLAUDE.md](./CLAUDE.md) for plugin development guidelines.

### Repo Structure

```
agents/
├── packages/
│   └── data-warehouse/      # Data warehouse MCP server (SQL, schema discovery, Python kernel)
├── shared-skills/           # Skills (shared by Claude Code & OpenCode)
│   ├── init-warehouse/      # /data:init - schema discovery
│   ├── data-analysis/       # SQL-based analysis
│   ├── dag-authoring/       # DAG creation
│   └── ...                  # Other skills
├── claude-code-plugin/      # Claude Code plugin config
└── opencode/                # OpenCode config
```

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

## License

Apache 2.0
