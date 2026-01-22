"""Tests for Pydantic models."""

from datetime import datetime

from astro_airflow_mcp.models import (
    APIError,
    AssetInfo,
    ConnectionInfo,
    DAGInfo,
    DAGRun,
    DAGWarning,
    ImportError,
    PluginInfo,
    PoolInfo,
    ProviderInfo,
    TaskInfo,
    TaskInstance,
    VariableInfo,
    VersionInfo,
)


class TestDAGInfo:
    """Tests for DAGInfo model."""

    def test_minimal_dag_info(self):
        """Test DAGInfo with minimal fields."""
        dag = DAGInfo(dag_id="test_dag")
        assert dag.dag_id == "test_dag"
        assert dag.is_paused is False
        assert dag.is_active is True
        assert dag.owners == []
        assert dag.tags == []

    def test_full_dag_info(self):
        """Test DAGInfo with all fields."""
        dag = DAGInfo(
            dag_id="example_dag",
            dag_display_name="Example DAG",
            is_paused=True,
            is_active=False,
            is_subdag=False,
            fileloc="/opt/airflow/dags/example.py",
            file_token="abcd1234",
            owners=["airflow", "admin"],
            description="An example DAG",
            schedule_interval="0 * * * *",
            tags=[{"name": "production"}],
            max_active_runs=5,
            max_active_tasks=10,
            has_task_concurrency_limits=True,
            has_import_errors=False,
        )
        assert dag.dag_id == "example_dag"
        assert dag.is_paused is True
        assert dag.owners == ["airflow", "admin"]
        assert dag.schedule_interval == "0 * * * *"

    def test_dag_info_extra_fields(self):
        """Test DAGInfo allows extra fields."""
        dag = DAGInfo(dag_id="test", custom_field="custom_value")
        assert dag.dag_id == "test"
        assert dag.custom_field == "custom_value"


class TestDAGRun:
    """Tests for DAGRun model."""

    def test_minimal_dag_run(self):
        """Test DAGRun with minimal fields."""
        run = DAGRun(dag_run_id="manual__2024-01-01", dag_id="test_dag")
        assert run.dag_run_id == "manual__2024-01-01"
        assert run.dag_id == "test_dag"
        assert run.external_trigger is False

    def test_dag_run_with_dates(self):
        """Test DAGRun with datetime fields."""
        now = datetime.now()
        run = DAGRun(
            dag_run_id="scheduled__2024-01-01",
            dag_id="test_dag",
            logical_date=now,
            start_date=now,
            state="running",
            run_type="scheduled",
        )
        assert run.state == "running"
        assert run.run_type == "scheduled"
        assert run.logical_date == now


class TestTaskInfo:
    """Tests for TaskInfo model."""

    def test_minimal_task_info(self):
        """Test TaskInfo with minimal fields."""
        task = TaskInfo(task_id="extract")
        assert task.task_id == "extract"
        assert task.depends_on_past is False
        assert task.downstream_task_ids == []

    def test_task_with_dependencies(self):
        """Test TaskInfo with dependency info."""
        task = TaskInfo(
            task_id="transform",
            operator_name="PythonOperator",
            upstream_task_ids=["extract"],
            downstream_task_ids=["load"],
        )
        assert task.upstream_task_ids == ["extract"]
        assert task.downstream_task_ids == ["load"]


class TestTaskInstance:
    """Tests for TaskInstance model."""

    def test_task_instance(self):
        """Test TaskInstance model."""
        ti = TaskInstance(
            task_id="extract",
            dag_id="etl_dag",
            dag_run_id="manual__2024-01-01",
            state="success",
            try_number=1,
            duration=10.5,
        )
        assert ti.task_id == "extract"
        assert ti.state == "success"
        assert ti.duration == 10.5


class TestPoolInfo:
    """Tests for PoolInfo model."""

    def test_default_pool(self):
        """Test PoolInfo with defaults."""
        pool = PoolInfo(name="default_pool")
        assert pool.name == "default_pool"
        assert pool.slots == 128
        assert pool.occupied_slots == 0

    def test_custom_pool(self):
        """Test PoolInfo with custom values."""
        pool = PoolInfo(
            name="limited_pool",
            slots=5,
            occupied_slots=3,
            running_slots=2,
            queued_slots=1,
            open_slots=2,
        )
        assert pool.slots == 5
        assert pool.occupied_slots == 3
        assert pool.open_slots == 2


class TestConnectionInfo:
    """Tests for ConnectionInfo model."""

    def test_connection_info(self):
        """Test ConnectionInfo model."""
        conn = ConnectionInfo(
            connection_id="postgres_default",
            conn_type="postgres",
            host="localhost",
            port=5432,
            login="airflow",
        )
        assert conn.connection_id == "postgres_default"
        assert conn.conn_type == "postgres"
        assert conn.port == 5432

    def test_connection_info_schema_alias(self):
        """Test ConnectionInfo handles 'schema' field aliasing."""
        conn = ConnectionInfo(
            connection_id="test",
            conn_type="postgres",
            schema="public",
        )
        assert conn.schema_ == "public"


class TestVariableInfo:
    """Tests for VariableInfo model."""

    def test_variable_info(self):
        """Test VariableInfo model."""
        var = VariableInfo(
            key="api_endpoint",
            value="https://api.example.com",
            description="External API URL",
        )
        assert var.key == "api_endpoint"
        assert var.value == "https://api.example.com"


class TestAssetInfo:
    """Tests for AssetInfo model."""

    def test_asset_info(self):
        """Test AssetInfo model."""
        asset = AssetInfo(
            id=1,
            uri="s3://bucket/path/file.csv",
            consuming_dags=[{"dag_id": "consumer_dag"}],
            producing_tasks=[{"task_id": "producer_task"}],
        )
        assert asset.uri == "s3://bucket/path/file.csv"
        assert len(asset.consuming_dags) == 1


class TestVersionInfo:
    """Tests for VersionInfo model."""

    def test_version_info(self):
        """Test VersionInfo model."""
        version = VersionInfo(version="3.0.0", git_version="abc123")
        assert version.version == "3.0.0"
        assert version.git_version == "abc123"


class TestProviderInfo:
    """Tests for ProviderInfo model."""

    def test_provider_info(self):
        """Test ProviderInfo model."""
        provider = ProviderInfo(
            package_name="apache-airflow-providers-amazon",
            version="8.0.0",
            description="Amazon AWS integration",
        )
        assert provider.package_name == "apache-airflow-providers-amazon"


class TestPluginInfo:
    """Tests for PluginInfo model."""

    def test_plugin_info(self):
        """Test PluginInfo model."""
        plugin = PluginInfo(
            name="custom_plugin",
            hooks=["CustomHook"],
            executors=[],
        )
        assert plugin.name == "custom_plugin"
        assert plugin.hooks == ["CustomHook"]


class TestImportError:
    """Tests for ImportError model."""

    def test_import_error(self):
        """Test ImportError model."""
        error = ImportError(
            import_error_id=1,
            filename="/opt/airflow/dags/broken_dag.py",
            stack_trace="SyntaxError: invalid syntax",
        )
        assert error.filename == "/opt/airflow/dags/broken_dag.py"
        assert "SyntaxError" in error.stack_trace


class TestDAGWarning:
    """Tests for DAGWarning model."""

    def test_dag_warning(self):
        """Test DAGWarning model."""
        warning = DAGWarning(
            dag_id="deprecated_dag",
            warning_type="deprecated_parameter",
            message="Parameter X is deprecated",
        )
        assert warning.dag_id == "deprecated_dag"
        assert warning.warning_type == "deprecated_parameter"


class TestAPIError:
    """Tests for APIError model."""

    def test_api_error(self):
        """Test APIError model for unavailable features."""
        error = APIError(
            error="Not found",
            operation="get_dag_stats",
            available=False,
            note="dagStats not available in Airflow 2.x",
            alternative="Use list_dag_runs instead",
        )
        assert error.available is False
        assert error.alternative == "Use list_dag_runs instead"
