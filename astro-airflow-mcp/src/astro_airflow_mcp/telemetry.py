"""Shared telemetry primitives for af CLI and MCP server."""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess  # nosec B404 - subprocess is needed for fire-and-forget telemetry
import sys
import uuid
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


def _get_anonymous_id() -> str:
    """Get or create a persistent anonymous user ID.

    Reads from the ``telemetry.anonymous_id`` field in config.yaml.
    If not present, generates a new UUID and persists it to config.
    """
    with contextlib.suppress(Exception):
        from astro_airflow_mcp.config.loader import ConfigManager

        cm = ConfigManager()
        config = cm.load()

        if config.telemetry.anonymous_id:
            return config.telemetry.anonymous_id

        anonymous_id = str(uuid.uuid4())
        config.telemetry.anonymous_id = anonymous_id
        cm.save(config)
        return anonymous_id

    # Fallback if config operations fail
    return str(uuid.uuid4())


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
        if not config.telemetry.enabled:
            return True

    return False


def _detect_invocation_context() -> tuple[str, str | None, str | None]:
    """Detect if running interactively or via an agent/automation.

    Returns:
        Tuple of (context, agent_name, ci_system):
        - context: 'agent', 'ci', 'interactive', or 'non-interactive'
        - agent_name: specific AI agent name if detected, None otherwise
        - ci_system: specific CI/CD system name if detected, None otherwise
    """
    agent_name: str | None = None
    ci_system: str | None = None

    # Check for known AI agent environment variables
    agent_env_vars = {
        "CLAUDECODE": "claude-code",
        "CLAUDE_CODE_ENTRYPOINT": "claude-code",
        "CURSOR_TRACE_ID": "cursor",
        "CURSOR_AGENT": "cursor",
        "AIDER_MODEL": "aider",
        "CONTINUE_GLOBAL_DIR": "continue",
        "CORTEX_SESSION_ID": "snowflake-cortex",
        "GEMINI_CLI": "gemini-cli",
        "OPENCODE": "opencode",
        "CODEX_API_KEY": "codex",
    }
    for var, name in agent_env_vars.items():
        if os.environ.get(var):
            agent_name = name
            break

    # Check for CI/CD environments
    ci_env_vars = {
        "GITHUB_ACTIONS": "github-actions",
        "GITLAB_CI": "gitlab-ci",
        "JENKINS_URL": "jenkins",
        "HUDSON_URL": "jenkins",
        "CIRCLECI": "circleci",
        "TF_BUILD": "azure-devops",
        "BITBUCKET_BUILD_NUMBER": "bitbucket-pipelines",
        "CODEBUILD_BUILD_ID": "aws-codebuild",
        "TEAMCITY_VERSION": "teamcity",
        "BUILDKITE": "buildkite",
        "CF_BUILD_ID": "codefresh",
        "TRAVIS": "travis-ci",
        "CI": "ci-unknown",  # Generic CI flag, check last
    }
    for var, name in ci_env_vars.items():
        if os.environ.get(var):
            ci_system = name
            break

    # Determine primary context
    if agent_name:
        context = "agent"
    elif ci_system:
        context = "ci"
    elif sys.stdin.isatty() and sys.stdout.isatty():
        context = "interactive"
    else:
        context = "non-interactive"

    return (context, agent_name, ci_system)


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
        stdin = proc.stdin  # Always set when stdin=subprocess.PIPE
        if stdin is not None:
            stdin.write(payload.encode())
            stdin.close()
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
    context, agent, ci_system = _detect_invocation_context()

    from astro_airflow_mcp import __version__

    properties: dict[str, object] = {
        "tool": tool_name,
        "success": success,
        "cli_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "os": platform.system().lower(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
        "context": context,
    }
    if agent:
        properties["agent"] = agent
    if ci_system:
        properties["ci_system"] = ci_system

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
