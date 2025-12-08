# Makefile for airflow-mcp development

.PHONY: help install install-dev install-dev-ci install-hooks run docker-build docker-run build test lint format type-check security check clean pre-commit

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	uv pip install -e .

install-tool:  ## Install as a system-wide CLI tool
	uv tool install -e .

install-dev:  ## Install the package with dev dependencies (local)
	uv sync --all-extras

install-dev-ci:  ## Install the package with dev dependencies (CI - system Python)
	uv export --no-hashes --format requirements-txt --all-extras > /tmp/requirements.txt
	uv pip install --system -r /tmp/requirements.txt
	uv pip install --system -e .

install-hooks:  ## Install pre-commit hooks
	pre-commit install
	@echo "✓ Pre-commit hooks installed"

run:  ## Run the MCP server (defaults: http mode, localhost:8000, airflow at localhost:8080)
	uv run python -m astro_airflow_mcp

docker-build:  ## Build Docker image
	docker build -t astro-airflow-mcp .

docker-run:  ## Run Docker container (http mode with 0.0.0.0 binding for container access)
	docker run -p 8000:8000 \
		-e AIRFLOW_API_URL=http://host.docker.internal:8080 \
		astro-airflow-mcp \
		python -m astro_airflow_mcp --host 0.0.0.0

build:  ## Build distribution packages (wheel and sdist)
	uv build

test:  ## Run tests
	PYTHONPATH=src uv run pytest

lint:  ## Run linting checks (ruff) - reports issues only
	uv run ruff check src/ tests/

format:  ## Format code with ruff - auto-fixes issues
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

type-check:  ## Run type checking (mypy) - excludes tests
	uv run mypy src/astro_airflow_mcp/ --ignore-missing-imports --no-strict-optional

security:  ## Run security checks (bandit) - excludes tests
	uv run bandit -c pyproject.toml -r src/astro_airflow_mcp/

check: lint type-check security  ## Run all checks (lint, type-check, security)
	@echo "✓ All checks passed"

pre-commit:  ## Run pre-commit on all files
	pre-commit run --all-files

pre-commit-update:  ## Update pre-commit hook versions
	pre-commit autoupdate

clean:  ## Clean up build artifacts and cache files
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

setup: install-dev install-hooks  ## Complete setup (install dev deps + hooks)
	@echo "✓ Development environment ready"

ci: pre-commit test  ## Run CI checks (pre-commit + tests)
	@echo "✓ CI checks passed"
