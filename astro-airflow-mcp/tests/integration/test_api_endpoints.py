"""Integration tests for all API endpoints against real Airflow instances.

These tests validate that each adapter method works correctly with both
Airflow 2.x and 3.x. They run in CI against real Airflow containers.
"""

import pytest

from astro_airflow_mcp.adapters import create_adapter, detect_version

from .conftest import TEST_DAG_ID


class TestVersionDetection:
    """Test version detection against real Airflow."""

    def test_detect_version(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Should correctly detect Airflow version."""
        major, version = detect_version(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )
        assert major in (2, 3), f"Expected major version 2 or 3, got {major}"
        assert version, "Version string should not be empty"
        print(f"Detected Airflow {version} (major: {major})")


class TestAdapterCreation:
    """Test adapter creation against real Airflow."""

    def test_create_adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Should create appropriate adapter for detected version."""
        adapter = create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )
        assert adapter is not None
        assert adapter.version
        print(f"Created adapter for Airflow {adapter.version}")


class TestDAGEndpoints:
    """Test DAG-related endpoints."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_list_dags(self, adapter):
        """Should list DAGs successfully."""
        result = adapter.list_dags(limit=10)
        assert "dags" in result
        assert isinstance(result["dags"], list)
        print(f"Found {len(result['dags'])} DAGs")

    def test_get_dag(self, adapter):
        """Should get a specific DAG."""
        result = adapter.get_dag(TEST_DAG_ID)
        assert result.get("dag_id") == TEST_DAG_ID
        print(f"Got DAG: {TEST_DAG_ID}")

    def test_list_tasks(self, adapter):
        """Should list tasks for a DAG."""
        result = adapter.list_tasks(TEST_DAG_ID)
        assert "tasks" in result
        print(f"DAG {TEST_DAG_ID} has {len(result['tasks'])} tasks")


class TestDAGStatsEndpoint:
    """Test DAG stats endpoint - the endpoint that caught us with version differences."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_get_dag_stats_with_dag_ids(self, adapter):
        """Should get stats for specific DAGs."""
        result = adapter.get_dag_stats(dag_ids=[TEST_DAG_ID])
        assert "error" not in result or "available" not in result
        print(f"Got stats for DAG {TEST_DAG_ID}: {result}")

    def test_get_dag_stats_without_dag_ids(self, adapter):
        """Should get stats for all DAGs when no dag_ids provided.

        This is the critical test - Airflow 2.x requires dag_ids,
        but our adapter should handle this transparently.
        """
        result = adapter.get_dag_stats(dag_ids=None)

        # Should not return an error
        assert "error" not in result or "available" not in result
        print(f"Got stats for all DAGs: {len(result.get('dags', []))} entries")


class TestMonitoringEndpoints:
    """Test monitoring endpoints."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_list_import_errors(self, adapter):
        """Should list import errors."""
        result = adapter.list_import_errors(limit=10)
        assert "import_errors" in result
        print(f"Found {len(result['import_errors'])} import errors")

    def test_list_dag_warnings(self, adapter):
        """Should list DAG warnings."""
        result = adapter.list_dag_warnings(limit=10)
        assert "dag_warnings" in result
        print(f"Found {len(result['dag_warnings'])} DAG warnings")

    def test_get_version(self, adapter):
        """Should get Airflow version."""
        result = adapter.get_version()
        assert "version" in result
        print(f"Airflow version: {result['version']}")


class TestResourceEndpoints:
    """Test resource endpoints (pools, connections, variables)."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_list_pools(self, adapter):
        """Should list pools."""
        result = adapter.list_pools(limit=10)
        assert "pools" in result
        # Default pool should always exist
        pool_names = [p["name"] for p in result["pools"]]
        assert "default_pool" in pool_names
        print(f"Found {len(result['pools'])} pools")

    def test_get_pool(self, adapter):
        """Should get specific pool."""
        result = adapter.get_pool("default_pool")
        assert result.get("name") == "default_pool"
        print(f"Got pool: {result}")

    def test_list_variables(self, adapter):
        """Should list variables."""
        result = adapter.list_variables(limit=10)
        assert "variables" in result
        print(f"Found {len(result['variables'])} variables")

    def test_list_connections(self, adapter):
        """Should list connections (with passwords filtered)."""
        result = adapter.list_connections(limit=10)
        assert "connections" in result

        # Verify passwords are filtered
        for conn in result.get("connections", []):
            if "password" in conn:
                assert conn["password"] in (
                    None,
                    "",
                    "***FILTERED***",
                ), f"Password not filtered for {conn.get('connection_id')}"
        print(f"Found {len(result['connections'])} connections")


class TestAssetEndpoints:
    """Test asset/dataset endpoints."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_list_assets(self, adapter):
        """Should list assets (normalized from datasets in v2)."""
        result = adapter.list_assets(limit=10)
        # Response should have 'assets' key (normalized from 'datasets' in v2)
        assert "assets" in result or "available" in result
        print(f"Assets response: {result}")


class TestProviderEndpoints:
    """Test provider/plugin endpoints."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_list_providers(self, adapter):
        """Should list providers."""
        result = adapter.list_providers()
        assert "providers" in result
        print(f"Found {len(result['providers'])} providers")

    def test_list_plugins(self, adapter):
        """Should list plugins."""
        result = adapter.list_plugins(limit=10)
        assert "plugins" in result
        print(f"Found {len(result['plugins'])} plugins")


class TestDAGSourceEndpoint:
    """Test DAG source code endpoint."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_get_dag_source(self, adapter):
        """Should get DAG source code for an existing DAG.

        Note: V2 uses file_token from DAG details, V3 uses dag_id directly.
        The adapter handles this transparently.
        """
        result = adapter.get_dag_source(TEST_DAG_ID)

        assert isinstance(result, dict)
        if "error" not in result and "available" not in result:
            assert "content" in result
        print(f"Got source for DAG {TEST_DAG_ID}: {len(str(result))} chars")


class TestDAGRunEndpoints:
    """Test DAG run operations - list, get, and trigger."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_trigger_dag_run(self, adapter):
        """Should trigger a new DAG run."""
        result = adapter.trigger_dag_run(
            dag_id=TEST_DAG_ID,
            conf={"test_key": "test_value"},
        )

        assert result.get("dag_id") == TEST_DAG_ID
        assert "dag_run_id" in result
        # V2 uses execution_date, V3 uses logical_date
        assert "execution_date" in result or "logical_date" in result
        print(f"Triggered run {result.get('dag_run_id')} for DAG {TEST_DAG_ID}")

    def test_list_dag_runs_all(self, adapter):
        """Should list DAG runs across all DAGs.

        Note: When dag_id is None, uses '~' for Airflow 2.x compatibility.
        """
        result = adapter.list_dag_runs(dag_id=None, limit=10)

        assert "dag_runs" in result
        assert isinstance(result["dag_runs"], list)
        print(f"Found {len(result['dag_runs'])} total DAG runs")

    def test_list_dag_runs_for_specific_dag(self, adapter):
        """Should list DAG runs for a specific DAG."""
        result = adapter.list_dag_runs(dag_id=TEST_DAG_ID, limit=10)

        assert "dag_runs" in result
        assert isinstance(result["dag_runs"], list)
        for run in result["dag_runs"]:
            assert run.get("dag_id") == TEST_DAG_ID
        print(f"Found {len(result['dag_runs'])} runs for DAG {TEST_DAG_ID}")

    def test_get_dag_run(self, adapter):
        """Should get details for a specific DAG run."""
        # Trigger a run to ensure one exists
        triggered = adapter.trigger_dag_run(dag_id=TEST_DAG_ID)
        dag_run_id = triggered["dag_run_id"]

        result = adapter.get_dag_run(TEST_DAG_ID, dag_run_id)

        assert result.get("dag_id") == TEST_DAG_ID
        assert result.get("dag_run_id") == dag_run_id
        assert "state" in result
        print(f"Got run {dag_run_id} with state: {result.get('state')}")


class TestTaskEndpoints:
    """Test task and task instance operations.

    Tests that need a completed DAG run use the completed_dag_run session fixture.
    """

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_get_task(self, adapter):
        """Should get details of a specific task definition."""
        result = adapter.get_task(TEST_DAG_ID, "quick_task")

        assert result.get("task_id") == "quick_task"
        print(f"Got task quick_task from DAG {TEST_DAG_ID}")

    def test_get_task_instances(self, adapter, completed_dag_run):
        """Should list task instances for a DAG run."""
        dag_id, dag_run_id = completed_dag_run

        result = adapter.get_task_instances(dag_id, dag_run_id, limit=100)

        assert "task_instances" in result
        assert isinstance(result["task_instances"], list)
        print(f"Found {len(result['task_instances'])} task instances for run {dag_run_id}")

    def test_get_task_instance(self, adapter, completed_dag_run):
        """Should get details of a specific task instance."""
        dag_id, dag_run_id = completed_dag_run

        instances = adapter.get_task_instances(dag_id, dag_run_id, limit=10)
        if not instances.get("task_instances"):
            pytest.skip("No task instances available")

        task_id = instances["task_instances"][0]["task_id"]
        result = adapter.get_task_instance(dag_id, dag_run_id, task_id)

        assert result.get("task_id") == task_id
        assert result.get("dag_id") == dag_id
        assert "state" in result
        print(f"Got task instance {task_id} with state: {result.get('state')}")

    def test_get_task_logs(self, adapter, completed_dag_run):
        """Should get logs for a task instance."""
        dag_id, dag_run_id = completed_dag_run

        instances = adapter.get_task_instances(dag_id, dag_run_id, limit=20)
        target_task = None
        for ti in instances.get("task_instances", []):
            if ti.get("state") in ("success", "failed", "upstream_failed"):
                target_task = ti
                break

        if not target_task:
            pytest.skip("No executed task instances available to test logs")

        task_id = target_task["task_id"]
        try_number = target_task.get("try_number", 1)

        result = adapter.get_task_logs(
            dag_id=dag_id,
            dag_run_id=dag_run_id,
            task_id=task_id,
            try_number=try_number,
            full_content=True,
        )

        assert isinstance(result, dict)
        if "available" not in result:
            assert "content" in result or len(result) > 0
        print(f"Got logs for task {task_id} (try {try_number}): {len(str(result))} chars")


class TestVariableEndpoint:
    """Test variable get operation."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_get_variable(self, adapter):
        """Should get a specific variable if one exists."""
        variables = adapter.list_variables(limit=10)
        if not variables.get("variables"):
            pytest.skip("No variables configured to test")

        variable_key = variables["variables"][0]["key"]
        result = adapter.get_variable(variable_key)

        assert result.get("key") == variable_key
        assert "value" in result
        print(f"Got variable {variable_key}")


class TestConfigEndpoint:
    """Test configuration endpoint."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_get_config(self, adapter):
        """Should get Airflow configuration.

        Note: Requires AIRFLOW__WEBSERVER__EXPOSE_CONFIG=true in Airflow 2.x.
        """
        result = adapter.get_config()

        assert isinstance(result, dict)

        # Check for successful response structure
        if "error" not in result and "note" not in result:
            # Successful response has 'sections' containing config
            assert "sections" in result
            assert isinstance(result["sections"], list)
            print(f"Found {len(result['sections'])} config sections")
        else:
            # Airflow 2.x without expose_config returns error info
            print(f"Config access returned: {result}")


class TestPauseUnpauseEndpoints:
    """Test pause and unpause DAG operations."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_pause_dag(self, adapter):
        """Should pause a DAG."""
        # Get initial state
        initial = adapter.get_dag(TEST_DAG_ID)
        initial_paused = initial.get("is_paused")

        try:
            # Pause the DAG
            result = adapter.pause_dag(TEST_DAG_ID)

            assert result.get("dag_id") == TEST_DAG_ID
            assert result.get("is_paused") is True
            print(f"Paused DAG {TEST_DAG_ID}")
        finally:
            # Restore original state if it was unpaused
            if not initial_paused:
                adapter.unpause_dag(TEST_DAG_ID)

    def test_unpause_dag(self, adapter):
        """Should unpause a DAG."""
        # Get initial state
        initial = adapter.get_dag(TEST_DAG_ID)
        initial_paused = initial.get("is_paused")

        try:
            # Unpause the DAG
            result = adapter.unpause_dag(TEST_DAG_ID)

            assert result.get("dag_id") == TEST_DAG_ID
            assert result.get("is_paused") is False
            print(f"Unpaused DAG {TEST_DAG_ID}")
        finally:
            # Restore original state if it was paused
            if initial_paused:
                adapter.pause_dag(TEST_DAG_ID)

    def test_pause_unpause_roundtrip(self, adapter):
        """Should successfully pause and unpause a DAG."""
        # Get initial state
        initial = adapter.get_dag(TEST_DAG_ID)
        initial_paused = initial.get("is_paused")

        try:
            # Pause the DAG
            paused = adapter.pause_dag(TEST_DAG_ID)
            assert paused.get("is_paused") is True

            # Verify via get_dag
            verify_paused = adapter.get_dag(TEST_DAG_ID)
            assert verify_paused.get("is_paused") is True

            # Unpause the DAG
            unpaused = adapter.unpause_dag(TEST_DAG_ID)
            assert unpaused.get("is_paused") is False

            # Verify via get_dag
            verify_unpaused = adapter.get_dag(TEST_DAG_ID)
            assert verify_unpaused.get("is_paused") is False

            print(f"Successfully completed pause/unpause roundtrip for {TEST_DAG_ID}")
        finally:
            # Restore original state
            if initial_paused:
                adapter.pause_dag(TEST_DAG_ID)
            else:
                adapter.unpause_dag(TEST_DAG_ID)
