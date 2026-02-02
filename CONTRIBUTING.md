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

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Test with local plugin
claude --plugin-dir .

# Or install from local marketplace
claude plugin marketplace add .
claude plugin install data@astronomer
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
claude plugin uninstall data@astronomer && claude plugin install data@astronomer
```

### Working on the MCP Server

The Airflow MCP server is in `astro-airflow-mcp/`. See its [README](./astro-airflow-mcp/README.md) for specific development instructions.

## Pull Request Process

1. **Create a focused PR**: Each PR should address a single concern (bug fix, feature, etc.)
2. **Write descriptive commits**: Use clear commit messages that explain the "why"
3. **Update documentation**: If your change affects user-facing behavior, update relevant docs
4. **Ensure tests pass**: All pre-commit hooks and tests must pass
5. **Request review**: Tag maintainers for review

### PR Checklist

- [ ] Pre-commit hooks pass (`pre-commit run --all-files`)
- [ ] Changes are documented (if applicable)
- [ ] Commit messages are clear and descriptive
- [ ] Branch is up to date with `main`

## Coding Standards

This project uses automated tooling to enforce code style:

### Pre-commit Hooks

The following checks run automatically on commit:

- **Ruff**: Python linting and formatting
- **Trailing whitespace**: Removes trailing whitespace
- **End of file fixer**: Ensures files end with a newline
- **YAML/JSON validation**: Checks syntax of config files
- **Large file check**: Prevents accidentally committing large files
- **doctoc**: Auto-generates table of contents for README.md

Run hooks manually:

```bash
pre-commit run --all-files
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
# Run pre-commit hooks
pre-commit run --all-files

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
