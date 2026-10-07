"""Gate 1 and Gate 3 tests for validate_dag.py.

Gate 1 (ast.parse + optional ruff) and Gate 3 (structural asserts against a
stubbed DagBag) need no airflow. The airflow-dependent path (Gate 2 / real
DagBag) is import-guarded and skips cleanly when airflow is absent."""

import pytest

import validate_dag


# --- Gate 1: python import + lint ------------------------------------------


def _project(tmp_path, files):
    (tmp_path / "dags").mkdir()
    (tmp_path / "include").mkdir()
    for rel, body in files.items():
        (tmp_path / rel).write_text(body)
    return str(tmp_path)


def test_gate1_pass(tmp_path):
    proj = _project(tmp_path, {"dags/good.py": "x = 1 + 1\n"})
    assert validate_dag.gate1_import_lint(proj)["status"] == "pass"


def test_gate1_syntax_error_fails(tmp_path):
    proj = _project(tmp_path, {"dags/bad.py": "def broken(:\n"})
    r = validate_dag.gate1_import_lint(proj)
    assert r["status"] == "fail"
    assert r["details"]["parse_errors"]


def test_gate1_no_files_fails(tmp_path):
    (tmp_path / "dags").mkdir()
    assert validate_dag.gate1_import_lint(str(tmp_path))["status"] == "fail"


# --- Gate 3: structural asserts against a stubbed DagBag --------------------


class _Asset:
    def __init__(self, uri):
        self.uri = uri


class _Task:
    def __init__(self, task_id, downstream=(), outlets=()):
        self.task_id = task_id
        self.downstream_task_ids = set(downstream)
        self.outlets = list(outlets)


class _Dag:
    def __init__(self, tasks, schedule="@daily"):
        self.tasks = tasks
        self.schedule = schedule


class _DagBag:
    def __init__(self, dags):
        self._dags = dags

    def get_dag(self, dag_id):
        return self._dags.get(dag_id)


def _dag():
    return _Dag(
        [_Task("extract", ["load"]), _Task("load", outlets=[_Asset("s3://out")])]
    )


def test_gate3_structure_pass():
    manifest = {
        "units": {
            "asset:orders": {
                "dag_id": "orders",
                "task_count": 2,
                "edges": [["extract", "load"]],
                "schedule": "@daily",
                "asset_outlets": ["s3://out"],
            }
        }
    }
    r = validate_dag.gate3_structure(_DagBag({"orders": _dag()}), manifest, None)
    assert r["status"] == "pass"
    assert r["details"]["runtime_attribute_probe"]["schedule_attr"] == "schedule"


def test_gate3_structure_mismatch_fails():
    manifest = {
        "units": {
            "asset:orders": {
                "dag_id": "orders",
                "task_count": 99,
                "edges": [["a", "b"]],
            }
        }
    }
    r = validate_dag.gate3_structure(_DagBag({"orders": _dag()}), manifest, None)
    assert r["status"] == "fail"


def test_gate3_all_missing_dag_id_is_loud_fail():
    manifest = {"units": {"asset:a": {"dag_id": None}, "op:b": {"dag_id": None}}}
    r = validate_dag.gate3_structure(_DagBag({}), manifest, None)
    assert r["status"] == "fail"
    assert r["details"]["skipped_no_dag_id_count"] == 2


def test_gate3_target_none_skipped_silently():
    manifest = {"units": {"io:x": {"target": "none"}}}
    r = validate_dag.gate3_structure(_DagBag({}), manifest, None)
    # a deliberately DAG-less unit is not counted as a planning gap
    assert r["details"]["skipped_no_dag_id_count"] == 0
    assert r["status"] == "skip"


def test_gate3_asset_schedule_and_timetable_type():
    class CronPartitionTimetable:  # class name is what timetable_type matches
        def __repr__(self):
            return "CronPartitionTimetable('15 * * * *')"

    dag = _Dag([_Task("a")], schedule="[Asset(uri='s3://raw')]")
    dag.timetable = CronPartitionTimetable()
    manifest = {
        "units": {
            "asset:daily": {
                "dag_id": "daily",
                "asset_schedule": ["s3://raw"],
                "timetable_type": "CronPartitionTimetable",
            }
        }
    }
    r = validate_dag.gate3_structure(_DagBag({"daily": dag}), manifest, None)
    checks = r["details"]["units"][0]["checks"]
    assert checks["asset_schedule"]["ok"] and checks["timetable_type"]["ok"]


# --- Gate 2 / real DagBag: needs airflow, skip cleanly without it ----------


def test_gate2_real_dagbag_requires_airflow(tmp_path):
    pytest.importorskip("airflow")
    (tmp_path / "dags").mkdir()
    (tmp_path / "dags" / "d.py").write_text("x = 1\n")
    dagbag, import_path, err = validate_dag.load_dagbag(str(tmp_path))
    r = validate_dag.gate2_dagbag(str(tmp_path), dagbag, import_path, err)
    assert r["gate"] == 2 and r["status"] in ("pass", "fail", "skip")


# --- Gate 2: which Astro CLI parse check runs --------------------------------


class _Proc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_astro(monkeypatch, local_help_rc, parse_rc=0):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd == ["astro", "local", "af", "--help"]:
            return _Proc(local_help_rc)
        return _Proc(parse_rc, stdout="parsed")

    monkeypatch.setattr(validate_dag.shutil, "which", lambda name: "/usr/bin/astro")
    monkeypatch.setattr(validate_dag.subprocess, "run", run)
    return calls


@pytest.mark.parametrize(
    ("local_help_rc", "expected"),
    [(0, ["astro", "local", "check"]), (1, ["astro", "dev", "parse"])],
)
def test_gate2_runs_the_parse_check_of_the_cli_on_path(
    monkeypatch, tmp_path, local_help_rc, expected
):
    calls = _fake_astro(monkeypatch, local_help_rc)
    r = validate_dag.gate2_dagbag(str(tmp_path), None, None, "no airflow")
    assert calls[-1] == expected
    assert r["details"]["astro_parse_command"] == " ".join(expected)
    assert r["status"] == "pass"


def test_gate2_parse_failure_fails_the_gate(monkeypatch, tmp_path):
    _fake_astro(monkeypatch, 0, parse_rc=1)
    r = validate_dag.gate2_dagbag(str(tmp_path), None, None, "no airflow")
    assert r["status"] == "fail"
    assert r["details"]["astro_parse_returncode"] == 1


def test_gate2_no_verdict_from_astro_local_check_does_not_fail(monkeypatch, tmp_path):
    _fake_astro(monkeypatch, 0, parse_rc=2)
    r = validate_dag.gate2_dagbag(str(tmp_path), None, None, "no airflow")
    assert r["status"] == "skip"
    assert "no verdict" in r["details"]["astro_parse"]


def test_gate2_exit_2_from_astro_dev_parse_still_fails(monkeypatch, tmp_path):
    _fake_astro(monkeypatch, 1, parse_rc=2)
    r = validate_dag.gate2_dagbag(str(tmp_path), None, None, "no airflow")
    assert r["status"] == "fail"


def test_gate2_skips_the_cli_when_the_probe_times_out(monkeypatch, tmp_path):
    def run(cmd, **kwargs):
        raise validate_dag.subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(validate_dag.shutil, "which", lambda name: "/usr/bin/astro")
    monkeypatch.setattr(validate_dag.subprocess, "run", run)
    r = validate_dag.gate2_dagbag(str(tmp_path), None, None, "no airflow")
    assert r["status"] == "skip"
    assert "version probe" in r["details"]["astro_parse"]
