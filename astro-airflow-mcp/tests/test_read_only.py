"""Tests for read-only mode (AF_READ_ONLY environment variable).

Verifies that all write operations are blocked when AF_READ_ONLY=1,
while read operations continue to work normally.
"""

import json
from unittest.mock import MagicMock

import pytest

from astro_airflow_mcp.adapters.base import ReadOnlyError, _assert_writable


class TestAssertWritable:
    """Unit tests for the _assert_writable guard function."""

    def test_allowed_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("AF_READ_ONLY", raising=False)
        _assert_writable("POST dags/test/dagRuns")  # should not raise

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes"])
    def test_blocked_with_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("AF_READ_ONLY", value)
        with pytest.raises(ReadOnlyError, match="read-only mode"):
            _assert_writable("POST dags/test/dagRuns")

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "off"])
    def test_allowed_with_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("AF_READ_ONLY", value)
        _assert_writable("POST dags/test/dagRuns")  # should not raise

    def test_error_message_includes_operation_and_env_var(self, monkeypatch):
        monkeypatch.setenv("AF_READ_ONLY", "1")
        with pytest.raises(ReadOnlyError, match="PATCH dags/my_dag") as exc_info:
            _assert_writable("PATCH dags/my_dag")
        assert "AF_READ_ONLY" in str(exc_info.value)


class TestEndToEnd:
    """End-to-end: tool _impl → real AirflowV3Adapter → real guard.

    Only httpx is mocked (to prevent network calls). Everything else is real.
    """

    def _real_adapter(self, mocker):
        mocker.patch("httpx.Client")
        from astro_airflow_mcp.adapters.airflow_v3 import AirflowV3Adapter

        return AirflowV3Adapter(airflow_url="http://localhost:8080", version="3.0.0")

    def test_pause_dag_blocked(self, monkeypatch, mocker):
        from astro_airflow_mcp.tools.dag import _pause_dag_impl

        monkeypatch.setenv("AF_READ_ONLY", "1")
        mocker.patch(
            "astro_airflow_mcp.tools.dag._get_adapter", return_value=self._real_adapter(mocker)
        )

        result = _pause_dag_impl("my_dag")
        assert "read-only mode" in result
        assert "PATCH" in result

    def test_unpause_dag_blocked(self, monkeypatch, mocker):
        from astro_airflow_mcp.tools.dag import _unpause_dag_impl

        monkeypatch.setenv("AF_READ_ONLY", "1")
        mocker.patch(
            "astro_airflow_mcp.tools.dag._get_adapter", return_value=self._real_adapter(mocker)
        )

        result = _unpause_dag_impl("my_dag")
        assert "read-only mode" in result

    def test_trigger_dag_blocked(self, monkeypatch, mocker):
        from astro_airflow_mcp.tools.dag_run import _trigger_dag_impl

        monkeypatch.setenv("AF_READ_ONLY", "1")
        mocker.patch(
            "astro_airflow_mcp.tools.dag_run._get_adapter", return_value=self._real_adapter(mocker)
        )

        result = _trigger_dag_impl("my_dag")
        assert "read-only mode" in result
        # _trigger_dag_impl unpause the DAG (PATCH) before triggering (POST),
        # so PATCH is the first write operation to be blocked.
        assert "PATCH" in result

    def test_clear_task_instances_blocked(self, monkeypatch, mocker):
        from astro_airflow_mcp.tools.task import _clear_task_instances_impl

        monkeypatch.setenv("AF_READ_ONLY", "1")
        mocker.patch(
            "astro_airflow_mcp.tools.task._get_adapter", return_value=self._real_adapter(mocker)
        )

        result = _clear_task_instances_impl(
            dag_id="my_dag", dag_run_id="run_1", task_ids=["task1"], dry_run=False
        )
        assert "read-only mode" in result

    def test_raw_request_non_get_blocked(self, monkeypatch, mocker):
        """Covers `af api -X POST/PUT/DELETE` path."""
        monkeypatch.setenv("AF_READ_ONLY", "1")
        adapter = self._real_adapter(mocker)

        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with pytest.raises(ReadOnlyError):
                adapter.raw_request(method, "variables")

    def test_read_operations_still_work(self, monkeypatch, mocker):
        """list_dags (GET) works even with AF_READ_ONLY=1."""
        from astro_airflow_mcp.tools.dag import _list_dags_impl

        monkeypatch.setenv("AF_READ_ONLY", "1")
        adapter = self._real_adapter(mocker)
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=adapter)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"dags": [{"dag_id": "dag1"}], "total_entries": 1}
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        data = json.loads(_list_dags_impl(limit=10, offset=0))
        assert data["total_dags"] == 1

    def test_writes_work_when_flag_off(self, monkeypatch, mocker):
        """pause_dag succeeds when AF_READ_ONLY is not set."""
        from astro_airflow_mcp.tools.dag import _pause_dag_impl

        monkeypatch.delenv("AF_READ_ONLY", raising=False)
        mock_adapter = MagicMock()
        mock_adapter.pause_dag.return_value = {"dag_id": "d", "is_paused": True}
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

        data = json.loads(_pause_dag_impl("d"))
        assert data["is_paused"] is True
