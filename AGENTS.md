<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Claude Code Plugin Development](#claude-code-plugin-development)
  - [Plugin Structure](#plugin-structure)
  - [Installing the Plugin](#installing-the-plugin)
  - [Skills](#skills)
  - [Configuration](#configuration)
  - [Key Files](#key-files)
  - [Config Location](#config-location)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Claude Code Plugin Development

## Plugin Structure

```
project-root/
├── .claude-plugin/
│   ├── marketplace.json        # Marketplace catalog (strict: false)
│   └── plugin.json             # Plugin manifest with hooks
└── skills/                     # Skills (auto-discovered)
    └── skill-name/
        ├── SKILL.md            # Skill with YAML frontmatter
        └── hooks/              # Hook scripts (co-located with skill)
            └── *.sh
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

Plugin configuration is split across two files:

- **hooks**: Inlined in `.claude-plugin/plugin.json`, scripts co-located in `skills/<name>/hooks/`
- **mcpServers**: Inlined in `.claude-plugin/plugin.json`
- **skills**: Auto-discovered from `skills/` directory
- **marketplace metadata**: Defined in `.claude-plugin/marketplace.json` (`strict: false`)

Use `${CLAUDE_PLUGIN_ROOT}` to reference files within the plugin (required because plugins are copied to a cache location when installed).

**Important:** Hooks in `SKILL.md` frontmatter can use **relative paths** from the skill's directory (e.g., `./scripts/bar.py`). Use `${CLAUDE_PLUGIN_ROOT}` in `plugin.json` to reference the plugin root.

## Key Files

- `.claude-plugin/plugin.json` - Plugin manifest with hooks and mcpServers
- `.claude-plugin/marketplace.json` - Marketplace catalog (metadata only, `strict: false`)
- `skills/*/SKILL.md` - Individual skills (auto-discovered)
- `skills/*/hooks/*.sh` - Hook scripts (co-located with skills, referenced via relative paths from SKILL.md or `${CLAUDE_PLUGIN_ROOT}/skills/<name>/hooks/...` from plugin.json)

## Config Location

This plugin uses `~/.astro/agents/` for user configuration (warehouse credentials, etc.).
