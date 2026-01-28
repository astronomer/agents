"""Task management CLI commands."""

from typing import Annotated

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response

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
