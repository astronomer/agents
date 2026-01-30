"""Task management CLI commands."""

from typing import Annotated

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response


# Callback to parse comma-separated task IDs
def parse_task_ids(value: str) -> list[str]:
    """Parse comma-separated task IDs into a list."""
    return [t.strip() for t in value.split(",") if t.strip()]


app = typer.Typer(help="Task management commands", no_args_is_help=True)


@app.command("list")
def list_tasks(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to list tasks for")],
) -> None:
    """List all tasks defined in a specific DAG.

    Returns information about all tasks including task_id, operator_name,
    dependencies (upstream/downstream task IDs), and configuration.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_tasks(dag_id)

        if "tasks" in data:
            result = wrap_list_response(data["tasks"], "tasks", data)
            output_json(result)
        else:
            output_json({"message": "No tasks found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("get")
def get_task(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    task_id: Annotated[str, typer.Argument(help="The task ID")],
) -> None:
    """Get detailed information about a specific task definition.

    Returns task configuration including operator type, trigger_rule,
    retries, dependencies, pool assignment, and more.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_task(dag_id, task_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("instance")
def get_task_instance(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
    task_id: Annotated[str, typer.Argument(help="The task ID")],
) -> None:
    """Get information about a specific task instance execution.

    Returns execution details including state, start/end times,
    duration, try_number, and operator.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_task_instance(dag_id, dag_run_id, task_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("logs")
def get_task_logs(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
    task_id: Annotated[str, typer.Argument(help="The task ID")],
    try_number: Annotated[
        int,
        typer.Option("--try", "-t", help="Task try/attempt number (1-indexed)"),
    ] = 1,
    map_index: Annotated[
        int,
        typer.Option("--map-index", "-m", help="Map index for mapped tasks (-1 for unmapped)"),
    ] = -1,
) -> None:
    """Get logs for a specific task instance execution.

    Returns the actual log output from the task execution, including
    stdout/stderr, error messages, and timing information.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_task_logs(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_id=task_id,
            try_number=try_number,
            map_index=map_index,
            full_content=True,
        )
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("clear")
def clear_task_instances(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
    task_ids: Annotated[
        str,
        typer.Argument(help="Comma-separated list of task IDs to clear"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", "-d/-D", help="Preview what would be cleared"),
    ] = True,
    only_failed: Annotated[
        bool,
        typer.Option("--only-failed/--all", "-f/-a", help="Only clear failed task instances"),
    ] = False,
    include_downstream: Annotated[
        bool,
        typer.Option("--downstream/--no-downstream", help="Also clear downstream tasks"),
    ] = False,
) -> None:
    """Clear task instances to allow re-running them.

    By default, runs in dry-run mode showing what would be cleared.
    Use --no-dry-run or -D to actually clear the tasks.

    Examples:
        af tasks clear my_dag run_123 task1,task2 --dry-run
        af tasks clear my_dag run_123 task1 -D --only-failed
        af tasks clear my_dag run_123 task1 -D --downstream
    """
    try:
        adapter = get_adapter()
        task_id_list = parse_task_ids(task_ids)

        if not task_id_list:
            output_error("No task IDs provided")
            return

        data = adapter.clear_task_instances(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_ids=task_id_list,
            dry_run=dry_run,
            only_failed=only_failed,
            include_downstream=include_downstream,
        )

        # Add context to the output
        result = {
            "dry_run": dry_run,
            "dag_id": dag_id,
            "dag_run_id": dag_run_id,
            "requested_task_ids": task_id_list,
            **data,
        }
        output_json(result)
    except Exception as e:
        output_error(str(e))
