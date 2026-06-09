"""Tests for structured, agent-friendly tool error responses (``tool_errors``)."""

import json

import httpx
import pytest

from astro_airflow_mcp.adapters.base import NotFoundError, ReadOnlyError
from astro_airflow_mcp.tool_errors import error_payload, tool_error


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError carrying the given status code."""
    request = httpx.Request("GET", "http://airflow.example/api/v2/dags")
    response = httpx.Response(status_code=status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


class TestErrorPayloadShape:
    """The payload always carries error/error_type/hint/retryable."""

    def test_includes_message_type_hint_and_retryable(self):
        payload = error_payload(ValueError("boom"))

        assert payload["error"] == "boom"
        assert payload["error_type"] == "ValueError"
        assert payload["hint"]  # non-empty
        assert payload["retryable"] is False  # unknown -> don't spin

    def test_empty_message_falls_back_to_class_name(self):
        payload = error_payload(ValueError())

        assert payload["error"] == "ValueError"

    def test_echoes_context_and_drops_none(self):
        payload = error_payload(ValueError("x"), dag_id="d", dag_run_id=None)

        assert payload["dag_id"] == "d"
        assert "dag_run_id" not in payload

    def test_explicit_overrides_win_over_inference(self):
        payload = error_payload(ValueError("x"), retryable=True, hint="do this")

        assert payload["retryable"] is True
        assert payload["hint"] == "do this"


class TestExceptionClassification:
    """Retryability is inferred from the exception type / status code."""

    def test_not_found_is_retryable(self):
        payload = error_payload(NotFoundError("dags/missing"))

        assert payload["error_type"] == "NotFoundError"
        assert payload["retryable"] is True

    def test_read_only_blocks_and_preserves_substrings(self):
        # Backward-compat: callers/tests scanned the old bare string for these.
        exc = ReadOnlyError("PATCH dags/my_dag")
        payload = error_payload(exc, dag_id="my_dag")

        assert payload["retryable"] is False
        assert "read-only mode" in payload["error"]
        assert "PATCH dags/my_dag" in payload["error"]
        assert payload["dag_id"] == "my_dag"

    @pytest.mark.parametrize(
        ("status", "retryable"),
        [
            (400, True),
            (422, True),
            (401, False),
            (403, False),
            (404, True),
            (409, False),
            (429, True),
            (500, False),
            (503, False),
        ],
    )
    def test_http_status_classification(self, status, retryable):
        payload = error_payload(_http_status_error(status))

        assert payload["retryable"] is retryable
        assert str(status) in payload["hint"]

    def test_http_status_error_echoes_context(self):
        payload = error_payload(_http_status_error(404), dag_id="etl", dag_run_id=None)

        assert payload["dag_id"] == "etl"
        assert "dag_run_id" not in payload
        assert payload["retryable"] is True

    def test_timeout_is_not_retryable(self):
        payload = error_payload(httpx.TimeoutException("slow"))

        assert payload["retryable"] is False
        assert "respond" in payload["hint"].lower()

    def test_connect_error_is_not_retryable(self):
        payload = error_payload(httpx.ConnectError("connection refused"))

        assert payload["retryable"] is False
        assert "reach airflow" in payload["hint"].lower()


class TestToolError:
    """``tool_error`` is the JSON-string form returned by MCP tools."""

    def test_returns_parseable_json(self):
        result = tool_error(NotFoundError("dags/x"), dag_id="x")
        data = json.loads(result)

        assert data["error_type"] == "NotFoundError"
        assert data["dag_id"] == "x"
        assert data["retryable"] is True
        assert data["hint"]
