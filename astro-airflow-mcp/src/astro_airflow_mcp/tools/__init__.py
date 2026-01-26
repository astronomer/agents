"""MCP tool modules - importing registers tools with the MCP server."""

from astro_airflow_mcp.tools import admin, asset, dag, dag_run, diagnostic, task

__all__ = ["admin", "asset", "dag", "dag_run", "diagnostic", "task"]
