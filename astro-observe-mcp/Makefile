# Makefile for astro-observe-mcp development

.PHONY: help install install-dev install-dev-ci run build test lint format type-check check clean setup ci

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	uv pip install -e .

uninstall:  ## Uninstall the package
	uv pip uninstall astro-observe-mcp

install-tool:  ## Install as a system-wide CLI tool
	uv tool install -e .

uninstall-tool:  ## Uninstall the system-wide CLI tool
	uv tool uninstall astro-observe-mcp

install-dev:  ## Install the package with dev dependencies (local)
	uv sync --all-extras

install-dev-ci:  ## Install the package with dev dependencies (CI - system Python)
	uv export --no-hashes --format requirements-txt --all-extras --all-groups > /tmp/requirements.txt
	uv pip install --system -r /tmp/requirements.txt
	uv pip install --system -e .

run:  ## Run the MCP server in HTTP mode
	uv run python -m astro_observe_mcp --transport http

build:  ## Build distribution packages (wheel and sdist)
	uv build

test:  ## Run tests
	uv run pytest tests/

lint:  ## Run linting checks (ruff) - reports issues only
	uv run ruff check src/ tests/

format:  ## Format code with ruff - auto-fixes issues
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

type-check:  ## Run type checking (mypy)
	uv run mypy src/astro_observe_mcp/ --ignore-missing-imports --no-strict-optional

check: lint type-check  ## Run all checks (lint, type-check)
	@echo "✓ All checks passed"

clean:  ## Clean up build artifacts and cache files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

setup: install-dev  ## Complete setup (install dev deps)
	@echo "✓ Development environment ready"

ci: check test  ## Run CI checks (lint + type-check + tests)
	@echo "✓ CI checks passed"
