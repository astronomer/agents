"""Asset/dataset tools - list assets, list events, get upstream events."""

import json

from astro_airflow_mcp.constants import DEFAULT_LIMIT, DEFAULT_OFFSET
from astro_airflow_mcp.server import (
    _get_adapter,
    _wrap_list_response,
    mcp,
)


def _list_assets_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
) -> str:
    """Internal implementation for listing assets from Airflow.

    Args:
        limit: Maximum number of assets to return (default: 100)
        offset: Offset for pagination (default: 0)

    Returns:
        JSON string containing the list of assets with their metadata
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_assets(limit=limit, offset=offset)

        if "assets" in data:
            return _wrap_list_response(data["assets"], "assets", data)
        return f"No assets found. Response: {data}"
    except Exception as e:
        return str(e)


def _list_asset_events_impl(
    limit: int = DEFAULT_LIMIT,
    offset: int = DEFAULT_OFFSET,
    source_dag_id: str | None = None,
    source_run_id: str | None = None,
    source_task_id: str | None = None,
) -> str:
    """Internal implementation for listing asset events from Airflow.

    Args:
        limit: Maximum number of events to return (default: 100)
        offset: Offset for pagination (default: 0)
        source_dag_id: Filter by DAG that produced the event
        source_run_id: Filter by DAG run that produced the event
        source_task_id: Filter by task that produced the event

    Returns:
        JSON string containing the list of asset events
    """
    try:
        adapter = _get_adapter()
        data = adapter.list_asset_events(
            limit=limit,
            offset=offset,
            source_dag_id=source_dag_id,
            source_run_id=source_run_id,
            source_task_id=source_task_id,
        )

        if "asset_events" in data:
            return _wrap_list_response(data["asset_events"], "asset_events", data)
        return f"No asset events found. Response: {data}"
    except Exception as e:
        return str(e)


def _get_upstream_asset_events_impl(
    dag_id: str,
    dag_run_id: str,
) -> str:
    """Internal implementation for getting upstream asset events for a DAG run.

    Args:
        dag_id: The DAG ID
        dag_run_id: The DAG run ID

    Returns:
        JSON string containing the asset events that triggered this run
    """
    try:
        adapter = _get_adapter()
        data = adapter.get_dag_run_upstream_asset_events(dag_id, dag_run_id)

        if "asset_events" in data:
            return json.dumps(
                {
                    "dag_id": dag_id,
                    "dag_run_id": dag_run_id,
                    "triggered_by_events": data["asset_events"],
                    "event_count": len(data["asset_events"]),
                },
                indent=2,
            )
        return json.dumps(data, indent=2)
    except Exception as e:
        return str(e)


@mcp.tool()
def list_assets() -> str:
    """Get data assets and datasets tracked by Airflow (data lineage).

    Use this tool when the user asks about:
    - "What datasets exist?" or "List all assets"
    - "What data does this DAG produce/consume?"
    - "Show me data dependencies" or "What's the data lineage?"
    - "Which DAGs use dataset X?"
    - Data freshness or update events

    Assets represent datasets or files that DAGs produce or consume.
    This enables data-driven scheduling where DAGs wait for data availability.

    Returns asset information including:
    - uri: Unique identifier for the asset (e.g., s3://bucket/path)
    - id: Internal asset ID
    - created_at: When this asset was first registered
    - updated_at: When this asset was last updated
    - consuming_dags: Which DAGs depend on this asset
    - producing_tasks: Which tasks create/update this asset

    Returns:
        JSON with list of all assets and their producing/consuming relationships
    """
    return _list_assets_impl()


@mcp.tool()
def list_asset_events(
    source_dag_id: str | None = None,
    source_run_id: str | None = None,
    source_task_id: str | None = None,
    limit: int = 100,
) -> str:
    """List asset/dataset events with optional filtering.

    Use this tool when the user asks about:
    - "What asset events were produced by DAG X?"
    - "Show me dataset events from run Y"
    - "Debug why downstream DAG wasn't triggered"
    - "What assets did this pipeline produce?"
    - "List recent asset update events"

    Asset events are produced when a task updates an asset/dataset.
    These events can trigger downstream DAGs that depend on those assets
    (data-aware scheduling).

    Returns event information including:
    - uri: The asset that was updated
    - source_dag_id: The DAG that produced this event
    - source_run_id: The DAG run that produced this event
    - source_task_id: The task that produced this event
    - timestamp: When the event was created

    Args:
        source_dag_id: Filter events by the DAG that produced them
        source_run_id: Filter events by the DAG run that produced them
        source_task_id: Filter events by the task that produced them
        limit: Maximum number of events to return (default: 100)

    Returns:
        JSON with list of asset events
    """
    return _list_asset_events_impl(
        limit=limit,
        source_dag_id=source_dag_id,
        source_run_id=source_run_id,
        source_task_id=source_task_id,
    )


@mcp.tool()
def get_upstream_asset_events(
    dag_id: str,
    dag_run_id: str,
) -> str:
    """Get asset events that triggered a specific DAG run.

    Use this tool when the user asks about:
    - "What triggered this DAG run?"
    - "Which asset events caused this run to start?"
    - "Why did DAG X start running?"
    - "Show me the upstream triggers for this run"
    - "What data changes triggered this pipeline run?"

    This is useful for understanding causation in data-aware scheduling.
    When a DAG is scheduled based on asset updates, this tool shows which
    specific asset events triggered the run.

    Returns information including:
    - dag_id: The DAG that was triggered
    - dag_run_id: The specific run
    - triggered_by_events: List of asset events that caused this run
    - event_count: Number of triggering events

    Each event includes:
    - asset_uri or dataset_uri: The asset that was updated
    - source_dag_id: The DAG that produced the event
    - source_run_id: The run that produced the event
    - timestamp: When the event occurred

    Args:
        dag_id: The ID of the DAG
        dag_run_id: The ID of the DAG run (e.g., "scheduled__2024-01-01T00:00:00+00:00")

    Returns:
        JSON with the asset events that triggered this DAG run
    """
    return _get_upstream_asset_events_impl(dag_id, dag_run_id)
