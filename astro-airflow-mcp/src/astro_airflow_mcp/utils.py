"""Shared utility functions for CLI and MCP server."""

from collections import Counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from astro_airflow_mcp.constants import DEFAULT_LIMIT, FAILED_TASK_STATES


def normalize_airflow_url(url: str) -> str:
    """Strip query string, fragment, and trailing slash from an Airflow base URL.

    API URLs are built by concatenation (eg ``f"{airflow_url}/api/v2/version"``),
    so a stored URL like ``https://host/dep?orgId=foo`` produces the malformed
    ``https://host/dep?orgId=foo/api/v2/version`` — the path stays at ``/dep``
    and ``/api/...`` ends up inside the query string. Normalizing once at the
    boundary keeps every downstream call safe.

    Any userinfo (``user:password@``) is also dropped: credentials are supplied
    separately via the token/basic-auth getters, and the normalized URL can end
    up in logs and in structured tool errors surfaced to the model.
    """
    if not url:
        return url
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    # Strip any ``user:password@`` userinfo while preserving host[:port] (and
    # IPv6 brackets) verbatim.
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, path, "", ""))


def filter_connection_passwords(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter sensitive fields from connections.

    Returns connection metadata with passwords excluded for security.

    Args:
        connections: List of connection dicts from the Airflow API

    Returns:
        List of connections with only safe fields included
    """
    return [
        {
            "connection_id": conn.get("connection_id"),
            "conn_type": conn.get("conn_type"),
            "description": conn.get("description"),
            "host": conn.get("host"),
            "port": conn.get("port"),
            "schema": conn.get("schema"),
            "login": conn.get("login"),
            "extra": conn.get("extra"),
        }
        for conn in connections
    ]


def extract_failed_tasks(task_instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract failed task info from task instances.

    Args:
        task_instances: List of task instance dicts from the Airflow API

    Returns:
        List of failed task details with relevant fields
    """
    return [
        {
            "task_id": task.get("task_id"),
            "map_index": task.get("map_index"),
            "state": task.get("state"),
            "try_number": task.get("try_number"),
            "start_date": task.get("start_date"),
            "end_date": task.get("end_date"),
        }
        for task in task_instances
        if task.get("state") in FAILED_TASK_STATES
    ]


def summarize_failed_tasks(
    task_instances: list[dict[str, Any]], include_all_failed_tasks: bool = False
) -> dict[str, Any]:
    """Count all failures and return bounded details, with actual failures first."""
    failed = extract_failed_tasks(task_instances)
    failed.sort(key=lambda task: task["state"] != "failed")
    sample = failed if include_all_failed_tasks else failed[:DEFAULT_LIMIT]
    return {
        "failed_tasks": sample,
        "failed_tasks_total": len(failed),
        "failed_tasks_returned": len(sample),
        "failed_tasks_truncated": len(sample) < len(failed),
    }


def summarize_task_instances(
    task_instances: list[dict[str, Any]], include_all_failed_tasks: bool = False
) -> dict[str, Any]:
    """Summarize every instance, retaining only a bounded sample of full details.

    Counts cover the complete listing. Failed-task details default to 100 with
    an opt-in for all. The full-detail sample always stays bounded, prioritizing
    failed, then upstream_failed instances. MCP and CLI share this format.
    """
    state_order = {"failed": 0, "upstream_failed": 1}
    sample = sorted(task_instances, key=lambda task: state_order.get(task.get("state"), 2))[
        :DEFAULT_LIMIT
    ]
    return {
        "task_instances": sample,
        "task_instances_returned": len(sample),
        "task_instances_truncated": len(sample) < len(task_instances),
        "summary": {
            "total_tasks": len(task_instances),
            "state_counts": dict(
                Counter(task.get("state") or "unknown" for task in task_instances)
            ),
            **summarize_failed_tasks(task_instances, include_all_failed_tasks),
        },
    }


def wrap_list_response(
    items: list[dict[str, Any]], key_name: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Wrap API list response with pagination metadata.

    Args:
        items: List of items from the API
        key_name: Name for the items key in response (e.g., 'dags', 'dag_runs')
        data: Original API response data (for total_entries)

    Returns:
        Dict with pagination metadata
    """
    total_entries = data.get("total_entries", len(items))
    return {
        f"total_{key_name}": total_entries,
        "returned_count": len(items),
        key_name: items,
    }
