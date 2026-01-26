"""Tests for consolidated MCP tools."""

import json
from unittest.mock import MagicMock

import astro_airflow_mcp.tools.diagnostic as diagnostic_module


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
        mock_dag = {"dag_id": "example_dag", "is_paused": False}
        mock_tasks = {"tasks": [{"task_id": "task1"}, {"task_id": "task2"}]}
        mock_source = {"content": "print('hello')"}

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_dag.return_value = mock_dag
        mock_adapter.list_tasks.return_value = mock_tasks
        mock_adapter.get_dag_source.return_value = mock_source

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        explore_dag_fn = get_tool_fn(diagnostic_module, "explore_dag")
        result = explore_dag_fn("example_dag")
        data = json.loads(result)

        assert data["dag_id"] == "example_dag"
        assert data["dag_info"]["dag_id"] == "example_dag"
        assert len(data["tasks"]) == 2
        assert data["source"]["content"] == "print('hello')"

    def test_explore_dag_partial_failure(self, mocker):
        """Test explore_dag handles partial API failures."""
        mock_dag = {"dag_id": "example_dag"}

        # Create mock adapter with partial failures
        mock_adapter = MagicMock()
        mock_adapter.get_dag.return_value = mock_dag
        mock_adapter.list_tasks.side_effect = Exception("Tasks endpoint failed")
        mock_adapter.get_dag_source.side_effect = Exception("Source endpoint failed")

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        explore_dag_fn = get_tool_fn(diagnostic_module, "explore_dag")
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

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_dag_run.return_value = mock_run
        mock_adapter.get_task_instances.return_value = mock_task_instances

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        diagnose_fn = get_tool_fn(diagnostic_module, "diagnose_dag_run")
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
        # Create mock adapter that raises exception
        mock_adapter = MagicMock()
        mock_adapter.get_dag_run.side_effect = Exception("Run not found")

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        diagnose_fn = get_tool_fn(diagnostic_module, "diagnose_dag_run")
        result = diagnose_fn("example_dag", "nonexistent")
        data = json.loads(result)

        assert "error" in data["run_info"]


class TestGetSystemHealth:
    """Tests for get_system_health consolidated tool."""

    def test_get_system_health_healthy(self, mocker):
        """Test get_system_health when system is healthy."""
        mock_version = {"version": "3.0.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {"dag_warnings": []}
        mock_stats = {"dags": []}

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_version.return_value = mock_version
        mock_adapter.list_import_errors.return_value = mock_import_errors
        mock_adapter.list_dag_warnings.return_value = mock_warnings
        mock_adapter.get_dag_stats.return_value = mock_stats

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        health_fn = get_tool_fn(diagnostic_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["version"]["version"] == "3.0.0"
        assert data["import_errors"]["count"] == 0
        assert data["dag_warnings"]["count"] == 0
        assert data["overall_status"] == "healthy"

    def test_get_system_health_with_import_errors(self, mocker):
        """Test get_system_health detects import errors."""
        mock_version = {"version": "3.0.0"}
        mock_import_errors = {
            "import_errors": [{"filename": "/dags/broken.py", "stack_trace": "SyntaxError"}]
        }
        mock_warnings = {"dag_warnings": []}
        mock_stats = {"dags": []}

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_version.return_value = mock_version
        mock_adapter.list_import_errors.return_value = mock_import_errors
        mock_adapter.list_dag_warnings.return_value = mock_warnings
        mock_adapter.get_dag_stats.return_value = mock_stats

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        health_fn = get_tool_fn(diagnostic_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["import_errors"]["count"] == 1
        assert data["overall_status"] == "unhealthy"
        assert "import error" in data["status_reason"]

    def test_get_system_health_with_warnings(self, mocker):
        """Test get_system_health detects warnings."""
        mock_version = {"version": "3.0.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {
            "dag_warnings": [{"dag_id": "deprecated_dag", "warning_type": "deprecation"}]
        }
        mock_stats = {"dags": []}

        # Create mock adapter
        mock_adapter = MagicMock()
        mock_adapter.get_version.return_value = mock_version
        mock_adapter.list_import_errors.return_value = mock_import_errors
        mock_adapter.list_dag_warnings.return_value = mock_warnings
        mock_adapter.get_dag_stats.return_value = mock_stats

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        health_fn = get_tool_fn(diagnostic_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["dag_warnings"]["count"] == 1
        assert data["overall_status"] == "warning"

    def test_get_system_health_dag_stats_unavailable(self, mocker):
        """Test get_system_health handles missing dagStats (Airflow 2.x)."""
        mock_version = {"version": "2.9.0"}
        mock_import_errors = {"import_errors": []}
        mock_warnings = {"dag_warnings": []}

        # Create mock adapter where dag_stats raises exception
        mock_adapter = MagicMock()
        mock_adapter.get_version.return_value = mock_version
        mock_adapter.list_import_errors.return_value = mock_import_errors
        mock_adapter.list_dag_warnings.return_value = mock_warnings
        mock_adapter.get_dag_stats.side_effect = Exception("Endpoint not found")

        mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=mock_adapter)

        health_fn = get_tool_fn(diagnostic_module, "get_system_health")
        result = health_fn()
        data = json.loads(result)

        assert data["dag_stats"]["available"] is False
        # Should still report overall health
        assert data["overall_status"] == "healthy"
