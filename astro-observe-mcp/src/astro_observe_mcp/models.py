"""Pydantic models for Astro Observability API responses.

These models represent the catalog assets returned by the Astro Cloud
Observability API, including tables, DAGs, tasks, and datasets.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Asset types supported by the API
AssetType = Literal[
    "databricksTable",
    "snowflakeTable",
    "bigQueryTable",
    "airflowTask",
    "airflowDataset",
    "openLineageDataset",
    "airflowDag",
]

# Filter types for asset filter discovery
FilterType = Literal["namespace", "dag_id", "dag_tag", "owner"]

# Sort fields
SortField = Literal[
    "assetId:asc",
    "assetId:desc",
    "timestamp:asc",
    "timestamp:desc",
    "tableGeneralPopularityScore:asc",
    "tableGeneralPopularityScore:desc",
]


class DeploymentDetails(BaseModel):
    """Deployment information for an asset."""

    deployment_id: str | None = Field(None, alias="deploymentId")
    deployment_name: str | None = Field(None, alias="deploymentName")
    deployment_url: str | None = Field(None, alias="deploymentUrl")
    airflow_url: str | None = Field(None, alias="airflowUrl")

    model_config = {"populate_by_name": True}


class WorkspaceDetails(BaseModel):
    """Workspace information for an asset."""

    workspace_id: str | None = Field(None, alias="workspaceId")
    workspace_name: str | None = Field(None, alias="workspaceName")
    workspace_url: str | None = Field(None, alias="workspaceUrl")

    model_config = {"populate_by_name": True}


class CollapsedAsset(BaseModel):
    """A collapsed asset in lineage (for circular dependencies)."""

    asset_id: str = Field(alias="assetId")
    asset_uid: str = Field(alias="assetUid")
    type: str

    model_config = {"populate_by_name": True}


class LineageDetails(BaseModel):
    """Lineage metadata for an asset."""

    circular_collapsed_assets: list[CollapsedAsset] = Field(
        default_factory=list, alias="circularCollapsedAssets"
    )
    should_auto_expand: bool = Field(False, alias="shouldAutoExpand")

    model_config = {"populate_by_name": True}


class TableMetadata(BaseModel):
    """Metadata specific to table assets (Snowflake, Databricks, BigQuery)."""

    connection_id: str | None = Field(None, alias="connectionId")
    connection_name: str | None = Field(None, alias="connectionName")
    connection_acct: str | None = Field(None, alias="connectionAcct")
    connection_type: str | None = Field(None, alias="connectionType")
    database: str | None = None
    schema_name: str | None = Field(None, alias="schema")
    table_name: str | None = Field(None, alias="tableName")

    model_config = {"populate_by_name": True}


class DagMetadata(BaseModel):
    """Metadata specific to DAG assets."""

    dag_id: str | None = Field(None, alias="dagId")
    dag_url: str | None = Field(None, alias="dagUrl")
    schedule: str | None = None
    owners: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    is_paused: bool | None = Field(None, alias="isPaused")

    model_config = {"populate_by_name": True}


class TaskMetadata(BaseModel):
    """Metadata specific to task assets."""

    dag_id: str | None = Field(None, alias="dagId")
    task_id: str | None = Field(None, alias="taskId")
    task_url: str | None = Field(None, alias="taskUrl")
    operator: str | None = None

    model_config = {"populate_by_name": True}


class DatasetMetadata(BaseModel):
    """Metadata specific to dataset/asset assets."""

    uri: str | None = None
    producing_tasks: list[str] = Field(default_factory=list, alias="producingTasks")
    consuming_dags: list[str] = Field(default_factory=list, alias="consumingDags")

    model_config = {"populate_by_name": True}


class CustomMetadata(BaseModel):
    """Custom metadata attached to an asset."""

    key: str
    value: str
    url: str | None = None
    display_text: str | None = Field(None, alias="displayText")

    model_config = {"populate_by_name": True}


class CommonCatalogAssetResponse(BaseModel):
    """Common fields for all catalog asset types."""

    id: str
    name: str
    namespace: str
    description: str | None = None
    updated_at: datetime | None = Field(None, alias="updatedAt")
    updated_by: str | None = Field(None, alias="updatedBy")
    deployment_details: DeploymentDetails = Field(
        default_factory=DeploymentDetails, alias="deploymentDetails"
    )
    workspace_details: WorkspaceDetails = Field(
        default_factory=WorkspaceDetails, alias="workspaceDetails"
    )
    lineage_details: LineageDetails = Field(default_factory=LineageDetails, alias="lineageDetails")

    model_config = {"populate_by_name": True}


class TableCatalogAssetResponse(CommonCatalogAssetResponse):
    """Response for table assets (Snowflake, Databricks, BigQuery)."""

    type: Literal["databricksTable", "snowflakeTable", "bigQueryTable"]
    metadata: TableMetadata = Field(default_factory=TableMetadata)
    astro_custom_metadata: list[CustomMetadata] = Field(
        default_factory=list, alias="astroCustomMetadata"
    )


class DagCatalogAssetResponse(CommonCatalogAssetResponse):
    """Response for DAG assets."""

    type: Literal["airflowDag"] = "airflowDag"
    metadata: DagMetadata = Field(default_factory=DagMetadata)


class TaskCatalogAssetResponse(CommonCatalogAssetResponse):
    """Response for task assets."""

    type: Literal["airflowTask"] = "airflowTask"
    metadata: TaskMetadata = Field(default_factory=TaskMetadata)


class DatasetCatalogAssetResponse(CommonCatalogAssetResponse):
    """Response for dataset assets (airflowDataset, openLineageDataset)."""

    type: Literal["airflowDataset", "openLineageDataset"]
    metadata: DatasetMetadata = Field(default_factory=DatasetMetadata)


# Union type for any catalog asset
CatalogAssetResponse = (
    TableCatalogAssetResponse
    | DagCatalogAssetResponse
    | TaskCatalogAssetResponse
    | DatasetCatalogAssetResponse
)


class CatalogAssetsResponse(BaseModel):
    """Response for listing catalog assets."""

    assets: list[dict[str, Any]] = Field(default_factory=list)
    total_count: int = Field(0, alias="totalCount")
    limit: int = 20
    offset: int = 0

    model_config = {"populate_by_name": True}


class AssetFilter(BaseModel):
    """A single asset filter value."""

    value: str
    label: str | None = None


class AssetFiltersResponse(BaseModel):
    """Response for listing asset filter values."""

    asset_filters: list[AssetFilter] = Field(default_factory=list, alias="assetFilters")
    total_count: int = Field(0, alias="totalCount")

    model_config = {"populate_by_name": True}
