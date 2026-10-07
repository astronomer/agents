"""Tests for MCP tool allowlist configuration."""

import asyncio
import json
import os
import subprocess
import sys

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from astro_airflow_mcp.tool_policy import apply_tool_allowlist, parse_allowed_tools


def test_single_tool():
    assert parse_allowed_tools("list_dags") == frozenset({"list_dags"})


def test_comma_separated_tools():
    assert parse_allowed_tools("list_dags,get_dag_details") == frozenset(
        {"list_dags", "get_dag_details"}
    )


def test_whitespace_and_duplicates_are_ignored():
    assert parse_allowed_tools(" list_dags,\n get_dag_details , list_dags ") == frozenset(
        {"list_dags", "get_dag_details"}
    )


def test_tool_names_remain_case_sensitive():
    assert parse_allowed_tools("LIST_DAGS,list_dags") == frozenset({"LIST_DAGS", "list_dags"})


@pytest.mark.parametrize(
    "value",
    [
        "",
        " \n ",
        ",",
        "list_dags,",
        ",list_dags",
        "list_dags,,get_dag_details",
        "list_dags, ,get_dag_details",
    ],
)
def test_empty_entries_are_rejected(value):
    with pytest.raises(ValueError, match=r"ASTRO_MCP_ALLOWED_TOOLS.*no empty entries"):
        parse_allowed_tools(value)


@pytest.fixture
def policy_server(mocker):
    server = FastMCP("Tool policy test")
    blocked_call = mocker.Mock()

    @server.tool
    def allowed() -> str:
        return "allowed result"

    @server.tool
    def blocked() -> str:
        blocked_call()
        return "blocked result"

    @server.resource("test://resource")
    def resource() -> str:
        return "resource result"

    @server.prompt(name="blocked")
    def blocked_prompt() -> str:
        return "prompt result"

    return server, blocked_call


def test_unset_policy_preserves_all_tools(policy_server):
    server, _ = policy_server

    async def run():
        await apply_tool_allowlist(server, None)
        async with Client(server) as client:
            assert {tool.name for tool in await client.list_tools()} == {"allowed", "blocked"}
            assert (await client.call_tool("blocked", {})).content[0].text == "blocked result"

    asyncio.run(run())


def test_allowlist_filters_discovery_and_blocks_invocation(policy_server):
    server, blocked_call = policy_server

    async def run():
        await apply_tool_allowlist(server, "allowed")
        async with Client(server) as client:
            assert {tool.name for tool in await client.list_tools()} == {"allowed"}
            assert (await client.call_tool("allowed", {})).content[0].text == "allowed result"
            with pytest.raises(ToolError, match="blocked"):
                await client.call_tool("blocked", {})

            assert len(await client.list_resources()) == 1
            assert (await client.read_resource("test://resource"))[0].text == "resource result"
            assert {prompt.name for prompt in await client.list_prompts()} == {"blocked"}
            assert (await client.get_prompt("blocked")).messages[0].content.text == "prompt result"

    asyncio.run(run())
    blocked_call.assert_not_called()


def test_unknown_names_expose_no_tools(policy_server, caplog):
    # A raise here would stop the Airflow API server in plugin mode, so
    # unknown names must instead hide every tool and log the error.
    server, _ = policy_server

    async def run():
        await apply_tool_allowlist(server, "allowed,typo_b,typo_a")
        async with Client(server) as client:
            assert await client.list_tools() == []
            with pytest.raises(ToolError, match="allowed"):
                await client.call_tool("allowed", {})
            assert len(await client.list_resources()) == 1
            assert {prompt.name for prompt in await client.list_prompts()} == {"blocked"}

    asyncio.run(run())
    assert "Unknown tool names" in caplog.text
    assert "typo_a, typo_b" in caplog.text


def test_malformed_value_exposes_no_tools(policy_server, caplog):
    # Same fail-closed path as unknown names: a raise here would stop the
    # Airflow API server in plugin mode, so the server hides every tool and
    # logs the error instead.
    server, _ = policy_server

    async def run():
        await apply_tool_allowlist(server, "allowed,")
        async with Client(server) as client:
            assert await client.list_tools() == []
            with pytest.raises(ToolError, match="allowed"):
                await client.call_tool("allowed", {})
            assert len(await client.list_resources()) == 1
            assert {prompt.name for prompt in await client.list_prompts()} == {"blocked"}

    asyncio.run(run())
    assert "ASTRO_MCP_ALLOWED_TOOLS" in caplog.text
    assert "Exposing no tools" in caplog.text


def test_later_registered_tools_are_still_blocked(policy_server):
    server, _ = policy_server

    async def run():
        await apply_tool_allowlist(server, "allowed")

        @server.tool
        def added_later() -> str:
            return "new tool"

        async with Client(server) as client:
            assert {tool.name for tool in await client.list_tools()} == {"allowed"}
            with pytest.raises(ToolError, match="added_later"):
                await client.call_tool("added_later", {})

    asyncio.run(run())


# Separate processes exercise the actual environment/startup wiring without
# mutating the shared MCP server imported by other test modules.
_SERVER_PROBE = """
import asyncio
import json
from unittest.mock import Mock, patch
from fastmcp import Client
from astro_airflow_mcp.server import mcp

async def run():
    adapter = Mock()
    adapter.list_dags.return_value = {"dags": [], "total_entries": 0}
    with patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=adapter), \\
         patch("astro_airflow_mcp.tools.admin._get_adapter") as admin_adapter:
        async with Client(mcp) as client:
            names = sorted(tool.name for tool in await client.list_tools())
            if "list_dags" in names:
                await client.call_tool("list_dags", {})
            if "get_variable" not in names:
                result = await client.call_tool(
                    "get_variable", {"variable_key": "secret"}, raise_on_error=False
                )
                assert result.is_error
                admin_adapter.assert_not_called()
            print(json.dumps(names))

asyncio.run(run())
"""


@pytest.mark.parametrize("value", [None, "list_dags,get_dag_details"])
def test_real_server_reads_environment_at_startup(value):
    env = {**os.environ, "AF_TELEMETRY_DISABLED": "1"}
    env.pop("ASTRO_MCP_ALLOWED_TOOLS", None)
    if value is not None:
        env["ASTRO_MCP_ALLOWED_TOOLS"] = value
    result = subprocess.run(
        [sys.executable, "-c", _SERVER_PROBE],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    names = set(json.loads(result.stdout))
    if value is None:
        assert {"list_dags", "get_variable", "list_connections", "trigger_dag"} <= names
    else:
        assert names == {"list_dags", "get_dag_details"}


# Malformed values surface at server startup, which in plugin mode belongs to
# the Airflow API server. The server must come up with no tools instead of
# failing. Parse-level variants are covered by test_empty_entries_are_rejected.
def test_real_server_exposes_no_tools_for_malformed_value():
    result = subprocess.run(
        [sys.executable, "-c", _SERVER_PROBE],
        env={**os.environ, "AF_TELEMETRY_DISABLED": "1", "ASTRO_MCP_ALLOWED_TOOLS": ""},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert "ASTRO_MCP_ALLOWED_TOOLS" in result.stderr


# Unknown names surface at server startup, which in plugin mode belongs to the
# Airflow API server. The server must come up with no tools instead of failing.
def test_real_server_exposes_no_tools_for_unknown_names():
    result = subprocess.run(
        [sys.executable, "-c", _SERVER_PROBE],
        env={
            **os.environ,
            "AF_TELEMETRY_DISABLED": "1",
            "ASTRO_MCP_ALLOWED_TOOLS": "list_dags,typo",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert "Unknown tool names" in result.stderr
