"""Shared telemetry primitives for af CLI and MCP server."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess  # nosec B404 - subprocess is needed for fire-and-forget telemetry
import sys
import uuid
from pathlib import Path
from typing import Any

from fastmcp.server.middleware import Middleware

# Telemetry API configuration
TELEMETRY_API_URL = "https://api.astronomer.io/v1alpha1/telemetry"
TELEMETRY_TIMEOUT_SECONDS = 3

# Source identifiers
CLI_TELEMETRY_SOURCE = "af-cli"
MCP_TELEMETRY_SOURCE = "astro-airflow-mcp"

# Environment variables
TELEMETRY_DISABLED_ENV = "AF_TELEMETRY_DISABLED"
TELEMETRY_DEBUG_ENV = "AF_TELEMETRY_DEBUG"

# File to store anonymous user ID
ANONYMOUS_ID_FILE = Path.home() / ".af" / ".anonymous_id"


def _get_anonymous_id() -> str:
    """Get or create a persistent anonymous user ID."""
    try:
        if ANONYMOUS_ID_FILE.exists():
            value = ANONYMOUS_ID_FILE.read_text().strip()
            # Validate it looks like a UUID (36 chars: 8-4-4-4-12)
            if len(value) == 36:
                uuid.UUID(value)
                return value
    except (OSError, ValueError):
        pass

    # Generate new ID (also regenerates if existing file was invalid)
    anonymous_id = str(uuid.uuid4())

    # Persist it
    try:
        ANONYMOUS_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        ANONYMOUS_ID_FILE.write_text(anonymous_id)
    except OSError:
        pass  # Continue even if we can't persist

    return anonymous_id


def _is_telemetry_disabled() -> bool:
    """Check if telemetry is disabled via environment variable or config file."""
    # Environment variable takes precedence
    disabled = os.environ.get(TELEMETRY_DISABLED_ENV, "").lower()
    if disabled in ("1", "true", "yes"):
        return True

    # Check config file
    with contextlib.suppress(Exception):
        from astro_airflow_mcp.config.loader import ConfigManager

        config = ConfigManager().load()
        if config.telemetry_disabled:
            return True

    return False


def _detect_invocation_context() -> tuple[str, str | None]:
    """Detect if running interactively or via an agent/automation.

    Returns:
        Tuple of (context, agent_name):
        - context: 'agent', 'ci', 'interactive', or 'non-interactive'
        - agent_name: specific agent/CI name if detected, None otherwise
    """
    # Check for known AI agent environment variables
    agent_env_vars = {
        "CLAUDECODE": "claude-code",
        "CLAUDE_CODE_ENTRYPOINT": "claude-code",
        "CURSOR_TRACE_ID": "cursor",
        "AIDER_MODEL": "aider",
        "CONTINUE_GLOBAL_DIR": "continue",
    }
    for var, agent_name in agent_env_vars.items():
        if os.environ.get(var):
            return ("agent", agent_name)

    # Check for CI/CD environments
    ci_env_vars = {
        "GITHUB_ACTIONS": "github-actions",
        "GITLAB_CI": "gitlab-ci",
        "JENKINS_URL": "jenkins",
        "CIRCLECI": "circleci",
        "CI": "ci-unknown",  # Generic CI flag, check last
    }
    for var, ci_name in ci_env_vars.items():
        if os.environ.get(var):
            return ("ci", ci_name)

    # Check if running in an interactive terminal
    if sys.stdin.isatty() and sys.stdout.isatty():
        return ("interactive", None)

    return ("non-interactive", None)


_SEND_SCRIPT = """\
import json, sys
from urllib import request, error

d = json.loads(sys.stdin.read())
data = json.dumps(d["body"]).encode("utf-8")
req = request.Request(
    d["api_url"], data=data,
    headers={"Content-Type": "application/json"}, method="POST",
)
debug = d.get("debug", False)
try:
    with request.urlopen(req, timeout=__TIMEOUT__) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        if debug:
            print(f"[telemetry] response: {resp.status} {body}", file=sys.stderr)
except error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    if debug:
        print(f"[telemetry] error: {e.code} {body}", file=sys.stderr)
except Exception as e:
    if debug:
        print(f"[telemetry] error: {e}", file=sys.stderr)
"""


def _send(api_url: str, body: dict, *, debug: bool = False) -> None:
    """Send telemetry event in a detached subprocess.

    When debug=True, logs request/response details to stderr and waits for
    the subprocess to finish. Otherwise fire-and-forget.
    """
    payload = json.dumps({"api_url": api_url, "body": body, "debug": debug})

    if debug:
        sys.stderr.write(f"[telemetry] POST {api_url}\n")
        sys.stderr.write(f"[telemetry] body: {json.dumps(body, indent=2)}\n")

    # Uses only stdlib (urllib) - no external dependencies needed.
    # In debug mode the subprocess prints request/response info to stderr,
    # which we pass through to the parent process.
    script = _SEND_SCRIPT.replace("__TIMEOUT__", str(TELEMETRY_TIMEOUT_SECONDS))

    with contextlib.suppress(Exception):
        proc = subprocess.Popen(  # nosec B603 - no untrusted input, script and args are hardcoded
            [sys.executable, "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=None if debug else subprocess.DEVNULL,
            start_new_session=not debug,
        )
        proc.stdin.write(payload.encode())
        proc.stdin.close()
        if debug:
            proc.wait()


def track_tool_call(tool_name: str, *, success: bool = True) -> None:
    """Track an MCP tool call invocation.

    Sends a telemetry event for each tool call with the tool name and
    success/failure status. Uses fire-and-forget subprocess dispatch.

    Args:
        tool_name: Name of the MCP tool that was called
        success: Whether the tool call succeeded
    """
    if _is_telemetry_disabled():
        return

    anonymous_id = _get_anonymous_id()
    context, agent = _detect_invocation_context()

    from astro_airflow_mcp import __version__

    properties: dict[str, object] = {
        "tool": tool_name,
        "success": success,
        "af_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "context": context,
    }
    if agent:
        properties["agent"] = agent

    api_url = os.environ.get("AF_TELEMETRY_API_URL", TELEMETRY_API_URL)
    debug = os.environ.get(TELEMETRY_DEBUG_ENV, "").lower() in ("1", "true", "yes")

    body = {
        "source": MCP_TELEMETRY_SOURCE,
        "event": "MCP Tool Call",
        "anonymousId": anonymous_id,
        "properties": properties,
    }

    _send(api_url, body, debug=debug)


class TelemetryMiddleware(Middleware):
    """FastMCP middleware that tracks tool calls via telemetry.

    Intercepts each tool call, lets it execute, then fires a telemetry
    event with the tool name and success/failure status.
    """

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        tool_name = context.message.name
        try:
            result = await call_next(context)
            track_tool_call(tool_name, success=True)
            return result
        except Exception:
            track_tool_call(tool_name, success=False)
            raise
