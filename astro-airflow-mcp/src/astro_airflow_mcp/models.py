"""Pydantic models for Airflow API responses.

These models serve as type references and documentation for the expected
API response structures. The adapters currently return raw dict[str, Any]
for flexibility, but these models document the expected fields and types.

They can be used for:
- Type hints and IDE autocompletion during development
- Documentation of API response structures
- Future validation if stricter typing is desired
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DAGInfo(BaseModel):
    """DAG information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    dag_id: str
    dag_display_name: str | None = None
    is_paused: bool = False
    is_active: bool = True
    is_subdag: bool = False
    fileloc: str | None = None
    file_token: str | None = None
    owners: list[str] = Field(default_factory=list)
    description: str | None = None
    schedule_interval: str | None = None
    timetable_summary: str | None = None
    timetable_description: str | None = None
    tags: list[dict[str, str]] = Field(default_factory=list)
    max_active_runs: int | None = None
    max_active_tasks: int | None = None
    has_task_concurrency_limits: bool = False
    has_import_errors: bool = False
    next_dagrun: datetime | None = None
    next_dagrun_create_after: datetime | None = None


class DAGRun(BaseModel):
    """DAG run information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    dag_run_id: str
    dag_id: str
    logical_date: datetime | None = None
    execution_date: datetime | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    state: str | None = None
    run_type: str | None = None
    queued_at: datetime | None = None
    external_trigger: bool = False
    conf: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class TaskInfo(BaseModel):
    """Task definition information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    task_display_name: str | None = None
    owner: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    trigger_rule: str | None = None
    depends_on_past: bool = False
    wait_for_downstream: bool = False
    retries: int | None = None
    retry_delay: float | None = None
    retry_exponential_backoff: bool = False
    execution_timeout: float | None = None
    operator_name: str | None = None
    pool: str | None = None
    pool_slots: int = 1
    queue: str | None = None
    priority_weight: int | None = None
    downstream_task_ids: list[str] = Field(default_factory=list)
    upstream_task_ids: list[str] = Field(default_factory=list)


class TaskInstance(BaseModel):
    """Task instance execution information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    dag_id: str
    dag_run_id: str | None = None
    run_id: str | None = None
    state: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    duration: float | None = None
    try_number: int | None = None
    max_tries: int | None = None
    operator: str | None = None
    pool: str | None = None
    pool_slots: int = 1
    queue: str | None = None
    priority_weight: int | None = None
    queued_when: datetime | None = None
    executor_config: str | None = None


class PoolInfo(BaseModel):
    """Pool information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    name: str
    slots: int = 128
    occupied_slots: int = 0
    running_slots: int = 0
    queued_slots: int = 0
    open_slots: int = 128
    description: str | None = None
    include_deferred: bool = False


class VariableInfo(BaseModel):
    """Variable information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    key: str
    value: str | None = None
    description: str | None = None
    is_encrypted: bool = False


class ConnectionInfo(BaseModel):
    """Connection information from Airflow API (password excluded)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    connection_id: str
    conn_type: str | None = None
    description: str | None = None
    host: str | None = None
    port: int | None = None
    schema_: str | None = Field(None, alias="schema")
    login: str | None = None
    extra: str | None = None


class ImportError(BaseModel):
    """Import error information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    import_error_id: int | None = None
    timestamp: datetime | None = None
    filename: str | None = None
    stack_trace: str | None = None


class DAGWarning(BaseModel):
    """DAG warning information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    dag_id: str | None = None
    warning_type: str | None = None
    message: str | None = None
    timestamp: datetime | None = None


class AssetInfo(BaseModel):
    """Asset/Dataset information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    id: int | None = None
    uri: str
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    consuming_dags: list[dict[str, Any]] = Field(default_factory=list)
    producing_tasks: list[dict[str, Any]] = Field(default_factory=list)
    # Airflow 3 uses scheduled_dags instead of consuming_dags
    scheduled_dags: list[dict[str, Any]] = Field(default_factory=list)


class VersionInfo(BaseModel):
    """Airflow version information."""

    model_config = ConfigDict(extra="allow")

    version: str
    git_version: str | None = None


class ProviderInfo(BaseModel):
    """Provider package information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    package_name: str
    version: str | None = None
    description: str | None = None


class PluginInfo(BaseModel):
    """Plugin information from Airflow API."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    hooks: list[str] = Field(default_factory=list)
    executors: list[str] = Field(default_factory=list)
    macros: list[Any] = Field(default_factory=list)
    flask_blueprints: list[Any] = Field(default_factory=list)
    appbuilder_views: list[Any] = Field(default_factory=list)
    appbuilder_menu_items: list[Any] = Field(default_factory=list)


# Response wrapper models for list endpoints
class ListResponse(BaseModel):
    """Base model for list responses with pagination metadata."""

    total_entries: int = 0


class DAGListResponse(ListResponse):
    """Response for listing DAGs."""

    dags: list[DAGInfo] = Field(default_factory=list)


class DAGRunListResponse(ListResponse):
    """Response for listing DAG runs."""

    dag_runs: list[DAGRun] = Field(default_factory=list)


class TaskListResponse(ListResponse):
    """Response for listing tasks."""

    tasks: list[TaskInfo] = Field(default_factory=list)


class PoolListResponse(ListResponse):
    """Response for listing pools."""

    pools: list[PoolInfo] = Field(default_factory=list)


class VariableListResponse(ListResponse):
    """Response for listing variables."""

    variables: list[VariableInfo] = Field(default_factory=list)


class ConnectionListResponse(ListResponse):
    """Response for listing connections."""

    connections: list[ConnectionInfo] = Field(default_factory=list)


class ImportErrorListResponse(ListResponse):
    """Response for listing import errors."""

    import_errors: list[ImportError] = Field(default_factory=list)


class DAGWarningListResponse(ListResponse):
    """Response for listing DAG warnings."""

    dag_warnings: list[DAGWarning] = Field(default_factory=list)


class AssetListResponse(ListResponse):
    """Response for listing assets."""

    assets: list[AssetInfo] = Field(default_factory=list)


class ProviderListResponse(ListResponse):
    """Response for listing providers."""

    providers: list[ProviderInfo] = Field(default_factory=list)


class PluginListResponse(ListResponse):
    """Response for listing plugins."""

    plugins: list[PluginInfo] = Field(default_factory=list)


# Error response model
class APIError(BaseModel):
    """Error response from Airflow API."""

    model_config = ConfigDict(extra="allow")

    error: str
    operation: str | None = None
    status: str | None = None
    available: bool = True
    note: str | None = None
    alternative: str | None = None
