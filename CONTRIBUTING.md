# Contributing to Astronomer Agents

Thank you for your interest in contributing to Astronomer Agents! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Reporting Issues](#reporting-issues)
- [Communication](#communication)

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [oss_security@astronomer.io](mailto:oss_security@astronomer.io).

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see below)
4. Create a branch for your changes
5. Make your changes and test them
6. Submit a pull request

## Development Setup

```bash
# Clone the repo
git clone https://github.com/astronomer/agents.git
cd agents

# Install prek hooks
pip install prek
prek install

# Test with local plugin
claude --plugin-dir .

# Or install from local marketplace
claude plugin marketplace add .
claude plugin install astronomer-data@astronomer
```

### Project Structure

```
agents/
├── .claude-plugin/          # Plugin configuration
│   └── marketplace.json     # Marketplace + plugin definition
├── skills/                  # Skills (auto-discovered)
│   └── <skill-name>/
│       ├── SKILL.md         # Skill definition with YAML frontmatter
│       └── hooks/           # Hook scripts (optional)
├── astro-airflow-mcp/       # Airflow MCP server package
└── tests/                   # Test files
```

## Making Changes

### Adding or Modifying Skills

Skills are markdown files with YAML frontmatter in `skills/<name>/SKILL.md`:

```yaml
---
name: skill-name
description: When to use this skill (Claude uses this to decide when to invoke it)
---

# Skill content here...
```

After adding or modifying skills, reinstall the plugin to test:

```bash
claude plugin uninstall astronomer-data@astronomer && claude plugin marketplace update && claude plugin install astronomer-data@astronomer
```

### Authoring Evergreen Skills

Skills rot when they embed content that changes every upstream release (operator params, REST paths, CLI flags, version numbers). A skill the maintainer has to touch on every Airflow/provider release is broken by design. Write skills so they keep working without edits.

**Three recurring rot patterns and their replacements:**

| Rot pattern | What it looks like | Replacement |
|---|---|---|
| **Hardcoded version gates** | `> Requires Airflow 3.1+` as immutable text, `Cosmos 1.11+`, etc. | Instruct the agent to verify at runtime: `uvx --from astro-airflow-mcp af config version` and `af config providers \| jq ...`. Keep the floor version as a reference, not an assertion. |
| **Embedded constructor signatures** | Multi-line `HITLOperator(task_id=..., subject=..., options=..., assigned_users=..., ...)` code blocks listing every kwarg | Name the class once in an anchoring table, then tell the agent to fetch current signatures via `af registry parameters <provider>` before writing code. One canonical example is fine; a parameter encyclopedia is not. |
| **Quoted REST paths / CLI flags** | `POST /api/v2/hitlDetails/{dag_id}/{run_id}/{task_id}`, `astro deploy --dags --pytest` as verbatim contracts | Derive at use time: `af api ls --filter <keyword>`, `af api spec`, `astro <cmd> --help`. Keep the *pattern* (what method, what it does) and discover the path. |

**Reviewer checklist for skill PRs:**

- [ ] Are class, operator, or hook names mentioned more than once outside a single anchoring table? If so, ask if each repetition is needed — each one is a surface that can rot.
- [ ] Does the skill quote a REST path verbatim instead of pointing at `af api ls` / `af api spec`?
- [ ] Does the skill assert a version floor instead of teaching the agent to check it?
- [ ] Does the skill embed a parameter table that duplicates what `af registry parameters` returns? If yes, delete the table and reference the command.
- [ ] Does the skill include more than one full code example per concept? One canonical example is enough — the agent adapts it using discovery.
- [ ] Does the skill cross-reference the `airflow` skill for registry and API discovery commands rather than re-explaining them?

**When embedding a concrete example is the right call:**

A single canonical example per capability is useful context — it anchors the agent on the correct shape (`@dag` decorator, import path, XCom wiring) that is stable across releases. Pair it with an explicit "verify params via `af registry` before writing code" instruction so stale param names in the example get corrected against live truth. See `skills/airflow-hitl/SKILL.md` for the current reference implementation of this pattern.

### Astro CLI v1 and v2 Commands

Skills are read on Astro CLI v1 (with the standalone `af`) and v2 alike, so every skill that runs Astro CLI or `af` commands follows one pattern, checked by `scripts/check_cli_forms.py`:

1. Its `SKILL.md` carries the "Astro CLI version" block from `shared/astro-cli-version.md`, before its first `##` section. Don't edit the copies: edit the source, then run `python3 scripts/sync_cli_version_block.py`. The block holds the version probe and the rewrite rule that turns a v2 command into its v1 form. The same file ships in astronomer/hosted-skills, byte for byte.
2. Commands are written in their v2 form, in fenced code blocks.
3. A v1 form the rewrite rule doesn't give goes on its own line directly under the v2 command, in the same code block:

   ```bash
   astro local check
   # v1: astro dev parse
   ```

4. A difference that isn't a command goes on its own line starting `**v1:**` (or `**v2:**`).

Nowhere else: no v1 columns in tables, no `v1:` in a trailing comment, no v1 command in prose.

### Working on the MCP Server

The Airflow MCP server is in `astro-airflow-mcp/`. See its [README](./astro-airflow-mcp/README.md) for specific development instructions.

## Pull Request Process

1. **Create a focused PR**: Each PR should address a single concern (bug fix, feature, etc.)
2. **Write descriptive commits**: Use clear commit messages that explain the "why"
3. **Update documentation**: If your change affects user-facing behavior, update relevant docs
4. **Ensure tests pass**: All prek hooks and tests must pass
5. **Request review**: Tag maintainers for review

### PR Checklist

- [ ] Prek hooks pass (`prek run --all-files`)
- [ ] Changes are documented (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] Branch is up to date with `main`

## Coding Standards

This project uses automated tooling to enforce code style:

### Prek Hooks

The following checks run automatically on commit (using prek, a fast alternative to pre-commit):

- **Ruff**: Python linting and formatting
- **Trailing whitespace**: Removes trailing whitespace
- **End of file fixer**: Ensures files end with a newline
- **YAML/JSON validation**: Checks syntax of config files
- **Large file check**: Prevents accidentally committing large files
- **doctoc**: Auto-generates table of contents for README.md
- **check-cli-forms**: Skills follow the Astro CLI v1/v2 format (see [Astro CLI v1 and v2 Commands](#astro-cli-v1-and-v2-commands)); its tests run alongside

Run hooks manually:

```bash
prek run --all-files
```

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Use type hints where practical
- Write docstrings for public functions and classes

### Markdown Style

- Use ATX-style headers (`#`, `##`, etc.)
- Include a table of contents for long documents
- Use fenced code blocks with language identifiers

## Testing

### Running Tests

```bash
# Run prek hooks
prek run --all-files

# Test plugin locally
claude --plugin-dir .
```

### Testing Skills

When modifying skills, test them interactively:

1. Install the plugin locally
2. Run Claude Code and invoke the skill
3. Verify the expected behavior

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Feature Requests

For feature requests, please describe:

- The problem you're trying to solve
- Your proposed solution
- Alternatives you've considered

## Communication

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Pull Requests**: For code contributions

---

Thank you for contributing to Astronomer Agents!
