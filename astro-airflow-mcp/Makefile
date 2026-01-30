# Makefile for airflow-mcp development

.PHONY: help install install-dev install-dev-ci install-hooks run cli cli-health cli-help docker-build docker-run build test test-integration test-integration-v2 test-integration-v3 lint format type-check security check clean prek

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	uv pip install -e .

uninstall:  ## Uninstall the package
	uv pip uninstall astro-airflow-mcp

install-tool:  ## Install as a system-wide CLI tool
	uv tool install -e .

uninstall-tool:  ## Uninstall the system-wide CLI tool
	uv tool uninstall astro-airflow-mcp

install-dev:  ## Install the package with dev dependencies (local)
	uv sync --all-extras

install-dev-ci:  ## Install the package with dev dependencies (CI - system Python)
	uv export --no-hashes --format requirements-txt --all-extras --all-groups > /tmp/requirements.txt
	uv pip install --system -r /tmp/requirements.txt
	uv pip install --system -e .

install-hooks:  ## Install prek hooks
	prek install
	@echo "✓ prek hooks installed"

run:  ## Run the MCP server in HTTP mode (default is stdio, but HTTP can be useful for local testing)
	uv run python -m astro_airflow_mcp --transport http

cli:  ## Run the af CLI tool (pass args with ARGS=, e.g., make cli ARGS="dags list")
	uv run af $(ARGS)

cli-health:  ## Run af CLI health check
	uv run af health

cli-help:  ## Show af CLI help
	uv run af --help

docker-build:  ## Build Docker image
	docker build -t astro-airflow-mcp .

docker-run:  ## Run Docker container
	docker run -p 8000:8000 \
		-e AIRFLOW_API_URL=http://host.docker.internal:8080 \
		astro-airflow-mcp \
		python -m astro_airflow_mcp --transport http

build:  ## Build distribution packages (wheel and sdist)
	uv build

test:  ## Run unit tests (fast, no external dependencies)
	uv run pytest tests/ --ignore=tests/integration/

test-integration:  ## Run integration tests against a running Airflow instance
	./scripts/run-integration-tests.sh

test-integration-v2:  ## Start Airflow 2.x and run integration tests
	docker compose -f docker-compose.test.yml --profile airflow2 up -d --wait
	./scripts/run-integration-tests.sh http://localhost:8080 admin admin; \
	EXIT_CODE=$$?; \
	docker compose -f docker-compose.test.yml --profile airflow2 down; \
	exit $$EXIT_CODE

test-integration-v3:  ## Start Airflow 3.x and run integration tests
	docker compose -f docker-compose.test.yml --profile airflow3 up -d --wait
	./scripts/run-integration-tests.sh http://localhost:8081 admin admin; \
	EXIT_CODE=$$?; \
	docker compose -f docker-compose.test.yml --profile airflow3 down; \
	exit $$EXIT_CODE

test-all:  ## Run unit tests + integration tests against both Airflow versions
	$(MAKE) test
	$(MAKE) test-integration-v2
	$(MAKE) test-integration-v3

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

prek:  ## Run prek on all files
	prek run --all-files

prek-update:  ## Update prek hook versions
	prek autoupdate

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

ci: prek test  ## Run CI checks (prek + tests)
	@echo "✓ CI checks passed"
