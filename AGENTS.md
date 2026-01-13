# Claude Code Plugin Development

## Plugin Structure

```
project-root/
├── shared-skills/                # Canonical skill source (shared)
│   └── skill-name/
│       └── SKILL.md              # Skill with YAML frontmatter
├── claude-code-plugin/
│   ├── .claude-plugin/
│   │   ├── marketplace.json      # Marketplace catalog (lists plugins)
│   │   └── plugin.json           # Plugin manifest (metadata)
│   ├── skills -> ../shared-skills  # Symlink to shared skills
│   └── .mcp.json                 # MCP server config (MUST be at plugin root)
└── .opencode/
    └── skills -> ../shared-skills  # Symlink for OpenCode discovery
```

**Important**: `.mcp.json` must be at the plugin root, not inside `.claude-plugin/`. The `source` field in `marketplace.json` is relative to the marketplace root.

Skills are stored in `shared-skills/` and symlinked to both `claude-code-plugin/skills/` and `.opencode/skills/` so both Claude Code and OpenCode can discover them.

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

## Testing with OpenCode

OpenCode discovers skills from `.opencode/skills/` in the project directory. Since skills are symlinked to `shared-skills/`, they work with both tools.

### Verify Skills are Discovered

```bash
opencode debug skill
```

This outputs all discovered skills with their names, descriptions, and file paths.

### Run OpenCode

```bash
# Start OpenCode TUI in the project
opencode

# Or run with a specific message
opencode run "help me write a DAG"
```

OpenCode will automatically discover and use skills from `.opencode/skills/` based on the task context.
