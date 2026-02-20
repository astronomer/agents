"""DAG run management CLI commands."""

import json
import time
from typing import Annotated, Any

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response
from astro_airflow_mcp.constants import TERMINAL_DAG_RUN_STATES
from astro_airflow_mcp.utils import extract_failed_tasks

app = typer.Typer(help="DAG run management commands", no_args_is_help=True)


@app.command("list")
def list_dag_runs(
    dag_id: Annotated[
        str | None,
        typer.Option("--dag-id", "-d", help="Filter by DAG ID"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of runs to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
    order_by: Annotated[
        str | None,
        typer.Option("--order-by", help="Sort field (prefix - for descending, e.g., -start_date)"),
    ] = None,
    state: Annotated[
        str | None,
        typer.Option("--state", "-s", help="Filter by state: running, success, failed, queued"),
    ] = None,
    start_date_gte: Annotated[
        str | None,
        typer.Option(
            "--start-date-gte", help="Runs with start_date >= value (e.g., 2024-01-01T00:00:00Z)"
        ),
    ] = None,
    start_date_lte: Annotated[
        str | None,
        typer.Option(
            "--start-date-lte", help="Runs with start_date <= value (e.g., 2024-01-01T00:00:00Z)"
        ),
    ] = None,
) -> None:
    """List DAG runs (workflow executions).

    Returns execution metadata including dag_run_id, state, execution_date,
    start_date, end_date, and run_type.
    """
    try:
        kwargs: dict[str, Any] = {}
        if order_by:
            kwargs["order_by"] = order_by
        if state:
            kwargs["state"] = state
        if start_date_gte:
            kwargs["start_date_gte"] = start_date_gte
        if start_date_lte:
            kwargs["start_date_lte"] = start_date_lte

        adapter = get_adapter()
        data = adapter.list_dag_runs(dag_id=dag_id, limit=limit, offset=offset, **kwargs)

        if "dag_runs" in data:
            result = wrap_list_response(data["dag_runs"], "dag_runs", data)
            output_json(result)
        else:
            output_json({"message": "No DAG runs found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("get")
def get_dag_run(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
) -> None:
    """Get detailed information about a specific DAG run.

    Returns state, start/end times, duration, run_type, and configuration.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_dag_run(dag_id, dag_run_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("trigger")
def trigger_dag(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to trigger")],
    conf: Annotated[
        str | None,
        typer.Option("--conf", "-c", help="Configuration JSON to pass to the DAG run"),
    ] = None,
) -> None:
    """Trigger a new DAG run.

    Creates a new DAG run that will be picked up by the scheduler.
    Optionally pass configuration parameters via --conf.
    """
    try:
        adapter = get_adapter()
        conf_dict = json.loads(conf) if conf else None
        data = adapter.trigger_dag_run(dag_id=dag_id, conf=conf_dict)
        output_json(data)
    except json.JSONDecodeError as e:
        output_error(f"Invalid JSON in --conf: {e}")
    except Exception as e:
        output_error(str(e))


@app.command("trigger-wait")
def trigger_dag_and_wait(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to trigger")],
    conf: Annotated[
        str | None,
        typer.Option("--conf", "-c", help="Configuration JSON to pass to the DAG run"),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Maximum time to wait in seconds"),
    ] = 3600.0,
    poll_interval: Annotated[
        float,
        typer.Option("--poll-interval", "-p", help="Seconds between status checks"),
    ] = 5.0,
) -> None:
    """Trigger a DAG run and wait for completion.

    This is a blocking operation that triggers the DAG and polls until
    it reaches a terminal state (success, failed, upstream_failed).
    """
    try:
        adapter = get_adapter()
        conf_dict = json.loads(conf) if conf else None

        # Step 1: Trigger the DAG
        trigger_data = adapter.trigger_dag_run(dag_id=dag_id, conf=conf_dict)
        dag_run_id = trigger_data.get("dag_run_id")

        if not dag_run_id:
            output_error(f"No dag_run_id in trigger response: {trigger_data}")
            return

        # Step 2: Poll for completion
        start_time = time.time()
        current_state = trigger_data.get("state", "queued")

        while True:
            elapsed = time.time() - start_time

            # Check timeout
            if elapsed >= timeout:
                result: dict[str, Any] = {
                    "dag_id": dag_id,
                    "dag_run_id": dag_run_id,
                    "state": current_state,
                    "timed_out": True,
                    "elapsed_seconds": round(elapsed, 2),
                    "message": f"Timed out after {timeout} seconds. DAG run is still {current_state}.",
                }
                output_json(result)
                return

            # Wait before polling
            time.sleep(poll_interval)

            # Get current status
            status_data = adapter.get_dag_run(dag_id=dag_id, dag_run_id=dag_run_id)
            current_state = status_data.get("state", current_state)

            # Check if we've reached a terminal state
            if current_state in TERMINAL_DAG_RUN_STATES:
                result = {
                    "dag_run": status_data,
                    "timed_out": False,
                    "elapsed_seconds": round(time.time() - start_time, 2),
                }

                # Fetch failed task details if not successful
                if current_state != "success":
                    failed_tasks = _get_failed_task_instances(adapter, dag_id, dag_run_id)
                    if failed_tasks:
                        result["failed_tasks"] = failed_tasks

                output_json(result)
                return

    except json.JSONDecodeError as e:
        output_error(f"Invalid JSON in --conf: {e}")
    except Exception as e:
        output_error(str(e))


def _get_failed_task_instances(
    adapter: Any,
    dag_id: str,
    dag_run_id: str,
) -> list[dict[str, Any]]:
    """Fetch task instances that failed in a DAG run."""
    try:
        data = adapter.get_task_instances(dag_id, dag_run_id)
        task_instances = data.get("task_instances", [])
        return extract_failed_tasks(task_instances)
    except Exception:
        return []


@app.command("delete")
def delete_dag_run(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID to delete")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Delete a specific DAG run.

    Permanently removes a DAG run and its associated metadata. This cannot be undone.
    """
    if not yes:
        typer.confirm(f"Delete DAG run '{dag_run_id}' for DAG '{dag_id}'?", abort=True)

    try:
        adapter = get_adapter()
        adapter.delete_dag_run(dag_id, dag_run_id)
        output_json({"message": f"DAG run '{dag_run_id}' deleted", "dag_id": dag_id})
    except Exception as e:
        output_error(str(e))


@app.command("clear")
def clear_dag_run(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID to clear")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be cleared without clearing"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Clear a DAG run to allow re-execution of all its tasks.

    Resets the DAG run and its task instances so they can be re-executed by
    the scheduler. Use --dry-run to preview what would be cleared.

    Note: The CLI clears immediately (with confirmation prompt) by default.
    The MCP tool defaults to dry_run=True for safety when called by AI agents.
    """
    try:
        adapter = get_adapter()

        if dry_run:
            data = adapter.clear_dag_run(dag_id, dag_run_id, dry_run=True)
            output_json({"dry_run": True, "dag_id": dag_id, "dag_run_id": dag_run_id, **data})
            return

        if not yes:
            typer.confirm(f"Clear DAG run '{dag_run_id}' for DAG '{dag_id}'?", abort=True)

        data = adapter.clear_dag_run(dag_id, dag_run_id, dry_run=False)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("diagnose")
def diagnose_dag_run(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
) -> None:
    """Diagnose issues with a specific DAG run.

    Returns run details, all task instances with their states,
    and highlights any failed tasks.
    """
    result: dict[str, Any] = {"dag_id": dag_id, "dag_run_id": dag_run_id}
    adapter = get_adapter()

    # Get DAG run details
    try:
        result["run_info"] = adapter.get_dag_run(dag_id, dag_run_id)
    except Exception as e:
        result["run_info"] = {"error": str(e)}
        output_json(result)
        return

    # Get task instances for this run
    try:
        tasks_data = adapter.get_task_instances(dag_id, dag_run_id)
        task_instances = tasks_data.get("task_instances", [])
        result["task_instances"] = task_instances

        # Summarize task states
        state_counts: dict[str, int] = {}
        failed_tasks = []
        for ti in task_instances:
            state = ti.get("state", "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
            if state in ("failed", "upstream_failed"):
                failed_tasks.append(
                    {
                        "task_id": ti.get("task_id"),
                        "state": state,
                        "start_date": ti.get("start_date"),
                        "end_date": ti.get("end_date"),
                        "try_number": ti.get("try_number"),
                    }
                )

        result["summary"] = {
            "total_tasks": len(task_instances),
            "state_counts": state_counts,
            "failed_tasks": failed_tasks,
        }
    except Exception as e:
        result["task_instances"] = {"error": str(e)}

    output_json(result)
