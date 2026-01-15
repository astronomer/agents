#!/usr/bin/env python3
"""Compare actual agent flow against expected flow definitions.

Usage:
    python scripts/compare-flows.py tests/traces/hitl-test.json tests/expected-flows/hitl-operators.yaml

Trace format (from Claude Code transcript):
{
    "query": "Find customers using HITL operators",
    "trace": [
        {"action": "read", "file": "SKILL.md", "timestamp": "..."},
        {"action": "webfetch", "url": "https://airflow.apache.org/...", "timestamp": "..."},
        {"action": "run_sql", "query": "SELECT ...", "timestamp": "..."}
    ]
}

Expected flow format (YAML):
expected_flow:
  - action: read
    file_pattern: "SKILL.md"
    required: true
  - action: webfetch
    url_pattern: "airflow.apache.org"
    required: true
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FlowStep:
    """A step in the expected flow."""

    action: str
    pattern: str  # file_pattern, url_pattern, or query_pattern
    required: bool
    note: str | None = None


@dataclass
class TraceStep:
    """A step in the actual trace."""

    action: str
    details: dict[str, Any]
    timestamp: str | None = None


@dataclass
class Mismatch:
    """A mismatch between expected and actual flow."""

    step_index: int
    expected: FlowStep | None
    actual: TraceStep | None
    reason: str


def load_trace(trace_file: str) -> tuple[str, list[TraceStep]]:
    """Load actual trace from JSON file.

    Returns:
        Tuple of (query, list of trace steps)
    """
    data = json.loads(Path(trace_file).read_text(encoding="utf-8"))
    query = data.get("query", "")
    trace = []

    for step in data.get("trace", []):
        trace.append(
            TraceStep(
                action=step.get("action", "unknown"),
                details=step,
                timestamp=step.get("timestamp"),
            )
        )

    return query, trace


def load_expected_flow(expected_file: str) -> tuple[str, list[FlowStep]]:
    """Load expected flow from YAML file.

    Returns:
        Tuple of (flow name, list of expected steps)
    """
    data = yaml.safe_load(Path(expected_file).read_text(encoding="utf-8"))
    name = data.get("name", "unnamed")
    steps = []

    for step in data.get("expected_flow", []):
        pattern = (
            step.get("file_pattern")
            or step.get("url_pattern")
            or step.get("query_pattern")
            or ""
        )
        steps.append(
            FlowStep(
                action=step.get("action", "unknown"),
                pattern=pattern,
                required=step.get("required", True),
                note=step.get("note"),
            )
        )

    return name, steps


def match_step(expected: FlowStep, actual: TraceStep) -> bool:
    """Check if an actual trace step matches an expected step."""
    if expected.action != actual.action:
        return False

    # Check pattern match based on action type
    if expected.action == "read":
        file_path = actual.details.get("file", "")
        return bool(re.search(expected.pattern, file_path, re.IGNORECASE))

    elif expected.action == "webfetch":
        url = actual.details.get("url", "")
        return bool(re.search(expected.pattern, url, re.IGNORECASE))

    elif expected.action == "run_sql":
        query = actual.details.get("query", "")
        return bool(re.search(expected.pattern, query, re.IGNORECASE | re.DOTALL))

    return True  # Unknown action types match if action name matches


def compare_flows(
    expected: list[FlowStep], actual: list[TraceStep]
) -> tuple[list[Mismatch], list[FlowStep]]:
    """Compare expected flow against actual trace.

    Returns:
        Tuple of (list of mismatches, list of missing required steps)
    """
    mismatches = []
    missing_required = []
    actual_idx = 0

    for exp_idx, exp_step in enumerate(expected):
        found = False

        # Look for this expected step in remaining actual steps
        for i in range(actual_idx, len(actual)):
            if match_step(exp_step, actual[i]):
                found = True
                # Check if we skipped any steps
                if i > actual_idx:
                    for j in range(actual_idx, i):
                        mismatches.append(
                            Mismatch(
                                step_index=j,
                                expected=None,
                                actual=actual[j],
                                reason=f"Unexpected step before {exp_step.action}",
                            )
                        )
                actual_idx = i + 1
                break

        if not found:
            if exp_step.required:
                missing_required.append(exp_step)
                mismatches.append(
                    Mismatch(
                        step_index=exp_idx,
                        expected=exp_step,
                        actual=None,
                        reason=f"Required step not found: {exp_step.action} matching '{exp_step.pattern}'",
                    )
                )

    return mismatches, missing_required


def format_results(
    flow_name: str,
    query: str,
    mismatches: list[Mismatch],
    missing_required: list[FlowStep],
) -> str:
    """Format comparison results as human-readable string."""
    lines = [
        f"Flow: {flow_name}",
        f"Query: {query}",
        "",
    ]

    if not mismatches and not missing_required:
        lines.append("PASS: Flow matches expected!")
        return "\n".join(lines)

    lines.append("FAIL: Flow does not match expected")
    lines.append("")

    if missing_required:
        lines.append("Missing required steps:")
        for step in missing_required:
            lines.append(f"  - {step.action}: {step.pattern}")
            if step.note:
                lines.append(f"    Note: {step.note}")

    if mismatches:
        lines.append("")
        lines.append("Mismatches:")
        for m in mismatches:
            lines.append(f"  [{m.step_index}] {m.reason}")
            if m.expected:
                lines.append(
                    f"       Expected: {m.expected.action} '{m.expected.pattern}'"
                )
            if m.actual:
                lines.append(f"       Actual: {m.actual.action} {m.actual.details}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 3:
        print("Usage: compare-flows.py <trace.json> <expected-flow.yaml>")
        print()
        print("Compares actual agent trace against expected flow definition.")
        sys.exit(1)

    trace_file = sys.argv[1]
    expected_file = sys.argv[2]

    # Load files
    query, actual_trace = load_trace(trace_file)
    flow_name, expected_flow = load_expected_flow(expected_file)

    # Compare
    mismatches, missing_required = compare_flows(expected_flow, actual_trace)

    # Output results
    result = format_results(flow_name, query, mismatches, missing_required)
    print(result)

    # Exit code based on success
    if mismatches or missing_required:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
