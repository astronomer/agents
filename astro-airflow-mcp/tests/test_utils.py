"""Tests for shared utility functions."""

from astro_airflow_mcp.constants import (
    DEFAULT_AIRFLOW_URL,
    DEFAULT_LIMIT,
    DEFAULT_OFFSET,
    FAILED_TASK_STATES,
    TERMINAL_DAG_RUN_STATES,
)
from astro_airflow_mcp.utils import (
    extract_failed_tasks,
    filter_connection_passwords,
    wrap_list_response,
)


class TestConstants:
    """Tests for shared constants."""

    def test_terminal_dag_run_states(self):
        """Test terminal DAG run states are defined correctly."""
        assert {"success", "failed", "upstream_failed"} == TERMINAL_DAG_RUN_STATES

    def test_failed_task_states(self):
        """Test failed task states are defined correctly."""
        assert {"failed", "upstream_failed"} == FAILED_TASK_STATES

    def test_default_values(self):
        """Test default values are defined correctly."""
        assert DEFAULT_LIMIT == 100
        assert DEFAULT_OFFSET == 0
        assert DEFAULT_AIRFLOW_URL == "http://localhost:8080"


class TestFilterConnectionPasswords:
    """Tests for filter_connection_passwords utility."""

    def test_filters_password_field(self):
        """Test that password field is filtered out."""
        connections = [
            {
                "connection_id": "my_conn",
                "conn_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "schema": "mydb",
                "login": "user",
                "password": "secret123",
                "extra": "{}",
            }
        ]
        result = filter_connection_passwords(connections)

        assert len(result) == 1
        assert result[0]["connection_id"] == "my_conn"
        assert result[0]["login"] == "user"
        assert "password" not in result[0]

    def test_handles_missing_fields(self):
        """Test that missing fields are handled gracefully."""
        connections = [{"connection_id": "minimal_conn"}]
        result = filter_connection_passwords(connections)

        assert len(result) == 1
        assert result[0]["connection_id"] == "minimal_conn"
        assert result[0]["conn_type"] is None
        assert result[0]["host"] is None

    def test_handles_empty_list(self):
        """Test that empty list returns empty list."""
        result = filter_connection_passwords([])
        assert result == []

    def test_preserves_all_safe_fields(self):
        """Test that all safe fields are preserved."""
        connections = [
            {
                "connection_id": "full_conn",
                "conn_type": "mysql",
                "description": "A test connection",
                "host": "db.example.com",
                "port": 3306,
                "schema": "testdb",
                "login": "admin",
                "extra": '{"ssl": true}',
                "password": "should_be_filtered",
            }
        ]
        result = filter_connection_passwords(connections)

        expected_fields = {
            "connection_id",
            "conn_type",
            "description",
            "host",
            "port",
            "schema",
            "login",
            "extra",
        }
        assert set(result[0].keys()) == expected_fields


class TestExtractFailedTasks:
    """Tests for extract_failed_tasks utility."""

    def test_extracts_failed_tasks(self):
        """Test extraction of failed tasks."""
        task_instances = [
            {"task_id": "task1", "state": "success", "try_number": 1},
            {
                "task_id": "task2",
                "state": "failed",
                "try_number": 2,
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-01-01T00:05:00",
            },
            {"task_id": "task3", "state": "running", "try_number": 1},
        ]
        result = extract_failed_tasks(task_instances)

        assert len(result) == 1
        assert result[0]["task_id"] == "task2"
        assert result[0]["state"] == "failed"
        assert result[0]["try_number"] == 2

    def test_extracts_upstream_failed(self):
        """Test extraction of upstream_failed tasks."""
        task_instances = [
            {"task_id": "task1", "state": "upstream_failed", "try_number": 1},
        ]
        result = extract_failed_tasks(task_instances)

        assert len(result) == 1
        assert result[0]["task_id"] == "task1"
        assert result[0]["state"] == "upstream_failed"

    def test_returns_empty_for_all_success(self):
        """Test that empty list is returned when all tasks succeeded."""
        task_instances = [
            {"task_id": "task1", "state": "success", "try_number": 1},
            {"task_id": "task2", "state": "success", "try_number": 1},
        ]
        result = extract_failed_tasks(task_instances)
        assert result == []

    def test_handles_empty_list(self):
        """Test that empty list returns empty list."""
        result = extract_failed_tasks([])
        assert result == []

    def test_handles_missing_fields(self):
        """Test that missing fields are handled gracefully."""
        task_instances = [{"state": "failed"}]
        result = extract_failed_tasks(task_instances)

        assert len(result) == 1
        assert result[0]["task_id"] is None
        assert result[0]["state"] == "failed"


class TestWrapListResponse:
    """Tests for wrap_list_response utility."""

    def test_wraps_response_with_pagination(self):
        """Test that response is wrapped with pagination metadata."""
        items = [{"id": 1}, {"id": 2}]
        data = {"total_entries": 10}
        result = wrap_list_response(items, "items", data)

        assert result["total_items"] == 10
        assert result["returned_count"] == 2
        assert result["items"] == items

    def test_uses_len_when_no_total_entries(self):
        """Test that len(items) is used when total_entries is missing."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]
        data = {}
        result = wrap_list_response(items, "dags", data)

        assert result["total_dags"] == 3
        assert result["returned_count"] == 3

    def test_handles_empty_list(self):
        """Test wrapping empty list."""
        result = wrap_list_response([], "tasks", {"total_entries": 0})

        assert result["total_tasks"] == 0
        assert result["returned_count"] == 0
        assert result["tasks"] == []

    def test_different_key_names(self):
        """Test that key_name is used correctly in output."""
        items = [{"name": "test"}]
        result = wrap_list_response(items, "dag_runs", {"total_entries": 1})

        assert "total_dag_runs" in result
        assert "dag_runs" in result
