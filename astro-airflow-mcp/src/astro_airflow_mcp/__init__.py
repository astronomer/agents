"""Airflow MCP Server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("astro-airflow-mcp")
except PackageNotFoundError:
    # Package is not installed (e.g., during development/testing with PYTHONPATH)
    __version__ = "0.0.0+dev"
