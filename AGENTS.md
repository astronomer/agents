# Claude Code Plugin Development

## Plugin Structure

```
claude-code-plugin/
├── .claude-plugin/
│   ├── marketplace.json   # Marketplace catalog (lists plugins)
│   └── plugin.json        # Plugin manifest (metadata)
├── skills/                # Skills directory (auto-discovered)
│   └── skill-name/
│       └── SKILL.md       # Skill with YAML frontmatter
└── .mcp.json              # MCP server config (MUST be at plugin root)
```

**Important**: `.mcp.json` must be at the plugin root, not inside `.claude-plugin/`. The `source` field in `marketplace.json` is relative to the marketplace root.

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

Configure in `.mcp.json`:

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

## Key Files

- `marketplace.json` - Lists plugins in this marketplace, references plugin source paths
- `plugin.json` - Plugin metadata (name, version, description, author)
- `.mcp.json` - MCP server configurations that get auto-added when plugin is installed
- `skills/*/SKILL.md` - Skills that Claude can invoke

## Config Location

This plugin uses `~/.astro/ai/config/` for user configuration (warehouse credentials, etc.).
