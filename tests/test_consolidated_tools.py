"""Tests for consolidated MCP tools."""

import json


# Helper to get the underlying function from a decorated MCP tool
def get_tool_fn(module, tool_name):
    """Get the underlying function from an MCP tool."""
    tool = getattr(module, tool_name)
    # FastMCP's FunctionTool has a 'fn' attribute with the original function
    if hasattr(tool, "fn"):
        return tool.fn
    return tool


class TestExploreDag:
    """Tests for explore_dag consolidated tool."""

    def test_explore_dag_success(self, mocker):
        """Test explore_dag returns combined data."""
        import astro_airflow_mcp.server as server_module

        mock_dag = {"dag_id": "example_dag", "is_paused": False}
        mock_tasks = {"tasks": [{"task_id": "task1"}, {"task_id": "task2"}]}
        mock_source = {"content": "print('hello')"}

        def mock_api_call(endpoint, *args, **kwargs):
            if "dags/example_dag/tasks" in endpoint:
                return mock_tasks
            elif "dagSources" in endpoint:
                return mock_source
            else:
                return mock_dag

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        explore_dag_fn = get_tool_fn(server_module, "explore_dag")
        result = explore_dag_fn("example_dag")
        data = json.loads(result)

        assert data["dag_id"] == "example_dag"
        assert data["dag_info"]["dag_id"] == "example_dag"
        assert len(data["tasks"]) == 2
        assert data["source"]["content"] == "print('hello')"

    def test_explore_dag_partial_failure(self, mocker):
        """Test explore_dag handles partial API failures."""
        import astro_airflow_mcp.server as server_module

        mock_dag = {"dag_id": "example_dag"}

        def mock_api_call(endpoint, *args, **kwargs):
            if "tasks" in endpoint:
                raise Exception("Tasks endpoint failed")
            elif "dagSources" in endpoint:
                raise Exception("Source endpoint failed")
            return mock_dag

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        explore_dag_fn = get_tool_fn(server_module, "explore_dag")
        result = explore_dag_fn("example_dag")
        data = json.loads(result)

        # Should still have DAG info even if tasks/source failed
        assert data["dag_id"] == "example_dag"
        assert "error" in data["tasks"]
        assert "error" in data["source"]


class TestDiagnoseDagRun:
    """Tests for diagnose_dag_run consolidated tool."""

    def test_diagnose_dag_run_success(self, mocker):
        """Test diagnose_dag_run returns run and task info."""
        import astro_airflow_mcp.server as server_module

        mock_run = {
            "dag_run_id": "manual__2024-01-01",
            "state": "failed",
        }
        mock_task_instances = {
            "task_instances": [
                {"task_id": "task1", "state": "success"},
                {"task_id": "task2", "state": "failed", "try_number": 3},
                {"task_id": "task3", "state": "upstream_failed"},
            ]
        }

        def mock_api_call(endpoint, *args, **kwargs):
            if "taskInstances" in endpoint:
                return mock_task_instances
            return mock_run

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        diagnose_fn = get_tool_fn(server_module, "diagnose_dag_run")
        result = diagnose_fn("example_dag", "manual__2024-01-01")
        data = json.loads(result)

        assert data["dag_id"] == "example_dag"
        assert data["dag_run_id"] == "manual__2024-01-01"
        assert data["run_info"]["state"] == "failed"

        # Check summary
        assert data["summary"]["total_tasks"] == 3
        assert data["summary"]["state_counts"]["success"] == 1
        assert data["summary"]["state_counts"]["failed"] == 1
        assert data["summary"]["state_counts"]["upstream_failed"] == 1
        assert len(data["summary"]["failed_tasks"]) == 2

    def test_diagnose_dag_run_not_found(self, mocker):
        """Test diagnose_dag_run handles missing run."""
        import astro_airflow_mcp.server as server_module

        mocker.patch(
            "astro_airflow_mcp.server._call_airflow_api",
            side_effect=Exception("Run not found"),
        )

        diagnose_fn = get_tool_fn(server_module, "diagnose_dag_run")
        result = diagnose_fn("example_dag", "nonexistent")
        data = json.loads(result)

        assert "error" in data["run_info"]


class TestGetSystemHealth:
    """Tests for get_system_health consolidated tool."""

    def test_get_system_health_healthy(self, mocker):
        """Test get_system_health when system is healthy."""
        import astro_airflow_mcp.server as server_module

        mock_version = {"version": "3.0.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {"dag_warnings": []}
        mock_stats = {"dags": []}

        def mock_api_call(endpoint, *args, **kwargs):
            if "version" in endpoint:
                return mock_version
            elif "importErrors" in endpoint:
                return mock_import_errors
            elif "dagWarnings" in endpoint:
                return mock_warnings
            elif "dagStats" in endpoint:
                return mock_stats
            return {}

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        health_fn = get_tool_fn(server_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["version"]["version"] == "3.0.0"
        assert data["import_errors"]["count"] == 0
        assert data["dag_warnings"]["count"] == 0
        assert data["overall_status"] == "healthy"

    def test_get_system_health_with_import_errors(self, mocker):
        """Test get_system_health detects import errors."""
        import astro_airflow_mcp.server as server_module

        mock_version = {"version": "3.0.0"}
        mock_import_errors = {
            "import_errors": [{"filename": "/dags/broken.py", "stack_trace": "SyntaxError"}]
        }
        mock_warnings = {"dag_warnings": []}
        mock_stats = {"dags": []}

        def mock_api_call(endpoint, *args, **kwargs):
            if "version" in endpoint:
                return mock_version
            elif "importErrors" in endpoint:
                return mock_import_errors
            elif "dagWarnings" in endpoint:
                return mock_warnings
            elif "dagStats" in endpoint:
                return mock_stats
            return {}

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        health_fn = get_tool_fn(server_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["import_errors"]["count"] == 1
        assert data["overall_status"] == "unhealthy"
        assert "import error" in data["status_reason"]

    def test_get_system_health_with_warnings(self, mocker):
        """Test get_system_health detects warnings."""
        import astro_airflow_mcp.server as server_module

        mock_version = {"version": "3.0.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {
            "dag_warnings": [{"dag_id": "deprecated_dag", "warning_type": "deprecation"}]
        }
        mock_stats = {"dags": []}

        def mock_api_call(endpoint, *args, **kwargs):
            if "version" in endpoint:
                return mock_version
            elif "importErrors" in endpoint:
                return mock_import_errors
            elif "dagWarnings" in endpoint:
                return mock_warnings
            elif "dagStats" in endpoint:
                return mock_stats
            return {}

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        health_fn = get_tool_fn(server_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["dag_warnings"]["count"] == 1
        assert data["overall_status"] == "warning"

    def test_get_system_health_dag_stats_unavailable(self, mocker):
        """Test get_system_health handles missing dagStats (Airflow 2.x)."""
        import astro_airflow_mcp.server as server_module

        mock_version = {"version": "2.9.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {"dag_warnings": []}

        def mock_api_call(endpoint, *args, **kwargs):
            if "version" in endpoint:
                return mock_version
            elif "importErrors" in endpoint:
                return mock_import_errors
            elif "dagWarnings" in endpoint:
                return mock_warnings
            elif "dagStats" in endpoint:
                raise Exception("Endpoint not found")
            return {}

        mocker.patch("astro_airflow_mcp.server._call_airflow_api", side_effect=mock_api_call)

        health_fn = get_tool_fn(server_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["dag_stats"]["available"] is False
        # Should still report overall health
        assert data["overall_status"] == "healthy"
