"""DAG management CLI commands."""

from typing import Annotated, Any

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response

app = typer.Typer(help="DAG management commands", no_args_is_help=True)


@app.command("list")
def list_dags(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of DAGs to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List all DAGs in Airflow.

    Returns DAG metadata including dag_id, is_paused, schedule_interval,
    description, tags, and owners.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_dags(limit=limit, offset=offset)

        if "dags" in data:
            result = wrap_list_response(data["dags"], "dags", data)
            output_json(result)
        else:
            output_json({"message": "No DAGs found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("get")
def get_dag(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to get details for")],
) -> None:
    """Get detailed information about a specific DAG.

    Returns complete DAG information including schedule, owners, tags,
    file location, and configuration.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_dag(dag_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("source")
def get_dag_source(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to get source code for")],
) -> None:
    """Get the source code for a specific DAG.

    Returns the Python source code of the DAG file.
    """
    try:
        adapter = get_adapter()
        data = adapter.get_dag_source(dag_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("stats")
def get_dag_stats(
    dag_ids: Annotated[
        list[str] | None,
        typer.Option("--dag-id", "-d", help="DAG IDs to get stats for (can specify multiple)"),
    ] = None,
) -> None:
    """Get statistics about DAG runs by state.

    Returns counts of DAG runs grouped by state (success, failed, running, etc.).
    """
    try:
        adapter = get_adapter()
        data = adapter.get_dag_stats(dag_ids=dag_ids)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("pause")
def pause_dag(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to pause")],
) -> None:
    """Pause a DAG to prevent new scheduled runs.

    When paused, no new scheduled runs will be created, but currently
    running tasks will complete. Manual triggers are still possible.
    """
    try:
        adapter = get_adapter()
        data = adapter.pause_dag(dag_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("unpause")
def unpause_dag(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to unpause")],
) -> None:
    """Unpause a DAG to allow scheduled runs to resume.

    The scheduler will create new runs based on the DAG's schedule_interval.
    """
    try:
        adapter = get_adapter()
        data = adapter.unpause_dag(dag_id)
        output_json(data)
    except Exception as e:
        output_error(str(e))


@app.command("explore")
def explore_dag(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID to explore")],
) -> None:
    """Comprehensive investigation of a DAG.

    Returns all relevant information about a DAG in one call:
    - DAG metadata (schedule, owners, tags, paused status)
    - All tasks with their operators and dependencies
    - DAG source code
    """
    result: dict[str, Any] = {"dag_id": dag_id}
    adapter = get_adapter()

    # Get DAG details
    try:
        result["dag_info"] = adapter.get_dag(dag_id)
    except Exception as e:
        result["dag_info"] = {"error": str(e)}

    # Get tasks
    try:
        tasks_data = adapter.list_tasks(dag_id)
        result["tasks"] = tasks_data.get("tasks", [])
    except Exception as e:
        result["tasks"] = {"error": str(e)}

    # Get DAG source
    try:
        result["source"] = adapter.get_dag_source(dag_id)
    except Exception as e:
        result["source"] = {"error": str(e)}

    output_json(result)


@app.command("warnings")
def list_dag_warnings(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of warnings to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List warnings and issues detected in DAG definitions.

    Returns warnings about DAG configuration issues, deprecations, etc.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_dag_warnings(limit=limit, offset=offset)

        if "dag_warnings" in data:
            result = wrap_list_response(data["dag_warnings"], "dag_warnings", data)
            output_json(result)
        else:
            output_json({"message": "No DAG warnings found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("errors")
def list_import_errors(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of errors to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List import errors from DAG files that failed to parse.

    Import errors occur when DAG files have problems that prevent Airflow
    from parsing them (syntax errors, missing imports, etc.).
    """
    try:
        adapter = get_adapter()
        data = adapter.list_import_errors(limit=limit, offset=offset)

        if "import_errors" in data:
            result = wrap_list_response(data["import_errors"], "import_errors", data)
            output_json(result)
        else:
            output_json({"message": "No import errors found", "response": data})
    except Exception as e:
        output_error(str(e))
