"""Configuration helpers for restricting the MCP tools exposed by the server."""

from typing import TYPE_CHECKING

from astro_airflow_mcp.constants import ALLOWED_TOOLS_ENV_VAR
from astro_airflow_mcp.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)


def parse_allowed_tools(value: str) -> frozenset[str]:
    """Parse the comma-separated ASTRO_MCP_ALLOWED_TOOLS setting.

    An empty value or an empty entry is a configuration error, never a
    fallback to unrestricted access. Names are case-sensitive; whitespace and
    duplicate names are ignored.

    This only validates the list format. Tool names must also be checked against
    the server's registered tools before applying the policy.
    """
    names = [name.strip() for name in value.split(",")]
    if any(not name for name in names):
        raise ValueError(
            f"{ALLOWED_TOOLS_ENV_VAR} must be a comma-separated list of tool names "
            "with no empty entries. Unset it to allow all tools."
        )

    return frozenset(names)


async def apply_tool_allowlist(server: "FastMCP", value: str | None) -> None:
    """Apply the allowlist setting (the raw env value) before serving requests.

    FastMCP visibility controls filter both discovery and invocation. Resources
    and prompts are unaffected. Call after tools have been registered.

    Configuration errors never raise: in plugin mode this code runs inside the
    Airflow API server's startup, where an exception stops the whole server,
    not just MCP. A malformed value and an unknown tool name both leave the
    server running with no tools and log the error, so the failure stays
    scoped to MCP and remains fail-closed.
    """
    if value is None:
        return

    try:
        allowed_tools = parse_allowed_tools(value)
    except ValueError as exc:
        server.disable(components={"tool"})
        logger.error("%s Exposing no tools until the value is fixed and the server restarts.", exc)
        return

    registered_tools = {tool.name for tool in await server.list_tools(run_middleware=False)}

    # Separate disable/enable calls keep the restriction scoped to tools.
    # FastMCP's enable(only=True) also disables resources and prompts.
    server.disable(components={"tool"})

    unknown = allowed_tools - registered_tools
    if unknown:
        logger.error(
            "Unknown tool names in %s: %s. Registered tools: %s. "
            "Exposing no tools until the value is fixed and the server restarts.",
            ALLOWED_TOOLS_ENV_VAR,
            ", ".join(sorted(unknown)),
            ", ".join(sorted(registered_tools)),
        )
        return

    server.enable(names=set(allowed_tools), components={"tool"})
    logger.info(
        "Tool allowlist active: exposing %d of %d tools: %s",
        len(allowed_tools),
        len(registered_tools),
        ", ".join(sorted(allowed_tools)),
    )
