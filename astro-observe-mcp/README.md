# Astro Observe MCP Server

A FastMCP server for Astro Cloud Observability API - search, list, and retrieve catalog assets.

## Features

- **search_assets**: Search and filter catalog assets with full-text search, asset type filters, namespace/DAG/tag filters
- **get_asset**: Get detailed information about a specific asset by ID
- **list_asset_filters**: Discover available filter values (namespaces, DAGs, tags, owners)

## Installation

```bash
# Using uv
uv pip install astro-observe-mcp

# Or from source
cd astro-observe-mcp
uv pip install -e .
```

## Authentication

The server supports multiple authentication methods (in order of precedence):

1. **CLI argument**: `--token "your-token"` and `--org-id`
2. **Environment variable**: `ASTRO_API_TOKEN`
3. **Astro CLI config**: Auto-discovered from `~/.astro/config.yaml` (created by `astro login`)

## Usage

### Auto-Discovery (Recommended)

The easiest way to use the server is with `astro login` - it automatically discovers both the token and organization ID:

```bash
# First, authenticate with Astro CLI
astro login

# Then run the MCP server (token and org-id auto-discovered)
astro-observe-mcp
```

### With Environment Variable

```bash
export ASTRO_API_TOKEN="your-api-token"
astro-observe-mcp --org-id clxxxxx
```

### With Explicit Token

```bash
astro-observe-mcp --org-id clxxxxx --token "your-api-token"
```

### Custom API URL

```bash
astro-observe-mcp --org-id clxxxxx --api-url https://api.astronomer.io
```

## MCP Tools

### search_assets

Search and filter catalog assets.

**Parameters:**
- `search` (optional): Full-text search query
- `asset_types` (optional): Filter by asset types (databricksTable, snowflakeTable, bigQueryTable, airflowTask, airflowDataset, openLineageDataset, airflowDag)
- `namespaces` (optional): Filter by deployment namespaces
- `dags` (optional): Filter by DAG IDs
- `dag_tags` (optional): Filter by DAG tags
- `owners` (optional): Filter by DAG owners
- `include_only_leaf_assets` (optional): Only return assets with no downstream dependencies
- `include_only_root_assets` (optional): Only return assets with no upstream dependencies
- `limit` (optional): Maximum results (default: 20, max: 100)
- `offset` (optional): Pagination offset
- `sorts` (optional): Sort criteria (e.g., "assetId:asc", "timestamp:desc")

### get_asset

Get detailed information about a specific asset.

**Parameters:**
- `asset_id`: The asset ID to retrieve

### list_asset_filters

Get available filter values for a specific filter type.

**Parameters:**
- `filter_type`: One of "namespace", "dag_id", "dag_tag", "owner"
- `search` (optional): Search within filter values
- `limit` (optional): Maximum results (default: 100)

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
pytest

# Lint
ruff check .
ruff format .
```

## License

Apache 2.0
