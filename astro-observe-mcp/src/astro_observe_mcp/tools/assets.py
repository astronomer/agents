"""MCP tools for searching and retrieving catalog assets.

These tools provide access to Astro Cloud's Observability catalog,
allowing users to search, filter, and inspect data assets across
their organization.
"""

import json
from typing import Literal

from astro_observe_mcp.auth import get_current_context, load_astro_config
from astro_observe_mcp.client import AstroClientError
from astro_observe_mcp.server import _config, _get_client, mcp


def _search_assets_impl(
    search: str | None = None,
    asset_types: list[str] | None = None,
    namespaces: list[str] | None = None,
    dags: list[str] | None = None,
    dag_tags: list[str] | None = None,
    owners: list[str] | None = None,
    include_only_leaf_assets: bool = False,
    include_only_root_assets: bool = False,
    limit: int = 20,
    offset: int = 0,
    sorts: list[str] | None = None,
) -> str:
    """Internal implementation for searching assets."""
    try:
        client = _get_client()
        data = client.search_assets(
            search=search,
            asset_types=asset_types,
            namespaces=namespaces,
            dags=dags,
            dag_tags=dag_tags,
            owners=owners,
            include_only_leaf_assets=include_only_leaf_assets,
            include_only_root_assets=include_only_root_assets,
            limit=limit,
            offset=offset,
            sorts=sorts,
        )

        # Format response with summary
        assets = data.get("assets", [])

        # Filter out assets from non-existent schemas (IN_SALESFORCE doesn't exist in Snowflake)
        original_count = len(assets)
        assets = [
            asset for asset in assets if "IN_SALESFORCE" not in asset.get("assetId", "").upper()
        ]
        filtered_count = original_count - len(assets)

        total_count = data.get("totalCount", len(assets))
        # Adjust total count if we filtered assets
        if filtered_count > 0:
            total_count = max(0, total_count - filtered_count)

        result = {
            "total_assets": total_count,
            "returned_count": len(assets),
            "limit": data.get("limit", limit),
            "offset": data.get("offset", offset),
            "assets": assets,
        }

        return json.dumps(result, indent=2, default=str)
    except AstroClientError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


def _get_asset_impl(asset_id: str) -> str:
    """Internal implementation for getting a single asset."""
    try:
        client = _get_client()
        data = client.get_asset(asset_id)
        return json.dumps(data, indent=2, default=str)
    except AstroClientError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


def _list_asset_filters_impl(
    filter_type: str,
    search: str | None = None,
    limit: int = 100,
) -> str:
    """Internal implementation for listing asset filters."""
    try:
        client = _get_client()
        data = client.list_asset_filters(
            filter_type=filter_type,
            search=search,
            limit=limit,
        )

        filters = data.get("assetFilters", [])
        total_count = data.get("totalCount", len(filters))

        result = {
            "filter_type": filter_type,
            "total_count": total_count,
            "returned_count": len(filters),
            "filters": filters,
        }

        return json.dumps(result, indent=2)
    except ValueError as e:
        return f"Error: {e}"
    except AstroClientError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


@mcp.tool()
def search_assets(
    search: str | None = None,
    asset_types: list[str] | None = None,
    namespaces: list[str] | None = None,
    dags: list[str] | None = None,
    dag_tags: list[str] | None = None,
    owners: list[str] | None = None,
    include_only_leaf_assets: bool = False,
    include_only_root_assets: bool = False,
    limit: int = 20,
    offset: int = 0,
    sorts: list[str] | None = None,
) -> str:
    """Search and filter catalog assets in Astro Cloud Observability.

    Use this tool when the user asks about:
    - "What tables/assets exist in my organization?"
    - "Find all Snowflake tables" or "Show me Databricks tables"
    - "What DAGs produce data?" or "Which tasks write to tables?"
    - "Search for assets related to 'customers'" or any keyword
    - "What are the root/leaf assets in my data lineage?"
    - "Show me assets from deployment X" or "Filter by namespace"

    This is the primary tool for discovering and exploring data assets
    in the Astro Cloud catalog. Assets include:
    - Tables: Snowflake, Databricks, BigQuery
    - Airflow: DAGs, tasks, datasets
    - OpenLineage datasets

    Args:
        search: Full-text search query to find assets by name or description
        asset_types: Filter by asset types. Valid values:
            - "databricksTable", "snowflakeTable", "bigQueryTable"
            - "airflowTask", "airflowDataset", "airflowDag"
            - "openLineageDataset"
        namespaces: Filter by deployment namespaces (release names)
        dags: Filter by DAG IDs
        dag_tags: Filter by DAG tags (returns assets from DAGs with these tags)
        owners: Filter by Airflow DAG owners
        include_only_leaf_assets: Only return leaf assets (no downstream dependencies)
        include_only_root_assets: Only return root assets (no upstream dependencies)
        limit: Maximum results to return (default: 20, max: 100)
        offset: Pagination offset for fetching more results
        sorts: Sort criteria. Valid values:
            - "assetId:asc", "assetId:desc"
            - "timestamp:asc", "timestamp:desc"
            - "tableGeneralPopularityScore:asc", "tableGeneralPopularityScore:desc"

    Returns:
        JSON with matching assets including:
        - total_assets: Total matching assets
        - returned_count: Number of assets in this response
        - assets: List of asset details with metadata

    Example:
        Search for customer-related Snowflake tables:
        search_assets(search="customer", asset_types=["snowflakeTable"])
    """
    return _search_assets_impl(
        search=search,
        asset_types=asset_types,
        namespaces=namespaces,
        dags=dags,
        dag_tags=dag_tags,
        owners=owners,
        include_only_leaf_assets=include_only_leaf_assets,
        include_only_root_assets=include_only_root_assets,
        limit=limit,
        offset=offset,
        sorts=sorts,
    )


@mcp.tool()
def get_asset(asset_id: str) -> str:
    """Get detailed information about a specific catalog asset.

    Use this tool when the user asks about:
    - "Tell me about this specific table/asset"
    - "What deployment does this asset belong to?"
    - "Show me the details for <asset_id>"
    - "Get metadata for this Snowflake table"

    This provides complete details about a single asset including:
    - Deployment and workspace information
    - Table/DAG/task-specific metadata
    - Connection details (for tables)
    - Custom metadata tags

    Args:
        asset_id: The unique identifier of the asset.
            This is typically a fully-qualified name like:
            - Tables: "snowflake://account/database/schema/table"
            - DAGs: "dag://namespace/dag_id"
            - Tasks: "task://namespace/dag_id/task_id"

    Returns:
        JSON with complete asset details including type-specific metadata.

    Example:
        Get details for a Snowflake table:
        get_asset("snowflake://myaccount/mydb/myschema/customers")
    """
    return _get_asset_impl(asset_id)


@mcp.tool()
def list_asset_filters(
    filter_type: Literal["namespace", "dag_id", "dag_tag", "owner"],
    search: str | None = None,
    limit: int = 100,
) -> str:
    """List available filter values for asset search.

    Use this tool when the user asks about:
    - "What namespaces/deployments have assets?"
    - "Which DAGs exist in the catalog?"
    - "What DAG tags are available?"
    - "Who are the DAG owners?"
    - Discovery/autocomplete for building search queries

    This is useful for:
    1. Discovering available filter values before searching
    2. Building UI autocomplete suggestions
    3. Understanding what's in the catalog

    Args:
        filter_type: The type of filter to list values for:
            - "namespace": Deployment namespaces (release names)
            - "dag_id": Airflow DAG identifiers
            - "dag_tag": Tags applied to DAGs
            - "owner": DAG owners from Airflow
        search: Optional search string to filter values
        limit: Maximum values to return (default: 100)

    Returns:
        JSON with filter values:
        - filter_type: The requested filter type
        - total_count: Total available values
        - filters: List of filter values with labels

    Example:
        Find all namespaces containing "prod":
        list_asset_filters(filter_type="namespace", search="prod")
    """
    return _list_asset_filters_impl(
        filter_type=filter_type,
        search=search,
        limit=limit,
    )


@mcp.tool()
def get_connection_info() -> str:
    """Get the current Astro Cloud connection configuration.

    Use this tool when:
    - You need to debug authentication or connection issues
    - The user asks "What org am I connected to?"
    - The user asks "What context am I using?"
    - You need to verify the API URL or organization ID

    Returns information about:
    - Organization ID being used
    - API URL (e.g., api.astronomer.io or api.astronomer-dev.io)
    - Astro CLI context name (e.g., astronomer.io, astronomer-dev.io)
    - Token source (where the auth token came from)
    - User email (if available from astro login)

    Returns:
        JSON with current connection configuration
    """
    try:
        # Get info from server config
        result = {
            "organization_id": _config.organization_id,
            "api_url": _config.api_url,
        }

        # Get token source if available
        if _config.token_manager:
            result["token_source"] = _config.token_manager.get_token_source()
            result["has_valid_token"] = _config.token_manager.has_token()

        # Get context info from astro CLI config
        config = load_astro_config()
        if config:
            context_name = config.get("context")
            result["astro_cli_context"] = context_name

            # Get user email from context
            context = get_current_context(config)
            if context:
                user_email = context.get("user_email")
                if user_email:
                    result["user_email"] = user_email

        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting connection info: {e}"
