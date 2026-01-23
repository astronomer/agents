#!/bin/bash
# Wrapper script to run astro-dwh-mcp MCP server with DRY_RUN mode
# Usage: DRY_RUN_MODE=true MOCK_RESPONSES_FILE=... ./scripts/run-dry-warehouse.sh

# Pass through environment variables and run the server
exec uvx astro-dwh-mcp "$@"
