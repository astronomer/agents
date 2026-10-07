"""End-to-end task pagination through the MCP and CLI diagnostic entry points."""

import json

import pytest
from typer.testing import CliRunner

from astro_airflow_mcp.adapters import AirflowV2Adapter, AirflowV3Adapter
from astro_airflow_mcp.cli.main import app
from astro_airflow_mcp.tools import dag_run, diagnostic


@pytest.fixture(params=[AirflowV2Adapter, AirflowV3Adapter])
def adapter(request, mocker):
    """Use real pagination while mocking the existing adapter endpoints."""
    adapter = request.param("http://localhost:8080", "3.1.0")
    mocker.patch.object(adapter, "get_dag", return_value={"is_paused": False})
    mocker.patch.object(adapter, "trigger_dag_run", return_value={"dag_run_id": "run"})
    mocker.patch.object(adapter, "get_dag_run", return_value={"state": "failed"})
    mocker.patch("astro_airflow_mcp.tools.diagnostic._get_adapter", return_value=adapter)
    mocker.patch("astro_airflow_mcp.tools.dag_run._get_adapter", return_value=adapter)
    mocker.patch("astro_airflow_mcp.cli.runs.get_adapter", return_value=adapter)
    mocker.patch("astro_airflow_mcp.cli.main.init_context")
    mocker.patch("time.sleep")
    return adapter


def invoke(interface, command):
    """Call the public diagnostic or trigger-wait entry point without a server."""
    if interface == "cli":
        args = ["runs", command, "dag"]
        if command == "diagnose":
            args.append("run")
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)
    if command == "diagnose":
        tool = diagnostic.diagnose_dag_run
        return json.loads(getattr(tool, "fn", tool)("dag", "run"))
    tool = dag_run.trigger_dag_and_wait
    return json.loads(getattr(tool, "fn", tool)("dag"))


@pytest.mark.parametrize("interface", ["mcp", "cli"])
@pytest.mark.parametrize("command", ["diagnose", "trigger-wait"])
def test_failures_beyond_server_clamped_pages(adapter, mocker, interface, command):
    """All four callers find late failures, including distinct mapped instances."""
    tasks = [{"task_id": "mapped", "map_index": i, "state": "success"} for i in range(813)] + [
        {"task_id": "mapped", "map_index": 813, "state": "failed"},
        {"task_id": "mapped", "map_index": 814, "state": "upstream_failed"},
    ]
    pages = mocker.patch.object(
        adapter,
        "get_task_instances",
        side_effect=lambda _dag_id, _dag_run_id, limit, offset: {
            "task_instances": tasks[offset : offset + min(limit, 40)],
            "total_entries": len(tasks),
        },
    )

    result = invoke(interface, command)

    summary = result["summary"] if command == "diagnose" else result
    assert [(task["map_index"], task["state"]) for task in summary["failed_tasks"]] == [
        (813, "failed"),
        (814, "upstream_failed"),
    ]
    assert [call.kwargs["offset"] for call in pages.call_args_list] == list(range(0, 815, 40))
    if command == "diagnose":
        assert summary["total_tasks"] == 815
        assert summary["state_counts"] == {"success": 813, "failed": 1, "upstream_failed": 1}
        assert len(result["task_instances"]) == 100
        assert result["task_instances"] == tasks[813:] + tasks[:98]
        assert result["task_instances_returned"] == 100
        assert result["task_instances_truncated"] is True


@pytest.mark.parametrize("interface", ["mcp", "cli"])
def test_diagnosis_prioritizes_failures_and_counts_unset_states(adapter, mocker, interface):
    """A late failure stays visible during a cascade, and unset states share a count."""
    tasks = [
        {"task_id": "pending", "state": None},
        {"task_id": "missing"},
        *[{"task_id": "mapped", "map_index": i, "state": "upstream_failed"} for i in range(100)],
        {"task_id": "root", "state": "failed"},
    ]
    mocker.patch.object(
        adapter,
        "get_task_instances",
        side_effect=lambda _dag_id, _dag_run_id, limit, offset: {
            "task_instances": tasks[offset : offset + limit],
            "total_entries": len(tasks),
        },
    )

    result = invoke(interface, "diagnose")

    assert result["summary"]["state_counts"] == {"unknown": 2, "upstream_failed": 100, "failed": 1}
    assert result["summary"]["total_tasks"] == 103
    assert len(result["summary"]["failed_tasks"]) == 101
    assert result["task_instances"] == [tasks[-1], *tasks[2:101]]
    assert result["task_instances_returned"] == 100
    assert result["task_instances_truncated"] is True


@pytest.mark.parametrize("interface", ["mcp", "cli"])
@pytest.mark.parametrize("command", ["diagnose", "trigger-wait"])
@pytest.mark.parametrize("failure", [{"available": False}, RuntimeError("API unavailable")])
def test_incomplete_pages_are_reported(adapter, mocker, interface, command, failure):
    """A failed second page cannot become an empty or partial failure summary."""
    mocker.patch.object(
        adapter,
        "get_task_instances",
        side_effect=[
            {"task_instances": [{"task_id": "ok", "state": "success"}], "total_entries": 2},
            failure,
        ],
    )

    result = invoke(interface, command)

    if command == "diagnose":
        assert "error" in result["task_instances"]
        assert "summary" not in result
        assert result["run_info"]["state"] == "failed"
    else:
        assert "error" in result["failed_tasks_error"]
        assert "failed_tasks" not in result
        assert result["dag_run"]["state"] == "failed"


@pytest.mark.parametrize("interface", ["mcp", "cli"])
@pytest.mark.parametrize("command", ["diagnose", "trigger-wait"])
def test_overlapping_pages_are_reported(adapter, mocker, interface, command):
    """An updated instance repeated on page two must not hide an omitted failure."""
    tasks = [{"task_id": "mapped", "map_index": i, "state": "success"} for i in range(101)]
    tasks[0]["state"] = "running"
    tasks[100]["state"] = "failed"
    pages = mocker.patch.object(
        adapter,
        "get_task_instances",
        side_effect=[
            {"task_instances": tasks[:100], "total_entries": len(tasks)},
            {
                "task_instances": [{**tasks[0], "state": "success"}],
                "total_entries": len(tasks),
            },
        ],
    )

    result = invoke(interface, command)

    assert [call.kwargs["offset"] for call in pages.call_args_list] == [0, 100]
    if command == "diagnose":
        assert "duplicate" in result["task_instances"]["error"]
        assert "summary" not in result
        assert result["run_info"]["state"] == "failed"
    else:
        assert "duplicate" in result["failed_tasks_error"]["error"]
        assert "failed_tasks" not in result
        assert result["dag_run"]["state"] == "failed"


@pytest.mark.parametrize("interface", ["mcp", "cli"])
def test_small_diagnosis_preserves_full_details(adapter, mocker, interface):
    tasks = [{"task_id": "only_task", "map_index": -1, "state": "failed", "duration": 12}]
    mocker.patch.object(
        adapter, "get_task_instances", return_value={"task_instances": tasks, "total_entries": 1}
    )

    result = invoke(interface, "diagnose")

    assert result["task_instances"] == tasks
    assert result["task_instances_returned"] == 1
    assert result["task_instances_truncated"] is False
    assert result["summary"]["failed_tasks"][0]["map_index"] == -1
