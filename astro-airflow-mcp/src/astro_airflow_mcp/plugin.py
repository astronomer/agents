"""Airflow plugin for integrating MCP server."""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

from astro_airflow_mcp import __version__

# Use standard logging for Airflow plugin integration
# This allows Airflow to control log level, format, and destination
logger = logging.getLogger(__name__)

# Per-request auth token, set by middleware and read by the adapter.
# ContextVar ensures isolation between concurrent async requests.
_request_auth_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_request_auth_token", default=None
)

try:
    from airflow.plugins_manager import AirflowPlugin

    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False
    AirflowPlugin = object
    logger.warning("Airflow not available, plugin disabled")


# FastAPI app configuration for Airflow 3.x plugin system
try:
    from fastapi import FastAPI

    from astro_airflow_mcp.server import _manager, mcp

    # Get the native MCP protocol ASGI app from FastMCP
    # Use stateless_http=True so sessions aren't stored in-memory,
    # which is required for multi-replica deployments (e.g., Astro)
    mcp_protocol_app = mcp.http_app(path="/", stateless_http=True)

    # Wrap in a FastAPI app with the MCP app's lifespan
    # This is required for FastMCP to initialize its task group
    app = FastAPI(
        title="Airflow MCP Server", version=__version__, lifespan=mcp_protocol_app.lifespan
    )

    # Mount the MCP protocol app
    app.mount("/v1", mcp_protocol_app)
    logger.info("MCP protocol app created and mounted")

    # Configure Airflow connection for plugin mode.
    # The plugin runs inside the Airflow API server process, so use localhost
    # for internal API calls. The client's auth token is forwarded per-request
    # via middleware.
    _plugin_port = 8080
    try:
        from airflow.configuration import conf

        _plugin_port = conf.getint("api", "port", fallback=8080)
    except Exception:
        logger.debug("Could not read api.port from Airflow config, using default 8080")

    _plugin_url = os.environ.get("AIRFLOW_API_URL", f"http://localhost:{_plugin_port}")

    # Configure the adapter manager for plugin mode: set the internal localhost URL
    # and override the token getter to read from the per-request ContextVar.
    _manager._airflow_url = _plugin_url
    _manager._get_auth_token = lambda: _request_auth_token.get()  # type: ignore[assignment]

    logger.info("Plugin mode configured with Airflow URL: %s", _plugin_url)

    # Pure ASGI middleware to forward the client's Authorization header
    # to internal Airflow API calls. Uses ContextVar for per-request isolation.
    class _ForwardAuthMiddleware:
        """Extract Authorization header and store in per-request ContextVar."""

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()
                if auth.lower().startswith("bearer "):
                    _request_auth_token.set(auth[7:])
            await self.app(scope, receive, send)

    app.add_middleware(_ForwardAuthMiddleware)

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

    @classmethod
    def on_load(cls, *_args: Any, **_kwargs: Any) -> None:
        """Called when the plugin is loaded."""
        logger.info("Airflow MCP Plugin loaded")


__all__ = ["AirflowMCPPlugin"]
