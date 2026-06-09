"""Tests for MCP tool safety annotations and the end-to-end error round-trip.

The end-to-end tests drive the real FastMCP server through an in-memory
``Client``, so they exercise tool registration, annotation serialization, and
the full call -> tool -> JSON-error path the way a real MCP client would.
"""

import asyncio
import json
from unittest.mock import MagicMock

from fastmcp import Client

from astro_airflow_mcp.adapters.base import NotFoundError, ReadOnlyError
from astro_airflow_mcp.server import mcp
from astro_airflow_mcp.tool_annotations import read_only, write

# Every write tool and its expected (destructiveHint, idempotentHint).
# Everything not listed here must be advertised as read-only.
WRITE_TOOLS = {
    "pause_dag": (False, True),
    "unpause_dag": (False, True),
    "trigger_dag": (False, False),
    "trigger_dag_and_wait": (False, False),
    "delete_dag_run": (True, False),
    "clear_dag_run": (True, True),
    "clear_task_instances": (True, True),
}


def _list_tools():
    async def run():
        async with Client(mcp) as client:
            return await client.list_tools()

    return asyncio.run(run())


def _call_tool(name: str, args: dict):
    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


class TestAnnotationHelpers:
    def test_read_only_is_safe_and_idempotent(self):
        ann = read_only()
        assert ann.readOnlyHint is True
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True
        assert ann.openWorldHint is True

    def test_write_defaults_are_cautious(self):
        ann = write()
        assert ann.readOnlyHint is False
        assert ann.destructiveHint is True
        assert ann.idempotentHint is False

    def test_write_can_be_narrowed(self):
        ann = write(destructive=False, idempotent=True)
        assert ann.destructiveHint is False
        assert ann.idempotentHint is True


class TestServerAnnotations:
    def test_every_tool_is_annotated(self):
        tools = _list_tools()
        assert tools  # server registered something
        missing = [t.name for t in tools if not t.annotations]
        assert missing == []

    def test_write_tools_have_correct_hints(self):
        tools = {t.name: t for t in _list_tools()}
        for name, (destructive, idempotent) in WRITE_TOOLS.items():
            ann = tools[name].annotations
            assert ann is not None, name
            assert ann.readOnlyHint is False, name
            assert ann.destructiveHint is destructive, name
            assert ann.idempotentHint is idempotent, name

    def test_all_other_tools_are_read_only(self):
        tools = {t.name: t for t in _list_tools()}
        read_names = set(tools) - set(WRITE_TOOLS)
        for name in read_names:
            assert tools[name].annotations.readOnlyHint is True, name


class TestStructuredErrorRoundTrip:
    """A failing tool returns structured JSON through the MCP protocol."""

    def test_not_found_error_round_trips(self, mocker):
        mock_adapter = MagicMock()
        mock_adapter.get_dag.side_effect = NotFoundError("dags/nope")
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

        result = _call_tool("get_dag_details", {"dag_id": "nope"})
        data = json.loads(result.content[0].text)

        assert data["error_type"] == "NotFoundError"
        assert data["dag_id"] == "nope"
        assert data["retryable"] is True
        assert data["hint"]

    def test_read_only_block_round_trips(self, mocker, monkeypatch):
        monkeypatch.setenv("AF_READ_ONLY", "true")
        mock_adapter = MagicMock()
        mock_adapter.pause_dag.side_effect = ReadOnlyError("PATCH dags/my_dag")
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

        result = _call_tool("pause_dag", {"dag_id": "my_dag"})
        data = json.loads(result.content[0].text)

        assert data["error_type"] == "ReadOnlyError"
        assert data["retryable"] is False
        assert "read-only mode" in data["error"]
        assert data["dag_id"] == "my_dag"
