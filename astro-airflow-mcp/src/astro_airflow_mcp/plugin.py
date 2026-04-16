"""Airflow plugin for integrating MCP server.

Supports both Airflow 2.x (Flask blueprint) and Airflow 3.x (FastAPI app).
The appropriate integration is selected automatically based on available packages.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import os
import threading
from typing import Any

from astro_airflow_mcp import __version__

# Use standard logging for Airflow plugin integration
# This allows Airflow to control log level, format, and destination
logger = logging.getLogger(__name__)

# Per-request auth token (Airflow 3.x bearer tokens), set by middleware
# and read by the adapter. ContextVar ensures isolation between concurrent requests.
_request_auth_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_request_auth_token", default=None
)


# Per-request basic auth (Airflow 2.x), set in the async handler
# and read by the adapter for internal API calls.
_request_basic_auth: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "mcp_request_basic_auth", default=None
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


# ---------------------------------------------------------------------------
# Airflow 2.x Flask blueprint (only if FastAPI/AF3 path was not taken)
# ---------------------------------------------------------------------------
flask_blueprints_config: list = []

if not fastapi_apps_config:
    try:
        from flask import Blueprint
        from flask import Response as FlaskResponse
        from flask import request as flask_request

        from astro_airflow_mcp.server import _manager, configure, mcp

        # --- Detect Airflow webserver config ---
        _plugin_port_v2 = 8080
        try:
            from airflow.configuration import conf

            _plugin_port_v2 = conf.getint("webserver", "web_server_port", fallback=8080)
        except Exception:
            logger.debug("Could not read webserver config, using defaults")

        def _get_base_path() -> str:
            """Read webserver.base_url path prefix lazily.

            On Astro, base_url is only set after the plugin loads, so we
            must read it from Airflow config at request time, not import time.
            """
            try:
                from urllib.parse import urlparse

                from airflow.configuration import conf as _conf

                url = _conf.get("webserver", "base_url", fallback="")
                return urlparse(url).path.rstrip("/")
            except Exception:
                return ""

        def _get_plugin_url() -> str:
            env_url = os.environ.get("AIRFLOW_API_URL")
            if env_url:
                return env_url
            return f"http://localhost:{_plugin_port_v2}{_get_base_path()}"

        # ASGI app — same as the AF3 path but we call it from Flask
        _mcp_asgi_app = mcp.http_app(path="/", stateless_http=True)

        # --- Lazy init: event loop + ASGI lifespan ---
        # FastMCP needs a running lifespan to initialize its task group.
        # We keep one asyncio loop in a daemon thread. Lazy because
        # gunicorn forks workers and threads don't survive the fork.
        _v2_state: dict[str, Any] = {"loop": None, "ready": False}
        _v2_lock = threading.Lock()

        def _ensure_ready() -> asyncio.AbstractEventLoop:
            if _v2_state["ready"]:
                return _v2_state["loop"]
            with _v2_lock:
                if _v2_state["ready"]:
                    return _v2_state["loop"]

                # Configure adapter for plugin mode.
                # Per-request auth is stored in a module-level dict (not
                # ContextVars — those don't propagate across the thread
                # boundary to the background asyncio loop). Safe because
                # gunicorn sync workers handle one request at a time.
                # URL is resolved lazily via _get_plugin_url() because
                # webserver.base_url may not be set at plugin load time.
                _plugin_url_v2 = _get_plugin_url()
                configure(url=_plugin_url_v2)
                _manager._get_auth_token = lambda: _v2_state.get("bearer_token")  # type: ignore[assignment]
                _manager._get_basic_auth = lambda: _v2_state.get("basic_auth")  # type: ignore[assignment]
                logger.info("MCP plugin URL: %s", _plugin_url_v2)

                loop = asyncio.new_event_loop()
                threading.Thread(target=loop.run_forever, daemon=True, name="mcp-loop").start()

                # Start ASGI lifespan (initializes FastMCP task group)
                started = threading.Event()

                async def _lifespan() -> None:
                    done = asyncio.Event()

                    async def recv() -> dict:
                        if not done.is_set():
                            return {"type": "lifespan.startup"}
                        await asyncio.Event().wait()
                        return {"type": "lifespan.shutdown"}

                    async def send(msg: dict) -> None:
                        if msg["type"] in (
                            "lifespan.startup.complete",
                            "lifespan.startup.failed",
                        ):
                            done.set()
                            started.set()

                    await _mcp_asgi_app(
                        {"type": "lifespan", "asgi": {"version": "3.0"}},
                        recv,
                        send,
                    )

                asyncio.run_coroutine_threadsafe(_lifespan(), loop)
                started.wait(timeout=10)

                _v2_state["loop"] = loop
                _v2_state["ready"] = True
                logger.info("MCP ASGI loop and lifespan ready")
                return loop

        # --- Flask blueprint ---
        bp = Blueprint("airflow_mcp", __name__, url_prefix="/mcp")

        @bp.record_once
        def _exempt_csrf(state: Any) -> None:
            """Exempt from CSRF — MCP clients use Basic auth, not cookies."""
            csrf = state.app.extensions.get("csrf")
            if csrf:
                csrf.exempt(bp)

        @bp.route(
            "/v1/",
            defaults={"subpath": ""},
            methods=["GET", "POST", "DELETE"],
        )
        @bp.route("/v1/<path:subpath>", methods=["GET", "POST", "DELETE"])
        def _mcp_handler(subpath: str = "") -> FlaskResponse:
            """Forward request to the ASGI MCP app."""
            loop = _ensure_ready()
            body = flask_request.get_data()
            path = "/" + subpath if subpath else "/"

            # Store per-request auth in _v2_state so the adapter can
            # read it from the background thread. Safe because gunicorn
            # sync workers handle one request at a time.
            auth_header = flask_request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                _v2_state["bearer_token"] = auth_header[7:]
                _v2_state["basic_auth"] = None
            elif flask_request.authorization and flask_request.authorization.username:
                _v2_state["bearer_token"] = None
                _v2_state["basic_auth"] = (
                    flask_request.authorization.username,
                    flask_request.authorization.password or "",
                )

            status = 200
            resp_headers: list[tuple[str, str]] = []
            parts: list[bytes] = []

            async def _handle() -> None:
                nonlocal status
                request_sent = False
                done = asyncio.Event()

                async def recv() -> dict:
                    nonlocal request_sent
                    if not request_sent:
                        request_sent = True
                        return {
                            "type": "http.request",
                            "body": body,
                            "more_body": False,
                        }
                    await done.wait()
                    return {"type": "http.disconnect"}

                async def send(msg: dict) -> None:
                    nonlocal status
                    if msg["type"] == "http.response.start":
                        status = msg["status"]
                        resp_headers.extend(
                            (
                                k.decode() if isinstance(k, bytes) else k,
                                v.decode() if isinstance(v, bytes) else v,
                            )
                            for k, v in msg.get("headers", [])
                        )
                    elif msg["type"] == "http.response.body":
                        if msg.get("body"):
                            parts.append(msg["body"])
                        if not msg.get("more_body", False):
                            done.set()

                await _mcp_asgi_app(
                    {
                        "type": "http",
                        "asgi": {"version": "3.0"},
                        "http_version": "1.1",
                        "method": flask_request.method,
                        "path": path,
                        "query_string": flask_request.query_string,
                        "root_path": "",
                        "headers": [
                            (k.lower().encode(), v.encode()) for k, v in flask_request.headers
                        ],
                    },
                    recv,
                    send,
                )

            future = asyncio.run_coroutine_threadsafe(_handle(), loop)
            future.result(timeout=120)

            return FlaskResponse(
                response=b"".join(parts),
                status=status,
                headers=dict(resp_headers),
            )

        flask_blueprints_config = [bp]
        logger.info("AF2 Flask blueprint created at /mcp/v1/")

    except ImportError as e:
        logger.debug("Flask integration not available: %s", e)


class AirflowMCPPlugin(AirflowPlugin):
    """Plugin to integrate MCP server with Airflow.

    Exposes MCP protocol endpoints at /mcp/v1/ for AI clients
    (Cursor, Claude Desktop, etc.).
    Supports Airflow 2.x (Flask blueprint) and 3.x (FastAPI app).
    """

    name = "astro_airflow_mcp"
    fastapi_apps = fastapi_apps_config
    flask_blueprints = flask_blueprints_config

    @classmethod
    def on_load(cls, *_args: Any, **_kwargs: Any) -> None:
        """Called when the plugin is loaded."""
        if cls.fastapi_apps:
            logger.info("Airflow MCP Plugin loaded (AF3 FastAPI mode)")
        elif cls.flask_blueprints:
            logger.info("Airflow MCP Plugin loaded (AF2 Flask mode)")
        else:
            logger.warning("Airflow MCP Plugin loaded but no integration available")


__all__ = ["AirflowMCPPlugin"]
