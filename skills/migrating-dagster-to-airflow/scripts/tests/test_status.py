"""State-machine tests for status.py, driven through main(argv) on a temp manifest."""

import json

import pytest

import status


def _write(tmp_path, units):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps({"units": units}))
    return str(p)


def _state(path, unit_id):
    units = json.loads(open(path).read())["units"]
    return status.unit_state(units[unit_id])


def _units():
    return {
        "asset:a": {"kind": "asset", "classification": "MECH", "status": "pending"},
        "op:b": {"kind": "op", "classification": "MECH", "status": "pending"},
        "op:c": {"kind": "op", "classification": "MECH", "status": "pending"},
        "res:d": {"kind": "resource", "target": "none", "status": "pending"},
    }


def test_advance_single(tmp_path):
    p = _write(tmp_path, _units())
    assert (
        status.main(["--manifest", p, "advance", "asset:a", "--evidence", "gate1.json"])
        == 0
    )
    assert _state(p, "asset:a") == "translate"


def test_advance_missing_unit(tmp_path):
    p = _write(tmp_path, _units())
    assert status.main(["--manifest", p, "advance", "nope:x", "--evidence", "e"]) == 2


def test_advance_requires_evidence(tmp_path):
    p = _write(tmp_path, _units())
    with pytest.raises(SystemExit):  # argparse: --evidence is required
        status.main(["--manifest", p, "advance", "asset:a"])


def test_advance_already_complete_is_error(tmp_path):
    units = _units()
    units["asset:a"]["status"] = {"state": "complete"}
    p = _write(tmp_path, units)
    assert status.main(["--manifest", p, "advance", "asset:a", "--evidence", "e"]) == 1


def test_target_none_advances_straight_to_complete(tmp_path):
    p = _write(tmp_path, _units())
    assert (
        status.main(
            ["--manifest", p, "advance", "res:d", "--evidence", "lowered to include/"]
        )
        == 0
    )
    assert _state(p, "res:d") == "complete"


def test_defer_and_reason_required(tmp_path):
    p = _write(tmp_path, _units())
    with pytest.raises(SystemExit):
        status.main(["--manifest", p, "defer", "op:b"])
    assert status.main(["--manifest", p, "defer", "op:b", "--reason", "blocked"]) == 0
    assert _state(p, "op:b") == "deferred"


def test_reopen(tmp_path):
    units = _units()
    units["asset:a"]["status"] = {"state": "complete"}
    p = _write(tmp_path, units)
    assert (
        status.main(["--manifest", p, "reopen", "asset:a", "--reason", "rework"]) == 0
    )
    assert _state(p, "asset:a") == "translate"


def test_bulk_advance_where(tmp_path):
    p = _write(tmp_path, _units())
    rc = status.main(
        [
            "--manifest",
            p,
            "advance",
            "--where",
            "kind=op",
            "--from-state",
            "pending",
            "--evidence",
            "batch",
        ]
    )
    assert rc == 0
    assert _state(p, "op:b") == "translate"
    assert _state(p, "op:c") == "translate"
    assert _state(p, "asset:a") == "pending"  # not matched


def test_bulk_dry_run_writes_nothing(tmp_path):
    p = _write(tmp_path, _units())
    rc = status.main(
        [
            "--manifest",
            p,
            "advance",
            "--where",
            "kind=op",
            "--evidence",
            "e",
            "--dry-run",
        ]
    )
    assert rc == 0
    assert _state(p, "op:b") == "pending"


def test_bulk_and_single_are_mutually_exclusive(tmp_path):
    p = _write(tmp_path, _units())
    assert (
        status.main(
            [
                "--manifest",
                p,
                "advance",
                "op:b",
                "--where",
                "kind=op",
                "--evidence",
                "e",
            ]
        )
        == 2
    )


def test_summary_exit_codes(tmp_path):
    # all pending -> in flight -> nonzero
    p = _write(tmp_path, _units())
    assert status.main(["--manifest", p, "summary"]) == 1
    # all dispositioned -> zero
    done = {u: {"status": {"state": "complete"}} for u in _units()}
    p2 = _write(tmp_path, done)
    assert status.main(["--manifest", p2, "summary"]) == 0


def test_summary_silent_omission_nonzero(tmp_path):
    p = _write(tmp_path, {"weird:x": {"status": {"state": "banana"}}})
    assert status.main(["--manifest", p, "summary"]) == 1


def test_summary_surfaces_static_only_note(tmp_path, capsys):
    manifest = {
        "units": {"asset:a": {"status": {"state": "complete"}}},
        "runtime_error": "dagster not importable in this interpreter",
    }
    rc = status.cmd_summary(manifest)
    out = capsys.readouterr().out
    assert rc == 0
    assert "STATIC-ONLY" in out
