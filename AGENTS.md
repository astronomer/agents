# Claude Code Plugin Development

## Plugin Structure

```
project-root/
├── .claude-plugin/
│   └── marketplace.json        # Marketplace + plugin definition (strict: false)
├── .mcp.json                   # MCP server configuration
├── hooks/                      # Plugin hooks
│   ├── hooks.json
│   └── *.sh
└── skills/                     # Skills (auto-discovered)
    └── skill-name/
        └── SKILL.md            # Skill with YAML frontmatter
```

## Installing the Plugin

```bash
# Add the marketplace (from repo root)
claude plugin marketplace add astronomer/agents

# Install the plugin
claude plugin install data@astronomer

# Or test locally (session only)
claude --plugin-dir .
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
- Users can also invoke directly with `/plugin-name:skill-name` (e.g., `/data:authoring-dags`)

## MCP Servers

Configure in `.mcp.json` at the repo root:

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

- `.claude-plugin/marketplace.json` - Marketplace catalog with inline plugin definition (references hooks and mcpServers)
- `.mcp.json` - MCP server configuration (referenced via `"mcpServers": "./.mcp.json"`)
- `hooks/hooks.json` - Plugin hooks (referenced via `"hooks": "./hooks/hooks.json"`)
- `skills/*/SKILL.md` - Individual skills (auto-discovered)

## Config Location

This plugin uses `~/.astro/ai/config/` for user configuration (warehouse credentials, etc.).
