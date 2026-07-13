#!/usr/bin/env python3
"""Run validation gates 1 to 3 against a generated Astro project.

Implements the cheap-to-expensive ladder from reference/validation.md:

  Gate 1  python import + lint   ast.parse over dags/ and include/, then ruff
  Gate 2  DagBag import check    load the project with airflow's DagBag, and/or
                                 shell out to `astro dev parse`
  Gate 3  structural asserts     compare each DAG against the inventory manifest
                                 (task count, dependency edges, schedule string,
                                 asset outlets)

The manifest is the JSON produced by scripts/inventory.py. Expected shape:

  {
    "units": {
      "<unit_id>": {
        "dag_id": "orders_daily",
        "task_count": 3,
        "edges": [["extract", "transform"], ["transform", "load"]],
        "schedule": "@daily",
        "asset_schedule": ["s3://warehouse/raw_orders"],
        "timetable_type": "CronPartitionTimetable",
        "asset_outlets": ["s3://warehouse/orders"],
        "target": "none",            # optional: lowers to include/ or platform
        "source_edges": [ ... ],     # written by inventory.py, ignored here
        "status": { ... }            # managed by status.py, ignored here
      }
    }
  }

Edge-key contract (G1): the SCANNER writes `source_edges` (dependency edges
found in Dagster source). The PLANNER writes the DISTINCT `edges` key that
Gate 3 asserts (target task edges). They never share a key. Every target
expectation below is optional and only asserted when present:
  edges           target task edges (upstream_task_id, downstream_task_id)
  schedule        cron string, for cron DAGs
  asset_schedule  asset uris/names that must appear in the DAG's asset condition
  timetable_type  timetable class-name substring (e.g. CronPartitionTimetable)
  asset_outlets   asset uris produced by the DAG's tasks
A unit with target:"none" is skipped silently (not a planning gap).

Two DAG attribute spellings are marked unverified in validation.md (whether the
airflow.sdk DAG exposes `schedule_interval` vs `timetable` vs `schedule`, and
whether task edges live on `downstream_task_ids`). Gate 3 probes both defensively
and reports which spelling the runtime actually has, so the first real run settles
the question.

Usage:
  validate_dag.py <astro_project> --manifest manifest.json [--gate N] [--dag-id X]
                  [--out report.json]

Exit code: 0 if every requested gate passed (or was cleanly skipped for a stated
reason). Otherwise the number of the first gate that FAILED (1, 2, or 3).
Machine-readable JSON goes to stdout (or --out); a human summary goes to stderr.
"""

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys


def log(msg):
    """Human-facing progress line, kept off stdout so JSON stays clean."""
    print(msg, file=sys.stderr)


def python_files(*dirs):
    """Every .py file under the given directories, sorted for stable output."""
    found = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for name in files:
                if name.endswith(".py"):
                    found.append(os.path.join(root, name))
    return sorted(found)


def gate1_import_lint(project):
    """Gate 1: files parse as Python and pass ruff (ruff optional)."""
    dags_dir = os.path.join(project, "dags")
    include_dir = os.path.join(project, "include")
    files = python_files(dags_dir, include_dir)

    result = {"gate": 1, "name": "import+lint", "status": "pass", "details": {}}

    if not files:
        result["status"] = "fail"
        result["details"]["error"] = "no python files found under dags/ or include/"
        return result

    # ast.parse: catches syntax errors without importing anything.
    parse_errors = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                ast.parse(fh.read(), filename=path)
        except SyntaxError as exc:
            parse_errors.append({"file": path, "error": str(exc)})
    result["details"]["files_checked"] = len(files)
    result["details"]["parse_errors"] = parse_errors
    if parse_errors:
        result["status"] = "fail"
        return result

    # ruff: tolerate a missing binary rather than failing the gate on it.
    if shutil.which("ruff") is None:
        result["details"]["ruff"] = "skipped: ruff not on PATH"
        return result

    proc = subprocess.run(
        ["ruff", "check", dags_dir, include_dir],
        capture_output=True,
        text=True,
    )
    result["details"]["ruff_returncode"] = proc.returncode
    result["details"]["ruff_output"] = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        result["status"] = "fail"
    return result


def load_dagbag(project):
    """Load the project with airflow's DagBag, in this interpreter.

    Returns (dagbag, import_path, error). `dagbag` is None when airflow is not
    importable here, in which case the caller falls back to `astro dev parse`.
    Run this script with the Astro project's own python so airflow is present.
    """
    dags_dir = os.path.join(project, "dags")

    # Put the Astro project root on sys.path so DAGs doing `from include...`
    # (the skill's own convention) import, matching what astro's container does.
    # Without this the in-process DagBag disagrees with `astro dev parse` (found in testing).
    project_root = os.path.abspath(project)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    DagBag = None
    import_path = None
    # Airflow 3.x path is airflow.dag_processing.dagbag (verified). The 2.x
    # airflow.models path is the compatibility fallback.
    for candidate in (
        "airflow.dag_processing.dagbag",
        "airflow.models.dagbag",
    ):
        try:
            module = __import__(candidate, fromlist=["DagBag"])
            DagBag = getattr(module, "DagBag")
            import_path = candidate
            break
        except Exception:
            continue

    if DagBag is None:
        return None, None, "airflow DagBag not importable in this interpreter"

    try:
        dagbag = DagBag(dag_folder=dags_dir, include_examples=False)
    except TypeError:
        # Older/newer signatures may not accept include_examples.
        dagbag = DagBag(dag_folder=dags_dir)
    return dagbag, import_path, None


def gate2_dagbag(project, dagbag, import_path, load_error):
    """Gate 2: the project imports cleanly (DagBag and/or `astro dev parse`)."""
    result = {"gate": 2, "name": "dagbag-import", "status": "pass", "details": {}}
    checks_ran = 0

    # In-process DagBag import.
    if dagbag is not None:
        checks_ran += 1
        errors = dict(getattr(dagbag, "import_errors", {}) or {})
        result["details"]["dagbag_import_path"] = import_path
        result["details"]["dagbag_import_errors"] = errors
        result["details"]["dag_ids"] = sorted(getattr(dagbag, "dag_ids", []) or [])
        if errors:
            result["status"] = "fail"
    else:
        result["details"]["dagbag"] = "skipped: " + (load_error or "unavailable")

    # `astro dev parse`, if the CLI is installed.
    if shutil.which("astro") is not None:
        checks_ran += 1
        proc = subprocess.run(
            ["astro", "dev", "parse"],
            cwd=project,
            capture_output=True,
            text=True,
        )
        result["details"]["astro_parse_returncode"] = proc.returncode
        result["details"]["astro_parse_output"] = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            result["status"] = "fail"
    else:
        result["details"]["astro_parse"] = "skipped: astro CLI not on PATH"

    if checks_ran == 0:
        result["status"] = "skip"
        result["details"]["error"] = (
            "neither in-process DagBag nor astro CLI available; "
            "run with the Astro project python or install the astro CLI"
        )
    return result


def probe_schedule(dag):
    """Return (attribute_name, value) for whichever schedule spelling exists."""
    # Probe order settled by testing (Airflow 3.3): `schedule` exists on sdk
    # DAGs and returns the original string ("@daily"); `timetable` exists too but
    # str() of it is a repr that never matches a manifest schedule. `summary` does
    # not exist on airflow.sdk timetables.
    for attr in ("schedule", "schedule_interval", "timetable"):
        if hasattr(dag, attr):
            return attr, getattr(dag, attr)
    return None, None


def probe_downstream(task):
    """Return (attribute_name, set_of_ids) for the task's downstream edges."""
    for attr in ("downstream_task_ids", "downstream_list"):
        if hasattr(task, attr):
            value = getattr(task, attr)
            if attr == "downstream_list":
                return attr, {t.task_id for t in value}
            return attr, set(value)
    return None, set()


def probe_outlets(task):
    """Return the set of outlet URIs for a task, tolerating missing outlets."""
    outlets = getattr(task, "outlets", None) or []
    uris = set()
    for a in outlets:
        uri = getattr(a, "uri", None)
        if uri is not None:
            uris.add(uri)
    return uris


def gate3_structure(dagbag, manifest, dag_id_filter):
    """Gate 3: each DAG's shape matches its manifest record."""
    result = {"gate": 3, "name": "structure", "status": "pass", "details": {}}

    if dagbag is None:
        result["status"] = "skip"
        result["details"]["error"] = (
            "gate 3 needs an in-process DagBag; airflow not importable"
        )
        return result

    units = manifest.get("units", {})
    unit_reports = []
    probe = {"schedule_attr": None, "downstream_attr": None}
    any_fail = False
    considered = 0  # units not filtered out by --dag-id
    skipped_no_dag_id = []  # considered units with no planned dag_id yet

    for unit_id, spec in units.items():
        dag_id = spec.get("dag_id")
        if dag_id_filter and dag_id != dag_id_filter:
            continue

        # Deliberately DAG-less units (target:"none") lower into another unit or
        # the platform layer (IO-manager helpers, external-asset decls, the
        # Definitions object). They are dispositioned in status.py, not here, so
        # skip them SILENTLY: they are not a planning gap and must not appear in
        # the loud skip warning (G13).
        if spec.get("target") == "none":
            continue

        considered += 1

        # Units without a dag_id have not been planned into a target DAG yet.
        # inventory.py documents them as skipped until planning fills them in;
        # we skip but count them LOUDLY (G6): silently no-op'ing every unit let
        # a run claim "gate 3 green" while gate 3 checked nothing.
        if not dag_id:
            skipped_no_dag_id.append(unit_id)
            continue

        ur = {"unit_id": unit_id, "dag_id": dag_id, "status": "pass", "checks": {}}
        dags_map = getattr(dagbag, "dags", None) or {}
        dag = dags_map.get(dag_id)
        if dag is None:
            try:
                dag = dagbag.get_dag(dag_id)
            except Exception:
                dag = None
        if dag is None:
            ur["status"] = "fail"
            ur["checks"]["dag_present"] = False
            unit_reports.append(ur)
            any_fail = True
            continue

        tasks = list(getattr(dag, "tasks", []))

        # Task count.
        expected_count = spec.get("task_count")
        if expected_count is not None:
            ok = len(tasks) == expected_count
            ur["checks"]["task_count"] = {
                "expected": expected_count,
                "actual": len(tasks),
                "ok": ok,
            }
            ur["status"] = ur["status"] if ok else "fail"

        # Dependency edges.
        expected_edges = spec.get("edges")
        if expected_edges is not None:
            actual_edges = set()
            for t in tasks:
                attr, downs = probe_downstream(t)
                probe["downstream_attr"] = probe["downstream_attr"] or attr
                for d in downs:
                    actual_edges.add((t.task_id, d))
            want = {tuple(e) for e in expected_edges}
            ok = actual_edges == want
            ur["checks"]["edges"] = {
                "ok": ok,
                "missing": sorted("->".join(e) for e in (want - actual_edges)),
                "unexpected": sorted("->".join(e) for e in (actual_edges - want)),
            }
            ur["status"] = ur["status"] if ok else "fail"

        # Schedule string, for CRON forms. The attribute spelling is unverified
        # upstream, so we record which one the runtime exposed.
        expected_schedule = spec.get("schedule")
        if expected_schedule is not None:
            attr, value = probe_schedule(dag)
            probe["schedule_attr"] = probe["schedule_attr"] or attr
            actual = str(value)
            ok = actual == str(expected_schedule)
            ur["checks"]["schedule"] = {
                "expected": expected_schedule,
                "actual": actual,
                "attribute": attr,
                "ok": ok,
            }
            ur["status"] = ur["status"] if ok else "fail"

        # Asset-aware schedule (the flagship lowering). Asset lists and partition
        # timetables render as Asset(...) / memory-address reprs that a plain
        # string compare cannot assert (G4), so we check each expected asset
        # uri/name is present in the rendered schedule + timetable repr.
        expected_asset_sched = spec.get("asset_schedule")
        if expected_asset_sched is not None:
            sched_repr = "{0} {1}".format(
                getattr(dag, "schedule", ""), getattr(dag, "timetable", "")
            )
            missing = [a for a in expected_asset_sched if str(a) not in sched_repr]
            ok = not missing
            ur["checks"]["asset_schedule"] = {
                "ok": ok,
                "missing": missing,
                "schedule_repr": sched_repr[:300],
            }
            ur["status"] = ur["status"] if ok else "fail"

        # Timetable class (e.g. "CronPartitionTimetable"): substring match on the
        # timetable type name, the assertable half of a partitioned schedule.
        expected_tt = spec.get("timetable_type")
        if expected_tt is not None:
            tt_name = type(getattr(dag, "timetable", None)).__name__
            ok = expected_tt in tt_name
            ur["checks"]["timetable_type"] = {
                "expected": expected_tt,
                "actual": tt_name,
                "ok": ok,
            }
            ur["status"] = ur["status"] if ok else "fail"

        # Asset outlets across all tasks.
        expected_outlets = spec.get("asset_outlets")
        if expected_outlets is not None:
            actual_outlets = set()
            for t in tasks:
                actual_outlets |= probe_outlets(t)
            want = set(expected_outlets)
            ok = actual_outlets == want
            ur["checks"]["asset_outlets"] = {
                "ok": ok,
                "missing": sorted(want - actual_outlets),
                "unexpected": sorted(actual_outlets - want),
            }
            ur["status"] = ur["status"] if ok else "fail"

        if ur["status"] == "fail":
            any_fail = True
        unit_reports.append(ur)

    result["details"]["units"] = unit_reports
    result["details"]["runtime_attribute_probe"] = probe
    result["details"]["skipped_no_dag_id"] = skipped_no_dag_id
    result["details"]["skipped_no_dag_id_count"] = len(skipped_no_dag_id)
    if considered == 0:
        # Nothing matched the --dag-id filter (or the manifest has no units).
        result["status"] = "skip"
        result["details"]["error"] = "no matching units in manifest"
    elif not unit_reports:
        # Units exist but every one lacks a dag_id: gate 3 was requested yet
        # verified nothing. That is a failure, not a silent pass (G6).
        result["status"] = "fail"
        result["details"]["error"] = (
            "all {0} considered unit(s) skipped: no dag_id "
            "(plan phase incomplete)".format(len(skipped_no_dag_id))
        )
    elif any_fail:
        result["status"] = "fail"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run validation gates 1 to 3.")
    parser.add_argument("astro_project", help="path to the generated Astro project")
    parser.add_argument(
        "--manifest", help="inventory manifest JSON (required for gate 3)"
    )
    parser.add_argument(
        "--gate",
        type=int,
        choices=[1, 2, 3],
        help="run only this gate (default: 1 through 3)",
    )
    parser.add_argument("--dag-id", help="restrict gate 3 to a single dag_id")
    parser.add_argument("--out", help="write JSON report here instead of stdout")
    args = parser.parse_args(argv)

    project = args.astro_project
    if not os.path.isdir(project):
        log("error: astro project not found: " + project)
        return 2

    gates_to_run = [args.gate] if args.gate else [1, 2, 3]
    manifest = {}
    if 3 in gates_to_run:
        if not args.manifest:
            log("error: gate 3 requires --manifest")
            return 2
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)

    report = {"project": project, "gates": []}
    first_failed = 0

    # DagBag is loaded once and shared by gates 2 and 3.
    dagbag = import_path = load_error = None
    if any(g in gates_to_run for g in (2, 3)):
        dagbag, import_path, load_error = load_dagbag(project)

    for gate in gates_to_run:
        if gate == 1:
            r = gate1_import_lint(project)
        elif gate == 2:
            r = gate2_dagbag(project, dagbag, import_path, load_error)
        else:
            r = gate3_structure(dagbag, manifest, args.dag_id)
        report["gates"].append(r)
        log("gate {0} ({1}): {2}".format(r["gate"], r["name"], r["status"].upper()))
        if gate == 3:
            n = r["details"].get("skipped_no_dag_id_count", 0)
            if n:
                log(
                    "gate3: {0} unit(s) skipped (no dag_id; plan phase incomplete)".format(
                        n
                    )
                )
        if r["status"] == "fail" and first_failed == 0:
            first_failed = gate

    report["result"] = "fail" if first_failed else "pass"
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        log("wrote report to " + args.out)
    else:
        print(text)

    return first_failed


if __name__ == "__main__":
    sys.exit(main())
