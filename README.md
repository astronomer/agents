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

### Claude Code

Test locally:
```bash
claude --plugin-dir ./claude-code-plugin
```

### OpenCode

Coming soon.

## Configuration

The plugin uses the Astro CLI AI config directory (`~/.astro/ai/config/`).

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI (v1.0.33+)
- [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) (for Airflow integration)

## Architecture

```
data-ai-plugins/
├── claude-code-plugin/     # Claude Code plugin
│   ├── .claude-plugin/     # Plugin manifest
│   └── .mcp.json           # MCP server config (astro-airflow-mcp)
├── opencode-plugin/        # OpenCode plugin (coming soon)
└── packages/               # MCP servers (coming soon)
    ├── data-jupyter/
    └── data-warehouse/
```

## Development

See [PLAN.md](./PLAN.md) for the development roadmap.

## License

Apache 2.0
