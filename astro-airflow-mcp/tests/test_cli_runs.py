"""Tests for the `af runs` CLI commands."""

from unittest.mock import MagicMock

from typer.testing import CliRunner

from astro_airflow_mcp.cli.main import app

runner = CliRunner()


class TestRunsListCommand:
    """Tests for `af runs list`."""

    def test_defaults_to_newest_first(self, mocker):
        """Default order_by is '-start_date' so the most recent runs come first."""
        mock_adapter = MagicMock()
        mock_adapter.list_dag_runs.return_value = {
            "dag_runs": [{"dag_run_id": "manual__2024-12-31"}],
            "total_entries": 1,
        }
        mocker.patch("astro_airflow_mcp.cli.runs.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["runs", "list", "-d", "example_dag"])

        assert result.exit_code == 0
        mock_adapter.list_dag_runs.assert_called_once_with(
            dag_id="example_dag",
            limit=100,
            offset=0,
            order_by="-start_date",
        )

    def test_custom_order_by_overrides_default(self, mocker):
        """Caller can override the default sort (e.g. to get oldest first)."""
        mock_adapter = MagicMock()
        mock_adapter.list_dag_runs.return_value = {"dag_runs": [], "total_entries": 0}
        mocker.patch("astro_airflow_mcp.cli.runs.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["runs", "list", "--order-by", "id"])

        assert result.exit_code == 0
        mock_adapter.list_dag_runs.assert_called_once_with(
            dag_id=None,
            limit=100,
            offset=0,
            order_by="id",
        )

    def test_end_date_filters_forwarded(self, mocker):
        """--end-date-gte / --end-date-lte are forwarded to the adapter as kwargs."""
        mock_adapter = MagicMock()
        mock_adapter.list_dag_runs.return_value = {"dag_runs": [], "total_entries": 0}
        mocker.patch("astro_airflow_mcp.cli.runs.get_adapter", return_value=mock_adapter)

        result = runner.invoke(
            app,
            [
                "runs",
                "list",
                "--end-date-gte",
                "2026-06-10T15:00:00Z",
                "--end-date-lte",
                "2026-06-10T15:15:00Z",
            ],
        )

        assert result.exit_code == 0
        mock_adapter.list_dag_runs.assert_called_once_with(
            dag_id=None,
            limit=100,
            offset=0,
            order_by="-start_date",
            end_date_gte="2026-06-10T15:00:00Z",
            end_date_lte="2026-06-10T15:15:00Z",
        )
