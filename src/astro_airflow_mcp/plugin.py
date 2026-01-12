"""Airflow plugin for integrating MCP server."""

from __future__ import annotations

import logging
from typing import Any

from astro_airflow_mcp import __version__

# Use standard logging for Airflow plugin integration
# This allows Airflow to control log level, format, and destination
logger = logging.getLogger(__name__)

try:
    from airflow.plugins_manager import AirflowPlugin

    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False
    AirflowPlugin = object  # type: ignore
    logger.warning("Airflow not available, plugin disabled")


# FastAPI app configuration for Airflow 3.x plugin system
try:
    from fastapi import FastAPI

    from astro_airflow_mcp.server import mcp

    # Get the native MCP protocol ASGI app from FastMCP
    mcp_protocol_app = mcp.http_app(path="/")

    # Wrap in a FastAPI app with the MCP app's lifespan
    # This is required for FastMCP to initialize its task group
    app = FastAPI(
        title="Airflow MCP Server", version=__version__, lifespan=mcp_protocol_app.lifespan
    )

    # Mount the MCP protocol app
    app.mount("/v1", mcp_protocol_app)
    logger.info("MCP protocol app created and mounted")

    # Airflow plugin configuration
    fastapi_apps_config = [{"app": app, "url_prefix": "/mcp", "name": "Airflow MCP Server"}]

except ImportError as e:
    logger.warning("FastAPI integration not available: %s", e)
    fastapi_apps_config = []


class AirflowMCPPlugin(AirflowPlugin):
    """Plugin to integrate MCP server with Airflow.

    Exposes MCP protocol endpoints at /mcp for AI clients (Cursor, Claude Desktop, etc.)
    """

    name = "astro_airflow_mcp"
    fastapi_apps = fastapi_apps_config

    @staticmethod
    def on_load(*_args: Any, **_kwargs: Any) -> None:
        """Called when the plugin is loaded."""
        logger.info("Airflow MCP Plugin loaded")


__all__ = ["AirflowMCPPlugin"]
