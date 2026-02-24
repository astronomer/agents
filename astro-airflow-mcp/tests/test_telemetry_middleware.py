"""Tests for MCP telemetry middleware and track_tool_call."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from astro_airflow_mcp import telemetry


@dataclass
class FakeMessage:
    """Minimal stand-in for CallToolRequestParams."""

    name: str
    arguments: dict | None = None


@dataclass
class FakeContext:
    """Minimal stand-in for MiddlewareContext."""

    message: FakeMessage
    method: str = "tools/call"


class TestTrackToolCall:
    """Tests for track_tool_call."""

    def test_sends_correct_payload(self, mocker, monkeypatch):
        """Test sends expected MCP tool call event body."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_API_URL", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.telemetry._send")
        mocker.patch("astro_airflow_mcp.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.telemetry._detect_invocation_context",
            return_value=("agent", "claude-code"),
        )

        telemetry.track_tool_call("list_dags", success=True)

        mock_send.assert_called_once()
        api_url, body = mock_send.call_args[0]
        assert api_url == telemetry.TELEMETRY_API_URL
        assert body["source"] == "astro-airflow-mcp"
        assert body["event"] == "MCP Tool Call"
        assert body["anonymousId"] == "test-id"
        assert body["properties"]["tool"] == "list_dags"
        assert body["properties"]["success"] is True
        assert body["properties"]["context"] == "agent"
        assert body["properties"]["agent"] == "claude-code"

    def test_tracks_failure(self, mocker, monkeypatch):
        """Test tracks tool call failure."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_API_URL", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.telemetry._send")
        mocker.patch("astro_airflow_mcp.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.telemetry._detect_invocation_context",
            return_value=("non-interactive", None),
        )

        telemetry.track_tool_call("get_dag_details", success=False)

        mock_send.assert_called_once()
        _, body = mock_send.call_args[0]
        assert body["properties"]["tool"] == "get_dag_details"
        assert body["properties"]["success"] is False
        assert "agent" not in body["properties"]

    def test_skips_when_disabled(self, mocker):
        """Test does not send when telemetry is disabled."""
        mock_send = mocker.patch("astro_airflow_mcp.telemetry._send")
        mocker.patch("astro_airflow_mcp.telemetry._is_telemetry_disabled", return_value=True)

        telemetry.track_tool_call("list_dags")

        mock_send.assert_not_called()

    def test_api_url_override(self, mocker, monkeypatch):
        """Test API URL can be overridden via env var."""
        monkeypatch.setenv("AF_TELEMETRY_API_URL", "https://custom.example.com/telemetry")
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.telemetry._send")
        mocker.patch("astro_airflow_mcp.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.telemetry._detect_invocation_context",
            return_value=("interactive", None),
        )

        telemetry.track_tool_call("list_dags")

        api_url = mock_send.call_args[0][0]
        assert api_url == "https://custom.example.com/telemetry"

    def test_not_idempotent(self, mocker, monkeypatch):
        """Test tool calls are tracked every time (unlike CLI which is once-only)."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_API_URL", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.telemetry._send")
        mocker.patch("astro_airflow_mcp.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.telemetry._detect_invocation_context",
            return_value=("agent", "claude-code"),
        )

        telemetry.track_tool_call("list_dags")
        telemetry.track_tool_call("get_dag_details")

        assert mock_send.call_count == 2


class TestTelemetryMiddleware:
    """Tests for TelemetryMiddleware."""

    @pytest.fixture
    def middleware(self):
        return telemetry.TelemetryMiddleware()

    def test_tracks_successful_tool_call(self, middleware, mocker):
        """Test middleware tracks successful tool call and returns result."""
        mock_track = mocker.patch("astro_airflow_mcp.telemetry.track_tool_call")
        context = FakeContext(message=FakeMessage(name="list_dags"))

        async def call_next(ctx):
            return "tool result"

        result = asyncio.run(middleware.on_call_tool(context, call_next))

        assert result == "tool result"
        mock_track.assert_called_once_with("list_dags", success=True)

    def test_tracks_failed_tool_call(self, middleware, mocker):
        """Test middleware tracks failure and re-raises exception."""
        mock_track = mocker.patch("astro_airflow_mcp.telemetry.track_tool_call")
        context = FakeContext(message=FakeMessage(name="get_dag_details"))

        async def call_next(ctx):
            raise ValueError("something went wrong")

        with pytest.raises(ValueError, match="something went wrong"):
            asyncio.run(middleware.on_call_tool(context, call_next))

        mock_track.assert_called_once_with("get_dag_details", success=False)

    def test_passes_context_through(self, middleware, mocker):
        """Test middleware passes context to call_next unchanged."""
        mocker.patch("astro_airflow_mcp.telemetry.track_tool_call")
        context = FakeContext(message=FakeMessage(name="trigger_dag"))
        received_context = None

        async def call_next(ctx):
            nonlocal received_context
            received_context = ctx
            return "ok"

        asyncio.run(middleware.on_call_tool(context, call_next))

        assert received_context is context
