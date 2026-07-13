#!/usr/bin/env python3
"""Per-unit migration state machine, backed by the inventory manifest.

Tracks where each migrated unit sits on the validation ladder from
reference/validation.md. State lives in the manifest under each unit's
"status" key, so inventory.py, validate_dag.py, and this script share one file.

States (exactly these, in ladder order):

  pending        not started
  translate      lowering Dagster to Airflow in progress
  fix-import     making it pass gate 2 (DagBag import)
  fix-lint       making it pass gate 1 (ruff) and gate 3 (structure)
  fix-tests      making it pass gate 4 (execution)
  verify-parity  making it pass gates 5 and 6 (data parity, idempotency)
  complete       every gate green
  deferred       cannot pass after the retry cap; REQUIRES a reason

Legal transitions: forward one step along the ladder order above, and into
`deferred` from any non-complete state. A deferred unit may be reopened by
advancing it, which moves it back to `translate`.

Advancing requires --evidence: a path or command-output reference that names the
gate proof (for example "reports/orders_daily.gate3.json" or the parity checksum
line). Deferring requires --reason.

A unit the planner marked target:"none" (it lowers into another unit or the
platform layer, so it has no DAG and no gate ladder) is dispositioned by a single
`advance` straight to complete, with --evidence naming where it went.

Manifest shape consumed and written:

  { "units": { "<unit_id>": { ..., "status": {
        "state": "translate",
        "reason": null,
        "history": [ {"to": "translate", "evidence": "..."} ]
  } } } }

Commands (advance/defer/reopen take a single <unit-id> OR a --where/--from-state
filter for bulk; the two forms are mutually exclusive):
  status.py [--manifest M] show [--by-state]
  status.py [--manifest M] advance <unit-id> --evidence "..."
  status.py [--manifest M] advance --where kind=op [--where classification=MECH]
            [--from-state pending] --evidence "..." [--dry-run]
  status.py [--manifest M] defer  (<unit-id> | --where KEY=VALUE ...) --reason "..." [--dry-run]
  status.py [--manifest M] reopen (<unit-id> | --where KEY=VALUE ...) --reason "..." [--dry-run]
  status.py [--manifest M] summary

Bulk semantics: every matched unit gets the transition under the normal legality
rules; illegal transitions are reported per-unit and skipped, not fatal. --where
KEY=VALUE matches a top-level record field (kind, classification, ...); repeatable
and ANDed. --from-state matches the unit's current state. --dry-run prints the
match list and planned transitions without writing. Single-unit mode is unchanged:
a missing unit exits 2, an illegal move exits 1.

Stdlib only.
"""

import argparse
import json
import os
import sys

DEFAULT_MANIFEST = os.path.join("include", "inventory", "manifest.json")

# Ladder order. `deferred` sits outside the linear chain.
LADDER = [
    "pending",
    "translate",
    "fix-import",
    "fix-lint",
    "fix-tests",
    "verify-parity",
    "complete",
]
ALL_STATES = LADDER + ["deferred"]

# States that count as a final disposition for the completeness check.
TERMINAL = {"complete", "deferred"}


def load_manifest(path):
    if not os.path.isfile(path):
        sys.stderr.write("error: manifest not found: " + path + "\n")
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_manifest(path, manifest):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


def unit_state(unit):
    """Current state of a unit, defaulting to pending when untracked."""
    status = unit.get("status")
    if not isinstance(status, dict):
        return "pending"
    return status.get("state", "pending")


def get_units(manifest):
    units = manifest.get("units")
    if not isinstance(units, dict):
        sys.stderr.write("error: manifest has no 'units' object\n")
        sys.exit(2)
    return units


def cmd_show(manifest, by_state):
    units = get_units(manifest)
    if by_state:
        buckets = {s: [] for s in ALL_STATES}
        for unit_id, unit in units.items():
            buckets.setdefault(unit_state(unit), []).append(unit_id)
        for state in ALL_STATES:
            ids = sorted(buckets.get(state, []))
            print("{0:<14} {1}".format(state, len(ids)))
            for unit_id in ids:
                print("    " + unit_id)
    else:
        for unit_id in sorted(units):
            unit = units[unit_id]
            state = unit_state(unit)
            reason = ""
            status = unit.get("status")
            if isinstance(status, dict) and status.get("reason"):
                reason = "  (" + status["reason"] + ")"
            print("{0:<40} {1}{2}".format(unit_id, state, reason))
    return 0


# Transition planners: given a unit, return (target_state, current_state, error).
# error is a human phrase when the transition is illegal (target is then None).


def _plan_advance(unit):
    current = unit_state(unit)
    if current == "complete":
        return None, current, "already complete"
    if unit.get("target") == "none":
        # Deliberately DAG-less units (lower into another unit or the platform
        # layer) have no gate ladder to walk. Advance dispositions them in one
        # step; the required --evidence names where the unit went (G13).
        return "complete", current, None
    if current == "deferred":
        return "translate", current, None  # reopen a deferred unit at the chain start
    return LADDER[LADDER.index(current) + 1], current, None


def _plan_defer(unit):
    current = unit_state(unit)
    if current == "complete":
        return None, current, "cannot defer a complete unit"
    return "deferred", current, None


def _plan_reopen(unit):
    current = unit_state(unit)
    if current not in ("complete", "deferred"):
        return None, current, "reopen only applies to complete or deferred units"
    return "translate", current, None


_PLANNERS = {"advance": _plan_advance, "defer": _plan_defer, "reopen": _plan_reopen}


def _commit(unit, target, current, op, evidence, reason):
    """Write the transition onto a unit's status (no save)."""
    status = unit.get("status")
    if not isinstance(status, dict):  # inventory.py emits status as a plain string
        status = unit["status"] = {}
    status["state"] = target
    status["reason"] = None if op == "advance" else reason
    entry = {"to": target}
    if op == "advance":
        entry["evidence"] = evidence
    elif op == "defer":
        entry["reason"] = reason
    else:  # reopen
        entry["reopened_from"] = current
        entry["reason"] = reason
    status.setdefault("history", []).append(entry)


def _single_line(op, uid, current, target, evidence, reason):
    """The one-line result for single-unit mode, unchanged from before."""
    if op == "advance":
        return "{0}: {1} -> {2}  ({3})".format(uid, current, target, evidence)
    if op == "defer":
        return "{0}: {1} -> deferred  ({2})".format(uid, current, reason)
    return "{0}: {1} -> translate (reopened)  ({2})".format(uid, current, reason)


def _parse_where(where_args):
    pairs = []
    for w in where_args or []:
        if "=" not in w:
            sys.stderr.write("error: --where expects key=value, got: " + w + "\n")
            sys.exit(2)
        k, v = w.split("=", 1)
        pairs.append((k.strip(), v.strip()))
    return pairs


def _matches(unit, where, from_state):
    for k, v in where:
        if str(unit.get(k)) != v:
            return False
    if from_state is not None and unit_state(unit) != from_state:
        return False
    return True


def _selected(units, where, from_state):
    return [
        (uid, units[uid])
        for uid in sorted(units)
        if _matches(units[uid], where, from_state)
    ]


def _filter_desc(where, from_state):
    parts = ["{0}={1}".format(k, v) for k, v in where]
    if from_state is not None:
        parts.append("from-state=" + from_state)
    return ", ".join(parts) or "(no filter)"


def run_transition(manifest, path, op, args):
    """Apply advance/defer/reopen to one unit (positional) or many (--where).

    Single-unit mode is unchanged: missing unit -> exit 2, illegal move -> exit 1.
    Bulk mode applies to every matched unit under the same legality rules;
    illegal transitions are reported per-unit and skipped, not fatal.
    """
    units = get_units(manifest)

    reason = getattr(args, "reason", None)
    if op in ("defer", "reopen"):
        if not reason or not reason.strip():
            sys.stderr.write("error: " + op + " requires a non-empty --reason\n")
            return 2
        reason = reason.strip()
    evidence = getattr(args, "evidence", None)

    where = _parse_where(args.where)
    from_state = args.from_state

    if args.unit_id is not None:
        if where or from_state is not None:
            sys.stderr.write(
                "error: pass a unit id OR --where/--from-state, not both\n"
            )
            return 2
        if args.unit_id not in units:
            sys.stderr.write("error: no such unit: " + args.unit_id + "\n")
            return 2
        targets, single = [(args.unit_id, units[args.unit_id])], True
    else:
        if not where and from_state is None:
            sys.stderr.write(
                "error: bulk mode needs at least one --where or --from-state filter\n"
            )
            return 2
        targets, single = _selected(units, where, from_state), False
        if not targets:
            print("no units matched " + _filter_desc(where, from_state))
            return 0

    planner = _PLANNERS[op]
    applied = skipped = 0
    for uid, unit in targets:
        target, current, err = planner(unit)
        if err is not None:
            if single:
                sys.stderr.write(
                    "error: cannot {0} {1}: {2} (state={3})\n".format(
                        op, uid, err, current
                    )
                )
                return 1
            print("  skip  {0}: {1} ({2})".format(uid, err, current))
            skipped += 1
            continue
        if args.dry_run:
            print("  would-{0}  {1}: {2} -> {3}".format(op, uid, current, target))
        else:
            _commit(unit, target, current, op, evidence, reason)
            print(
                _single_line(op, uid, current, target, evidence, reason)
                if single
                else "  {0}: {1} -> {2}".format(uid, current, target)
            )
        applied += 1

    if not args.dry_run and applied:
        save_manifest(path, manifest)
    if not single:
        verb = "would apply" if args.dry_run else "applied"
        tail = " (dry-run, nothing written)" if args.dry_run else ""
        print("{0}: {1} {2}, {3} skipped{4}".format(op, applied, verb, skipped, tail))
    return 0


def cmd_summary(manifest):
    """Counts per state plus the completeness gate.

    Silent omission = a unit whose recorded state is not one of the known
    states (or is missing entirely and cannot even default). Every manifest
    record must carry a recognized disposition; exit nonzero if any does not.
    """
    units = get_units(manifest)
    # Surface a static-only manifest so a summary is never mistaken for a full
    # inventory (GAP-1): runtime mode was requested but did not run.
    if manifest.get("runtime_error"):
        print(
            "NOTE: manifest is STATIC-ONLY (runtime mode did not run: {0})".format(
                manifest["runtime_error"]
            )
        )
    counts = {s: 0 for s in ALL_STATES}
    unknown = []

    for unit_id, unit in units.items():
        state = unit_state(unit)
        if state not in counts:
            unknown.append((unit_id, state))
        else:
            counts[state] += 1

    total = len(units)
    print("units: {0}".format(total))
    for state in ALL_STATES:
        print("  {0:<14} {1}".format(state, counts[state]))

    terminal = sum(counts[s] for s in TERMINAL)
    in_flight = total - terminal - len(unknown)
    print("dispositioned (complete or deferred): {0}/{1}".format(terminal, total))
    print("in flight: {0}".format(in_flight))

    if unknown:
        print(
            "SILENT OMISSION: {0} unit(s) with no recognized state".format(len(unknown))
        )
        for unit_id, state in unknown:
            print("  {0}  (state={1!r})".format(unit_id, state))
        return 1
    if in_flight:
        # SKILL.md rule 2: every record ends complete or deferred; exit nonzero otherwise.
        print("INCOMPLETE: {0} unit(s) not yet dispositioned".format(in_flight))
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Per-unit migration state machine.")
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="inventory manifest JSON (default: " + DEFAULT_MANIFEST + ")",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_filters(p):
        # bulk selection, shared by advance/defer/reopen (unit_id optional)
        p.add_argument(
            "unit_id",
            nargs="?",
            default=None,
            help="single unit id; omit and use --where/--from-state for bulk",
        )
        p.add_argument(
            "--where",
            action="append",
            default=[],
            metavar="KEY=VALUE",
            help="bulk filter on a record field (e.g. kind=op); repeatable, ANDed",
        )
        p.add_argument(
            "--from-state",
            dest="from_state",
            default=None,
            help="bulk filter: only units currently in this state",
        )
        p.add_argument(
            "--dry-run",
            action="store_true",
            help="print the matches and planned transitions without writing",
        )

    p_show = sub.add_parser("show", help="list units and their states")
    p_show.add_argument("--by-state", action="store_true", help="group by state")

    p_adv = sub.add_parser("advance", help="advance a unit (or a --where set) one step")
    _add_filters(p_adv)
    p_adv.add_argument(
        "--evidence",
        required=True,
        help="path or command-output reference proving the gate passed",
    )

    p_def = sub.add_parser(
        "defer", help="mark a unit (or a --where set) deferred with a reason"
    )
    _add_filters(p_def)
    p_def.add_argument("--reason", required=True, help="why the unit(s) are deferred")

    p_reopen = sub.add_parser(
        "reopen", help="move complete/deferred unit(s) back to translate"
    )
    _add_filters(p_reopen)
    p_reopen.add_argument(
        "--reason", required=True, help="why the unit(s) are being reopened"
    )

    sub.add_parser("summary", help="counts per state and completeness check")

    args = parser.parse_args(argv)
    manifest = load_manifest(args.manifest)

    if args.command == "show":
        return cmd_show(manifest, args.by_state)
    if args.command in ("advance", "defer", "reopen"):
        return run_transition(manifest, args.manifest, args.command, args)
    if args.command == "summary":
        return cmd_summary(manifest)
    return 2


if __name__ == "__main__":
    sys.exit(main())
