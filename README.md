# data

A Claude Code and OpenCode plugin for data engineering workflows. Built by [Astronomer](https://www.astronomer.io/).

## Overview

`data` extends Claude Code and OpenCode with specialized capabilities for data practitioners, enabling AI-assisted data engineering directly in your terminal. It provides intelligent tools for data warehouse exploration, pipeline authoring, and workflow orchestration.

## Features

### Jupyter Kernel Integration
- Automatically manages a Jupyter kernel for executing Python and SQL code
- Enables interactive data exploration and transformation within Claude Code sessions
- Supports iterative development with persistent kernel state

### Data Warehouse Discovery
- Connect to multiple data warehouse platforms:
  - Snowflake
  - BigQuery
  - Databricks
  - Redshift
  - (more coming)
- Discovery tools for exploring your data:
  - List schemas
  - List tables
  - Get table info (columns, types, statistics)
  - Run ad-hoc queries
- All queries execute through the managed Jupyter kernel

### Airflow Integration
- Integrates with [Astro CLI](https://www.astronomer.io/docs/astro/cli/overview) for local Airflow development
- Tools for managing DAGs, tasks, and runs
- Seamless pipeline authoring and testing workflow

### Data Engineering Skills
- Specialized prompts and capabilities optimized for data practitioner workflows
- **Pipeline Authoring**: Create, modify, and debug Airflow DAGs
- **Ad-hoc Exploration**: Investigate data quality, schema changes, and data lineage
- More skills coming soon

## Configuration

`data` uses a configuration file for data warehouse credentials and settings.

```yaml
# ~/.config/data/config.yaml
warehouses:
  my-snowflake:
    type: snowflake
    account: xxx
    user: xxx
    # additional connection parameters

  my-bigquery:
    type: bigquery
    project: xxx
    # additional connection parameters

airflow:
  # Astro CLI configuration
```

## Requirements

- [Claude Code](https://claude.ai/claude-code) CLI
- [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli) (for Airflow integration)
- Python 3.9+

## Installation

Coming soon.

## Usage

Coming soon.

## License

TBD
