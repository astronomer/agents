# Claude Code Plugin Development

## Plugin Structure

```
project-root/
├── shared-skills/                  # Canonical skill source (shared)
│   └── skill-name/
│       └── SKILL.md                # Skill with YAML frontmatter
├── claude-code-plugin/
│   ├── .claude-plugin/
│   │   ├── marketplace.json        # Marketplace catalog (lists plugins)
│   │   └── plugin.json             # Plugin manifest (metadata)
│   ├── skills -> ../shared-skills  # Symlink to shared skills
│   └── .mcp.json                   # MCP server config for Claude Code
└── opencode/
    ├── opencode.json               # MCP server config for OpenCode
    └── .opencode/
        └── skills -> ../../shared-skills  # Symlink for OpenCode discovery
```

**Important**: `.mcp.json` must be at the plugin root, not inside `.claude-plugin/`. The `source` field in `marketplace.json` is relative to the marketplace root.

Skills are stored in `shared-skills/` and symlinked to both `claude-code-plugin/skills/` and `opencode/.opencode/skills/` so both Claude Code and OpenCode can discover them.

## Installing the Plugin

```bash
# Add the marketplace
claude plugin marketplace add ./claude-code-plugin

# Install the plugin
claude plugin install data@astronomer

# Or test locally (session only)
claude --plugin-dir ./claude-code-plugin
```

After adding skills or making changes, reinstall the plugin:
```bash
claude plugin uninstall data@astronomer && claude plugin install data@astronomer
```

## Skills

Skills are markdown files with YAML frontmatter in `skills/<name>/SKILL.md`:

```yaml
---
name: skill-name
description: When to use this skill (Claude uses this to decide when to invoke it)
---

# Skill content here...
```

- Skills are auto-discovered from the `skills/` directory
- Claude invokes skills automatically based on the description matching user requests
- Users can also invoke directly with `/plugin-name:skill-name` (e.g., `/data:dag-authoring`)

## MCP Servers

### Claude Code

Configure in `claude-code-plugin/.mcp.json`:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "uvx",
      "args": ["package-name", "--transport", "stdio"]
    }
  }
}
```

### OpenCode

Configure in `opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "server-name": {
      "type": "local",
      "command": ["uvx", "package-name", "--transport", "stdio"]
    }
  }
}
```

Verify MCP servers are connected (run from `opencode/` directory):

```bash
cd opencode && opencode mcp list
```

## Key Files

- `marketplace.json` - Lists plugins in this marketplace, references plugin source paths
- `plugin.json` - Plugin metadata (name, version, description, author)
- `claude-code-plugin/.mcp.json` - MCP server config for Claude Code (auto-added on plugin install)
- `opencode/opencode.json` - MCP server config for OpenCode
- `shared-skills/*/SKILL.md` - Skills shared by both Claude Code and OpenCode

## Config Location

This plugin uses `~/.astro/ai/config/` for user configuration (warehouse credentials, etc.).

## Testing with OpenCode

OpenCode config and skills live in the `opencode/` subdirectory. Run OpenCode from there:

```bash
cd opencode
```

### Verify Skills are Discovered

```bash
opencode debug skill
```

This outputs all discovered skills with their names, descriptions, and file paths.

### Run OpenCode

```bash
# Start OpenCode TUI
opencode

# Or run with a specific message
opencode run "help me write a DAG"
```

OpenCode will automatically discover skills from `.opencode/skills/` and MCP servers from `opencode.json`.
