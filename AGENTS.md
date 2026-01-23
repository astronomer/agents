# Claude Code Plugin Development

## Plugin Structure

```
project-root/
├── .claude-plugin/
│   └── marketplace.json        # Marketplace + plugin definition (strict: false)
├── hooks/                      # Hook scripts
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

## Configuration

Everything is defined inline in `.claude-plugin/marketplace.json` following the [advanced plugin entries](https://code.claude.com/docs/en/plugin-marketplaces#advanced-plugin-entries) pattern:

- **hooks**: Inlined in marketplace.json, scripts in `hooks/`
- **mcpServers**: Inlined in marketplace.json
- **skills**: Auto-discovered from `skills/` directory

Use `${CLAUDE_PLUGIN_ROOT}` to reference files within the plugin (required because plugins are copied to a cache location when installed).

## Key Files

- `.claude-plugin/marketplace.json` - Marketplace catalog with inline plugin definition (hooks, mcpServers)
- `hooks/*.sh` - Hook scripts (referenced via `${CLAUDE_PLUGIN_ROOT}/hooks/...`)
- `skills/*/SKILL.md` - Individual skills (auto-discovered)

## Config Location

This plugin uses `~/.astro/ai/config/` for user configuration (warehouse credentials, etc.).
