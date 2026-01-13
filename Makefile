.PHONY: help install install-dev install-all sync lint format check test run build clean

# Directory containing the Python project
JUPYTER_DIR := packages/data-jupyter

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
install:  ## [quick] Install core dependencies
	cd $(JUPYTER_DIR) && uv sync

install-dev:  ## [dev] Install with dev dependencies
	cd $(JUPYTER_DIR) && uv sync --extra dev

install-all:  ## [dev] Install with all optional dependencies
	cd $(JUPYTER_DIR) && uv sync --all-extras

sync:  ## [dev] Sync dependencies from lockfile
	cd $(JUPYTER_DIR) && uv sync --frozen

# Development targets
lint:  ## [test] Run ruff linter
	cd $(JUPYTER_DIR) && uv run ruff check src/

format:  ## [dev] Format code with ruff
	cd $(JUPYTER_DIR) && uv run ruff format src/
	cd $(JUPYTER_DIR) && uv run ruff check --fix src/

check:  ## [test] Run linter and format check
	cd $(JUPYTER_DIR) && uv run ruff check src/
	cd $(JUPYTER_DIR) && uv run ruff format --check src/

test:  ## [test] Run tests with pytest
	cd $(JUPYTER_DIR) && uv run pytest

# Run target
run:  ## [quick] Run the Jupyter MCP server
	cd $(JUPYTER_DIR) && uv run data-jupyter

# Build targets
build:  ## [build] Build the package
	cd $(JUPYTER_DIR) && uv build

clean:  ## [util] Remove build artifacts
	rm -rf $(JUPYTER_DIR)/dist/
	rm -rf $(JUPYTER_DIR)/build/
	rm -rf $(JUPYTER_DIR)/.pytest_cache/
	rm -rf $(JUPYTER_DIR)/.ruff_cache/
	find $(JUPYTER_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(JUPYTER_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true

