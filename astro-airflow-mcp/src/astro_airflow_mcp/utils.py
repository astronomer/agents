"""Shared utility functions for CLI and MCP server."""

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from astro_airflow_mcp.constants import FAILED_TASK_STATES


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
            "state": task.get("state"),
            "try_number": task.get("try_number"),
            "start_date": task.get("start_date"),
            "end_date": task.get("end_date"),
        }
        for task in task_instances
        if task.get("state") in FAILED_TASK_STATES
    ]


def get_all_task_instances(
    adapter: Any, dag_id: str, dag_run_id: str, page_size: int = 100
) -> list[dict[str, Any]]:
    """Fetch every task instance for a DAG run, following pagination.

    A DAG run can have more task instances than the API's default page size
    (Airflow's `taskInstances` endpoint defaults to a limit of 100). Calling
    the adapter once and trusting the result silently drops every task past
    the first page -- with no indication anything was cut, since the caller's
    own `len(task_instances)` still looks like a plausible total. This loops
    on `total_entries` until every page has been collected.

    Args:
        adapter: An Airflow adapter exposing get_task_instances(dag_id, dag_run_id, limit, offset)
        dag_id: DAG ID
        dag_run_id: DAG run ID
        page_size: Page size to request per call

    Returns:
        The complete list of task instance dicts for the run
    """
    task_instances: list[dict[str, Any]] = []
    offset = 0
    while True:
        page_data = adapter.get_task_instances(dag_id, dag_run_id, limit=page_size, offset=offset)
        page = page_data.get("task_instances", [])
        task_instances.extend(page)

        total_entries = page_data.get("total_entries")
        # No total to compare against (e.g. a minimal/mocked adapter response),
        # or the API returned fewer than a full page -- either way, there's
        # nothing more to fetch.
        if total_entries is None or len(page) < page_size or len(task_instances) >= total_entries:
            break
        offset += page_size

    return task_instances


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
