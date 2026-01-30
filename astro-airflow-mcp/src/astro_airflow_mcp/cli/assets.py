"""Asset/dataset management CLI commands."""

from typing import Annotated

import typer

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json, wrap_list_response

app = typer.Typer(help="Asset/dataset management commands", no_args_is_help=True)


@app.command("list")
def list_assets(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of assets to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
) -> None:
    """List data assets/datasets tracked by Airflow.

    Returns asset information including URI, producing tasks,
    and consuming DAGs for data lineage.
    """
    try:
        adapter = get_adapter()
        data = adapter.list_assets(limit=limit, offset=offset)

        if "assets" in data:
            result = wrap_list_response(data["assets"], "assets", data)
            output_json(result)
        else:
            output_json({"message": "No assets found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("events")
def list_asset_events(
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of events to return"),
    ] = 100,
    offset: Annotated[
        int,
        typer.Option("--offset", "-o", help="Offset for pagination"),
    ] = 0,
    dag_id: Annotated[
        str | None,
        typer.Option("--dag-id", "-d", help="Filter by DAG that produced the event"),
    ] = None,
    run_id: Annotated[
        str | None,
        typer.Option("--run-id", "-r", help="Filter by DAG run that produced the event"),
    ] = None,
    task_id: Annotated[
        str | None,
        typer.Option("--task-id", "-t", help="Filter by task that produced the event"),
    ] = None,
) -> None:
    """List asset/dataset events.

    Asset events are produced when tasks update assets/datasets.
    These events can trigger downstream DAGs (data-aware scheduling).

    Examples:
        af assets events
        af assets events --dag-id my_dag
        af assets events --dag-id my_dag --run-id run_123
    """
    try:
        adapter = get_adapter()
        data = adapter.list_asset_events(
            limit=limit,
            offset=offset,
            source_dag_id=dag_id,
            source_run_id=run_id,
            source_task_id=task_id,
        )

        if "asset_events" in data:
            result = wrap_list_response(data["asset_events"], "asset_events", data)
            output_json(result)
        else:
            output_json({"message": "No asset events found", "response": data})
    except Exception as e:
        output_error(str(e))


@app.command("triggers")
def get_upstream_asset_events(
    dag_id: Annotated[str, typer.Argument(help="The DAG ID")],
    dag_run_id: Annotated[str, typer.Argument(help="The DAG run ID")],
) -> None:
    """Get asset events that triggered a specific DAG run.

    Shows which asset/dataset updates caused a DAG run to start.
    Useful for understanding data-aware scheduling causation.

    Examples:
        af assets triggers my_dag scheduled__2024-01-01T00:00:00+00:00
    """
    try:
        adapter = get_adapter()
        data = adapter.get_dag_run_upstream_asset_events(dag_id, dag_run_id)

        if "asset_events" in data:
            result = {
                "dag_id": dag_id,
                "dag_run_id": dag_run_id,
                "triggered_by_events": data["asset_events"],
                "event_count": len(data["asset_events"]),
            }
            output_json(result)
        else:
            output_json(data)
    except Exception as e:
        output_error(str(e))
