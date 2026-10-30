"""Fail-closed health reporting through both public consumers."""

import json
from unittest.mock import Mock, call

import httpx
import pytest

from astro_airflow_mcp.cli import main as cli
from astro_airflow_mcp.tools import diagnostic


@pytest.fixture(params=["mcp", "cli"])
def health(request, mocker):
    adapter = Mock()
    adapter.get_version.return_value = {"version": "3.3.2"}
    adapter.list_import_errors.return_value = {"import_errors": [], "total_entries": 0}
    adapter.list_dag_warnings.return_value = {"dag_warnings": [], "total_entries": 0}
    adapter.list_dags.return_value = {
        "dags": [{"dag_id": "first"}, {"dag_id": "second"}],
        "total_entries": 2,
    }
    adapter.get_dag_stats.return_value = {
        "dags": [{"dag_id": "first"}, {"dag_id": "second"}],
        "total_entries": 2,
    }
    if request.param == "mcp":
        factory = mocker.patch.object(diagnostic, "_get_adapter", return_value=adapter)
        tool = diagnostic.get_system_health
        function = tool.fn if hasattr(tool, "fn") else tool

        def invoke():
            return json.loads(function())
    else:
        factory = mocker.patch.object(cli, "get_adapter", return_value=adapter)
        output = mocker.patch.object(cli, "output_json")

        def invoke():
            cli.health()
            return output.call_args.args[0]

    return adapter, factory, invoke


def test_complete_checks_are_healthy(health):
    adapter, _, invoke = health
    result = invoke()
    assert result["overall_status"] == "healthy"
    assert result["dag_stats"]["total_entries"] == 2
    adapter.get_dag_stats.assert_called_once_with(dag_ids=["first", "second"])


@pytest.mark.parametrize(
    "method",
    ["get_version", "list_import_errors", "list_dag_warnings", "list_dags", "get_dag_stats"],
)
@pytest.mark.parametrize("error", [httpx.ConnectError("unreachable"), httpx.ReadTimeout("timeout")])
def test_failed_check_is_unknown(health, method, error):
    adapter, _, invoke = health
    getattr(adapter, method).side_effect = error
    result = invoke()
    section = {
        "get_version": "version",
        "list_import_errors": "import_errors",
        "list_dag_warnings": "dag_warnings",
        "list_dags": "dag_stats",
        "get_dag_stats": "dag_stats",
    }[method]
    assert result["overall_status"] == "unknown"
    assert section in result["status_reason"]
    assert result[section]["error_type"] == type(error).__name__
    assert result[section]["retryable"] is False


def test_adapter_initialization_failure_is_unknown(health):
    _, factory, invoke = health
    factory.side_effect = httpx.ConnectError("unreachable")
    result = invoke()
    assert result["overall_status"] == "unknown"
    assert result["error"]["error_type"] == "ConnectError"


@pytest.mark.parametrize(
    "stats",
    [
        {"dags": [], "total_entries": 0},
        {"dags": [{"dag_id": "first"}], "total_entries": 1},
        {
            "dags": [{"dag_id": "first"}],
            "total_entries": 1,
            "errors": [{"dag_id": "second", "error": "Forbidden"}],
        },
        {"available": False, "note": "Endpoint not available"},
        {"error": "Forbidden"},
        {},
    ],
)
def test_missing_or_partial_stats_are_unknown(health, stats):
    adapter, _, invoke = health
    adapter.get_dag_stats.return_value = stats
    result = invoke()
    assert result["overall_status"] == "unknown"
    assert "dag_stats" in result["status_reason"]
    assert result["dag_stats"]["available"] is False
    assert result["dag_stats"]["error"]


@pytest.mark.parametrize(
    ("method", "payload"),
    [
        ("get_version", {}),
        ("list_import_errors", {}),
        ("list_dag_warnings", {}),
        ("list_import_errors", {"error": "Forbidden"}),
        ("list_dag_warnings", {"available": False}),
        ("list_dags", {"error": "Forbidden"}),
        ("list_dags", {"dags": [], "total_entries": 0, "error": "Forbidden"}),
    ],
)
def test_malformed_or_error_responses_are_unknown(health, method, payload):
    adapter, _, invoke = health
    getattr(adapter, method).return_value = payload
    assert invoke()["overall_status"] == "unknown"


def test_dag_discovery_handles_server_capped_pages(health):
    adapter, _, invoke = health
    adapter.list_dags.side_effect = [
        {"dags": [{"dag_id": "first"}], "total_entries": 2},
        {"dags": [{"dag_id": "second"}], "total_entries": 2},
    ]
    assert invoke()["overall_status"] == "healthy"
    assert adapter.list_dags.call_args_list == [
        call(limit=100, offset=0),
        call(limit=100, offset=1),
    ]


def test_premature_empty_page_is_unknown(health):
    adapter, _, invoke = health
    adapter.list_dags.side_effect = [
        {"dags": [{"dag_id": "first"}], "total_entries": 2},
        {"dags": [], "total_entries": 2},
    ]
    result = invoke()
    assert result["overall_status"] == "unknown"
    assert "DAG listing ended" in result["dag_stats"]["error"]
    adapter.get_dag_stats.assert_not_called()


def test_verified_empty_instance_is_healthy(health):
    adapter, _, invoke = health
    adapter.list_dags.return_value = {"dags": [], "total_entries": 0}
    result = invoke()
    assert result["overall_status"] == "healthy"
    assert result["dag_stats"] == {"dags": [], "total_entries": 0}
    adapter.get_dag_stats.assert_not_called()


@pytest.mark.parametrize(
    ("section", "status"), [("import_errors", "unhealthy"), ("dag_warnings", "warning")]
)
def test_known_findings_preserved(health, section, status):
    adapter, _, invoke = health
    getattr(adapter, f"list_{section}").return_value = {
        section: [{"message": "problem"}],
        "total_entries": 120,
    }
    result = invoke()
    assert result["overall_status"] == status
    assert result[section]["count"] == 120


def test_known_import_errors_remain_unhealthy_with_incomplete_checks(health):
    adapter, _, invoke = health
    adapter.list_import_errors.return_value = {"import_errors": [{"message": "broken DAG"}]}
    adapter.get_dag_stats.side_effect = httpx.ConnectError("unreachable")
    result = invoke()
    assert result["overall_status"] == "unhealthy"
    assert "import error" in result["status_reason"]
    assert "dag_stats" in result["status_reason"]


def test_warning_with_failed_check_is_unknown(health):
    adapter, _, invoke = health
    adapter.list_dag_warnings.return_value = {"dag_warnings": [{"message": "warning"}]}
    adapter.get_dag_stats.side_effect = httpx.ConnectError("unreachable")
    result = invoke()
    assert result["overall_status"] == "unknown"
    assert result["dag_warnings"]["count"] == 1
