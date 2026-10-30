"""Shared, fail-closed system health checks for MCP and CLI consumers."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from astro_airflow_mcp.tool_errors import error_payload

if TYPE_CHECKING:
    from astro_airflow_mcp.adapters import AirflowAdapter


def _get_complete_dag_stats(adapter: "AirflowAdapter") -> dict[str, Any]:
    dag_ids: list[str] = []
    offset = 0
    while True:
        response = adapter.list_dags(limit=100, offset=offset)
        if response.get("error") or response.get("available") is False:
            raise ValueError(f"DAG discovery failed: {response}")
        dags = response["dags"]
        dag_ids.extend(dag["dag_id"] for dag in dags)
        offset += len(dags)
        if offset >= response["total_entries"]:
            break
        if not dags:
            raise ValueError("DAG listing ended before all DAGs were returned")

    if not dag_ids:
        return {"dags": [], "total_entries": 0}
    stats = adapter.get_dag_stats(dag_ids=dag_ids)
    if stats.get("error") or stats.get("errors") or stats.get("available") is False:
        raise ValueError(f"DAG statistics unavailable or incomplete: {stats}")
    missing = set(dag_ids) - {dag["dag_id"] for dag in stats["dags"]}
    if missing:
        raise ValueError(f"DAG statistics missing for: {', '.join(sorted(missing))}")
    return stats


def collect_system_health(
    adapter_factory: Callable[[], "AirflowAdapter"],
) -> dict[str, Any]:
    """Collect health without interpreting failed or incomplete reads as all-clear."""
    try:
        adapter = adapter_factory()
    except Exception as error:
        return {
            "overall_status": "unknown",
            "status_reason": "Could not initialize the Airflow adapter",
            "error": error_payload(error),
        }

    result: dict[str, Any] = {}
    checks = {
        "version": adapter.get_version,
        "import_errors": lambda: adapter.list_import_errors(limit=100),
        "dag_warnings": lambda: adapter.list_dag_warnings(limit=100),
        "dag_stats": lambda: _get_complete_dag_stats(adapter),
    }
    incomplete = []
    for name, check in checks.items():
        try:
            data = check()
            if data.get("error") or data.get("errors") or data.get("available") is False:
                raise ValueError(f"{name} check failed: {data}")
            if name in {"import_errors", "dag_warnings"}:
                items = data[name]
                if not isinstance(items, list):
                    raise ValueError(f"{name} response must contain a list")
                data = {
                    "count": max(len(items), data.get("total_entries", len(items))),
                    "errors" if name == "import_errors" else "warnings": items,
                }
            elif name == "version" and not data.get("version"):
                raise ValueError("Airflow version was not returned")
            result[name] = data
        except Exception as error:
            result[name] = error_payload(error)
            if name == "dag_stats":
                result[name]["available"] = False
            incomplete.append(name)

    import_error_count = result["import_errors"].get("count", 0)
    warning_count = result["dag_warnings"].get("count", 0)
    if import_error_count:
        status, reason = "unhealthy", f"{import_error_count} import error(s) detected"
    elif incomplete:
        status, reason = "unknown", "Incomplete health checks: " + ", ".join(incomplete)
    elif warning_count:
        status, reason = "warning", f"{warning_count} DAG warning(s) detected"
    else:
        status, reason = "healthy", "No import errors or warnings"
    if incomplete and status == "unhealthy":
        reason += "; incomplete health checks: " + ", ".join(incomplete)
    result.update(overall_status=status, status_reason=reason)
    return result
