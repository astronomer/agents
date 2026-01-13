# data

A Claude Code and OpenCode plugin for data engineering workflows. Built by [Astronomer](https://www.astronomer.io/).

## Overview

`data` extends Claude Code and OpenCode with specialized capabilities for data practitioners, enabling AI-assisted data engineering directly in your terminal.

## Current Status

**Phase 1**: Airflow MCP integration via [astro-airflow-mcp](https://github.com/astronomer/astro-airflow-mcp)

## Features

### Airflow Integration
- Full access to Airflow REST API
- DAG management, triggering, and debugging
- Task logs and execution details
- System health monitoring

### Coming Soon
- Data warehouse discovery (Snowflake, BigQuery, Databricks, Redshift)
- Jupyter kernel integration for Python/SQL execution
- Skills and commands for guided workflows

## Installation

### Prerequisites

Install the local MCP servers (required before installing the plugin):
```bash
make install
```

This installs `data-jupyter` as a local tool via `uv tool install`, making it available system-wide.

### Claude Code

**Install from local marketplace:**
```bash
# Add the marketplace
claude plugin marketplace add ./claude-code-plugin

# Install the plugin
claude plugin install data@astronomer
```

**Or test locally (session only):**
```bash
claude --plugin-dir ./claude-code-plugin
```

### OpenCode

Coming soon.

## Plugin Structure

```
claude-code-plugin/
├── .claude-plugin/
│   ├── marketplace.json   # Marketplace catalog (lists available plugins)
│   └── plugin.json        # Plugin manifest (metadata)
└── .mcp.json              # MCP server config (must be at plugin root, not inside .claude-plugin/)
```

**Important:** The `.mcp.json` file must be at the plugin root directory, not inside `.claude-plugin/`. The `source` field in `marketplace.json` is relative to the marketplace root.

## Configuration

The plugin uses the Astro CLI AI config directory (`~/.astro/ai/config/`).

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI (v1.0.33+)
- [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) (for Airflow integration)

## Development

See [PLAN.md](./PLAN.md) for the development roadmap.

## License

Apache 2.0
