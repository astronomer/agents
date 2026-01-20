# Investigate republishing MCP server as a CLI

**Labels:** enhancement, investigation

## Context

From Slack discussion in #ai-cli-dev, we've observed that Claude Code has a strong bias toward using CLI commands over MCP tools, even when the MCP server is properly connected.

## Problem

When users interact with Claude Code:
- Claude Code preferentially tries to use CLI commands (e.g., `astro deployment logs [deployment-id] --workers`)
- Even though MCP tools are available and work correctly when the server is connected, the model seems to favor CLI patterns
- This suggests we might benefit from providing CLI wrappers around our MCP functionality

## Observed Behavior

From the Slack thread (2026-01-20):
> julian: "like i told it to fetch logs for a deployment and it tried to run `astro deployment logs [deployment-id] --workers`"

> Greg Neiheisel: "I've seen that kind of behavior as well but only when the server isn't connected properly. Otherwise it'll favor the MCP from my testing in Cursor."

While MCP does work when properly connected, there's still value in having CLI commands available for:
1. Cases where MCP isn't connected or available
2. Aligning with LLM's natural preference for CLI patterns
3. Better discoverability for users

## Proposed Investigation

Explore options for republishing our data-warehouse MCP server functionality as CLI commands that could be:

### Option 1: Standalone CLI Tool
- Create a dedicated CLI tool (e.g., `data-warehouse` or `astro-dw`)
- Similar to the airflowctl pattern
- Can be installed independently
- Direct mapping to existing MCP tools

### Option 2: Integration with Astro CLI
- Add commands under `astro warehouse` namespace
- Leverage existing CLI infrastructure
- Better integration with existing Astronomer tooling
- Example commands:
  - `astro warehouse query "SELECT * FROM table"`
  - `astro warehouse list-schemas`
  - `astro warehouse list-tables`
  - `astro warehouse table-info <table-name>`

### Option 3: Hybrid Approach
- Keep MCP server for programmatic access
- Add thin CLI wrapper that calls MCP tools
- Best of both worlds

## Benefits

- **Better LLM alignment**: Matches Claude Code's bias toward CLI usage
- **Fallback option**: Works when MCP server isn't connected
- **Discoverability**: More visible to users familiar with CLI tools
- **Broader compatibility**: Works in environments where MCP isn't available
- **Consistent UX**: Aligns with existing Astronomer CLI patterns

## Current MCP Server Capabilities

Our `data-warehouse` MCP server (in `packages/data-warehouse/`) currently provides:

### Tools
- `run_sql` - Execute SQL queries against configured warehouses
- `list_tables` - List tables in schemas
- `get_tables_info` - Get detailed table information including columns and types
- `list_schemas_single_db` - List schemas in a single database
- `list_schemas_configured` - List all configured schemas

### Resources
- Warehouse connection management
- Configuration via `~/.astro/ai/config/`
- Session state management
- Query caching

These capabilities could be exposed as CLI commands with similar interfaces.

## Implementation Considerations

1. **Configuration**: CLI should use same config location (`~/.astro/ai/config/`)
2. **Output format**: Support both human-readable and machine-readable (JSON) output
3. **Authentication**: Leverage existing warehouse connection configs
4. **Error handling**: Consistent with existing CLI patterns
5. **Documentation**: Clear examples and help text
6. **Testing**: Integration tests for both MCP and CLI interfaces

## Success Metrics

- Claude Code successfully discovers and uses CLI commands
- Reduced friction for users when MCP isn't connected
- Consistent experience across both interfaces
- Positive user feedback on CLI usability

## Next Steps

1. Decide on approach (standalone vs. astro CLI integration)
2. Design CLI command structure and arguments
3. Prototype basic implementation
4. Test with Claude Code to verify LLM usage patterns
5. Gather user feedback
6. Iterate and expand functionality

## Related Discussion

See Slack thread in #ai-cli-dev from 2026-01-20 starting at 6:26 PM

---

**Created from Cursor Cloud Agent**
Branch: `cursor/mcp-cli-republication-9712`
