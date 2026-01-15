.PHONY: help install install-dev install-all sync lint format check test run build clean

# Directory containing the Python project
WAREHOUSE_DIR := packages/data-warehouse

# Default target
help:  ## Show this help message
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "\033[1mQuick Start\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## \[quick\]' $(MAKEFILE_LIST) | awk -F ':' '{target=$$1} /## \[quick\]/ {sub(/.*## \[quick\] /, ""); printf "  \033[36m%-18s\033[0m %s\n", target, $$0}'
	@echo ""
	@echo "\033[1mBuild\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## \[build\]' $(MAKEFILE_LIST) | awk -F ':' '{target=$$1} /## \[build\]/ {sub(/.*## \[build\] /, ""); printf "  \033[36m%-18s\033[0m %s\n", target, $$0}'
	@echo ""
	@echo "\033[1mDevelopment\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## \[dev\]' $(MAKEFILE_LIST) | awk -F ':' '{target=$$1} /## \[dev\]/ {sub(/.*## \[dev\] /, ""); printf "  \033[36m%-18s\033[0m %s\n", target, $$0}'
	@echo ""
	@echo "\033[1mTesting\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## \[test\]' $(MAKEFILE_LIST) | awk -F ':' '{target=$$1} /## \[test\]/ {sub(/.*## \[test\] /, ""); printf "  \033[36m%-18s\033[0m %s\n", target, $$0}'
	@echo ""
	@echo "\033[1mUtilities\033[0m"
	@grep -E '^[a-zA-Z_-]+:.*?## \[util\]' $(MAKEFILE_LIST) | awk -F ':' '{target=$$1} /## \[util\]/ {sub(/.*## \[util\] /, ""); printf "  \033[36m%-18s\033[0m %s\n", target, $$0}'
	@echo ""

# Installation targets
install:  ## [quick] Install core dependencies and local MCP server
	cd $(WAREHOUSE_DIR) && uv sync
	uv tool install --force $(WAREHOUSE_DIR)

install-dev:  ## [dev] Install with dev dependencies
	cd $(WAREHOUSE_DIR) && uv sync --extra dev

install-all:  ## [dev] Install with all optional dependencies
	cd $(WAREHOUSE_DIR) && uv sync --all-extras

sync:  ## [dev] Sync dependencies from lockfile
	cd $(WAREHOUSE_DIR) && uv sync --frozen

# Development targets
lint:  ## [test] Run ruff linter
	cd $(WAREHOUSE_DIR) && uv run ruff check src/

format:  ## [dev] Format code with ruff
	cd $(WAREHOUSE_DIR) && uv run ruff format src/
	cd $(WAREHOUSE_DIR) && uv run ruff check --fix src/

check:  ## [test] Run linter and format check
	cd $(WAREHOUSE_DIR) && uv run ruff check src/
	cd $(WAREHOUSE_DIR) && uv run ruff format --check src/

test:  ## [test] Run tests with pytest
	cd $(WAREHOUSE_DIR) && uv run pytest

# Run target
run:  ## [quick] Run the data warehouse MCP server
	cd $(WAREHOUSE_DIR) && uv run data-warehouse

# Build targets
build:  ## [build] Build the package
	cd $(WAREHOUSE_DIR) && uv build

clean:  ## [util] Remove build artifacts
	rm -rf $(WAREHOUSE_DIR)/dist/
	rm -rf $(WAREHOUSE_DIR)/build/
	rm -rf $(WAREHOUSE_DIR)/.pytest_cache/
	rm -rf $(WAREHOUSE_DIR)/.ruff_cache/
	find $(WAREHOUSE_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(WAREHOUSE_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
