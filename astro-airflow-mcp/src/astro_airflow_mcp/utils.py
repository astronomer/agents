"""Shared utility functions for CLI and MCP server."""

from typing import Any

from astro_airflow_mcp.constants import FAILED_TASK_STATES


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
