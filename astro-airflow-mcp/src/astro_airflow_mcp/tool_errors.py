"""Structured, agent-friendly error responses for MCP tools.

MCP tools in this server return JSON strings. On failure we return a JSON
object instead of a bare ``str(exc)`` so the calling agent can tell *why* a
call failed and decide what to do next:

    {
      "error": "<message>",        # always contains str(exc)
      "error_type": "NotFoundError",
      "hint": "<what to do next>", # actionable guidance for the agent
      "retryable": true,          # True  -> a corrected retry may succeed
                                  # False -> auth/infra/hard block; don't spin
      "dag_id": "...",            # any identifying args echoed back
    }

The distinction that matters for an agent: a *wrong dag_id* (fix the argument
and retry) looks identical to *Airflow is unreachable* (stop and surface to the
user) when both are collapsed to a bare string. ``retryable`` + ``hint``
disambiguate them; the echoed identifiers give the model the context it needs
to correct itself.

``str(exc)`` is always kept inside ``error`` so callers (and tests) that scanned
the old bare-string responses for substrings keep working.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from astro_airflow_mcp.adapters.base import NotFoundError, ReadOnlyError

try:  # Auth errors live in the astro session module; treat as optional.
    from astro_airflow_mcp._astro_session import AstroPATError
except Exception:  # pragma: no cover - defensive, _astro_session is import-light
    AstroPATError = None  # type: ignore[assignment, misc]


def _classify_status(exc: httpx.HTTPStatusError) -> tuple[bool, str]:
    """Map an HTTP status code to (retryable, hint)."""
    status = exc.response.status_code
    if status in (400, 422):
        return True, (
            f"Airflow rejected the request as invalid (HTTP {status}). Check the "
            "argument values and formats, then retry with corrected arguments."
        )
    if status in (401, 403):
        return False, (
            f"Not authorized (HTTP {status}). The token may be missing, expired, or "
            "lack permission for this operation. Re-authenticate and restart the "
            "MCP server, then try again."
        )
    if status == 404:
        return True, (
            "Not found (HTTP 404). Verify the identifiers are correct — a list_* "
            "tool (list_dags / list_dag_runs / list_tasks) can confirm valid values."
        )
    if status == 409:
        return False, (
            "Conflict (HTTP 409). The resource is in a state that does not allow "
            "this operation (e.g. it already exists or is currently running). "
            "Retrying the same call is unlikely to help."
        )
    if status == 429:
        return True, "Rate limited (HTTP 429). Wait briefly before retrying."
    if 500 <= status < 600:
        return False, (
            f"Airflow returned a server error (HTTP {status}). This is an "
            "instance-side problem; retrying the same call is unlikely to help."
        )
    return False, f"Airflow returned an unexpected HTTP {status}."


def _classify(exc: Exception) -> tuple[bool, str]:
    """Return ``(retryable, hint)`` inferred from the exception type."""
    if isinstance(exc, ReadOnlyError):
        return False, (
            "The server is running in read-only mode (AF_READ_ONLY=true), so this "
            "write was blocked. Do not retry; ask the operator to disable read-only "
            "mode if the change is intended."
        )
    if isinstance(exc, NotFoundError):
        return True, (
            "The resource was not found. Check the spelling/values of the "
            "identifiers (dag_id, dag_run_id, task_id) — a list_* tool can confirm "
            "valid values."
        )
    if AstroPATError is not None and isinstance(exc, AstroPATError):
        return False, (
            "Authentication with Astro failed. Re-authenticate (run `astro login`) "
            "and restart the MCP server, then try again."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return _classify_status(exc)
    if isinstance(exc, httpx.TimeoutException):
        return False, (
            "Airflow did not respond in time. The instance may be slow or "
            "unreachable; verify it is up and reachable before retrying."
        )
    if isinstance(exc, httpx.TransportError):
        # ConnectError, ReadError, etc. all subclass TransportError.
        return False, (
            "Could not reach Airflow. Check that the instance is running and that "
            "the configured URL and network are correct."
        )
    return False, (
        "The Airflow API call failed unexpectedly. Inspect the error message; this "
        "is more likely a server-side or configuration issue than a bad argument."
    )


def error_payload(
    exc: Exception,
    *,
    retryable: bool | None = None,
    hint: str | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Build a structured error dict from an exception.

    Args:
        exc: The caught exception. ``str(exc)`` is always placed in ``error``.
        retryable: Override the inferred retryability.
        hint: Override the inferred hint.
        **context: Identifying arguments to echo back (e.g. ``dag_id=dag_id``).
            ``None`` values are dropped so we never echo empty identifiers.

    Returns:
        A JSON-serializable dict with at least ``error``, ``error_type``,
        ``hint`` and ``retryable`` keys, plus any non-None context.
    """
    inferred_retryable, inferred_hint = _classify(exc)
    payload: dict[str, Any] = {
        "error": str(exc) or exc.__class__.__name__,
        "error_type": exc.__class__.__name__,
        "hint": hint if hint is not None else inferred_hint,
        "retryable": retryable if retryable is not None else inferred_retryable,
    }
    for key, value in context.items():
        if value is not None:
            payload[key] = value
    return payload


def tool_error(
    exc: Exception,
    *,
    retryable: bool | None = None,
    hint: str | None = None,
    **context: Any,
) -> str:
    """JSON-string form of :func:`error_payload` for MCP tool return values."""
    return json.dumps(error_payload(exc, retryable=retryable, hint=hint, **context), indent=2)
