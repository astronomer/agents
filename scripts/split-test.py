#!/usr/bin/env python3
"""Run split tests to evaluate skill configurations.

Compares agent behavior under different configurations:
- With/without warehouse.md
- With/without cache
- Different skill versions

Usage:
    python scripts/split-test.py --query "Find HITL operator customers"
    python scripts/split-test.py --queries tests/queries.txt --output results.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TestConfig:
    """Configuration for a test run."""

    name: str
    use_warehouse_md: bool = True
    use_cache: bool = True
    env_vars: dict[str, str] = field(default_factory=dict)


@dataclass
class TestResult:
    """Result from a single test run."""

    config_name: str
    query: str
    success: bool
    duration_sec: float
    output: str
    error: str | None = None
    trace: list[dict] | None = None
    operators_found: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_name": self.config_name,
            "query": self.query,
            "success": self.success,
            "duration_sec": round(self.duration_sec, 2),
            "operators_found": self.operators_found,
            "error": self.error,
        }


# Test configurations for split testing
CONFIGURATIONS = [
    TestConfig(
        name="baseline",
        use_warehouse_md=True,
        use_cache=True,
    ),
    TestConfig(
        name="no_warehouse_md",
        use_warehouse_md=False,
        use_cache=True,
    ),
    TestConfig(
        name="no_cache",
        use_warehouse_md=True,
        use_cache=False,
        env_vars={"DISABLE_CONCEPT_CACHE": "true"},
    ),
    TestConfig(
        name="neither",
        use_warehouse_md=False,
        use_cache=False,
        env_vars={"DISABLE_CONCEPT_CACHE": "true"},
    ),
]


def find_warehouse_md() -> Path | None:
    """Find warehouse.md in common locations."""
    locations = [
        Path(".astro/warehouse.md"),
        Path.home() / ".astro" / "ai" / "config" / "warehouse.md",
    ]
    for loc in locations:
        if loc.exists():
            return loc
    return None


def run_test(
    query: str,
    config: TestConfig,
    plugin_dir: str,
    mock_file: str | None = None,
    timeout: int = 300,
) -> TestResult:
    """Run a single test with given configuration.

    Args:
        query: The query to test
        config: Test configuration
        plugin_dir: Path to the Claude Code plugin directory
        mock_file: Optional mock responses file for DRY_RUN mode
        timeout: Maximum seconds to wait for completion

    Returns:
        TestResult with outcome
    """
    start = time.time()

    # Build environment
    env = os.environ.copy()
    env.update(config.env_vars)

    if mock_file:
        env["DRY_RUN_MODE"] = "true"
        env["MOCK_RESPONSES_FILE"] = mock_file

    # Handle warehouse.md
    warehouse_path = find_warehouse_md()
    warehouse_backup = None

    if not config.use_warehouse_md and warehouse_path and warehouse_path.exists():
        # Temporarily rename warehouse.md
        warehouse_backup = warehouse_path.with_suffix(".md.bak")
        shutil.move(str(warehouse_path), str(warehouse_backup))

    try:
        # Run claude with query
        result = subprocess.run(
            [
                "claude",
                "--plugin-dir",
                plugin_dir,
                "-p",
                query,
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )

        duration = time.time() - start

        # Parse output for operators found
        operators_found = []
        output_lower = result.stdout.lower()
        for op in [
            "HITLOperator",
            "HITLBranchOperator",
            "HITLEntryOperator",
            "ApprovalOperator",
            "ApprovalSensor",
            "SnowflakeOperator",
        ]:
            if op.lower() in output_lower:
                operators_found.append(op)

        return TestResult(
            config_name=config.name,
            query=query,
            success=result.returncode == 0,
            duration_sec=duration,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
            operators_found=operators_found,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            config_name=config.name,
            query=query,
            success=False,
            duration_sec=timeout,
            output="",
            error="Timeout",
        )

    except Exception as e:
        return TestResult(
            config_name=config.name,
            query=query,
            success=False,
            duration_sec=time.time() - start,
            output="",
            error=str(e),
        )

    finally:
        # Restore warehouse.md
        if warehouse_backup and warehouse_backup.exists():
            shutil.move(str(warehouse_backup), str(warehouse_path))


def run_split_test(
    queries: list[str],
    plugin_dir: str,
    configs: list[TestConfig] | None = None,
    mock_file: str | None = None,
) -> dict[str, Any]:
    """Run split tests across all configurations.

    Args:
        queries: List of queries to test
        plugin_dir: Path to Claude Code plugin directory
        configs: List of configurations to test (default: all)
        mock_file: Optional mock file for DRY_RUN mode

    Returns:
        Dictionary with all results and summary statistics
    """
    configs = configs or CONFIGURATIONS
    all_results = []
    summary = {
        "total_tests": len(queries) * len(configs),
        "passed": 0,
        "failed": 0,
        "by_config": {},
    }

    for query in queries:
        print(f"\nTesting: {query[:50]}...")
        for config in configs:
            print(f"  Config: {config.name}...", end=" ", flush=True)

            result = run_test(
                query=query,
                config=config,
                plugin_dir=plugin_dir,
                mock_file=mock_file,
            )

            all_results.append(result)

            if result.success:
                summary["passed"] += 1
                print(f"PASS ({result.duration_sec:.1f}s)")
            else:
                summary["failed"] += 1
                print(f"FAIL: {result.error}")

            # Track by config
            if config.name not in summary["by_config"]:
                summary["by_config"][config.name] = {
                    "passed": 0,
                    "failed": 0,
                    "avg_duration": 0,
                    "operators_found": set(),
                }
            cfg_summary = summary["by_config"][config.name]
            if result.success:
                cfg_summary["passed"] += 1
            else:
                cfg_summary["failed"] += 1
            cfg_summary["operators_found"].update(result.operators_found)

    # Calculate averages and convert sets to lists
    for cfg_name, cfg_summary in summary["by_config"].items():
        cfg_summary["operators_found"] = list(cfg_summary["operators_found"])

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "results": [r.to_dict() for r in all_results],
    }


def analyze_results(results: dict[str, Any]) -> str:
    """Analyze split test results and provide recommendations."""
    lines = [
        "=" * 60,
        "SPLIT TEST ANALYSIS",
        "=" * 60,
        "",
    ]

    summary = results["summary"]
    lines.append(f"Total tests: {summary['total_tests']}")
    lines.append(f"Passed: {summary['passed']}")
    lines.append(f"Failed: {summary['failed']}")
    lines.append("")

    lines.append("Results by configuration:")
    for cfg_name, cfg_summary in summary["by_config"].items():
        pass_rate = (
            cfg_summary["passed"]
            / (cfg_summary["passed"] + cfg_summary["failed"])
            * 100
            if (cfg_summary["passed"] + cfg_summary["failed"]) > 0
            else 0
        )
        ops = ", ".join(cfg_summary["operators_found"]) or "None"
        lines.append(f"  {cfg_name}:")
        lines.append(f"    Pass rate: {pass_rate:.0f}%")
        lines.append(f"    Operators found: {ops}")

    # Recommendations
    lines.append("")
    lines.append("Recommendations:")

    by_config = summary["by_config"]

    # Compare warehouse.md impact
    if "baseline" in by_config and "no_warehouse_md" in by_config:
        baseline_ops = set(by_config["baseline"]["operators_found"])
        no_wh_ops = set(by_config["no_warehouse_md"]["operators_found"])

        if baseline_ops == no_wh_ops:
            lines.append("  - warehouse.md: No impact on operators found")
        elif len(baseline_ops) > len(no_wh_ops):
            lines.append("  - warehouse.md: HELPS - finds more operators")
        else:
            lines.append("  - warehouse.md: May HURT - finds fewer operators")

    # Compare cache impact
    if "baseline" in by_config and "no_cache" in by_config:
        baseline_ops = set(by_config["baseline"]["operators_found"])
        no_cache_ops = set(by_config["no_cache"]["operators_found"])

        if baseline_ops == no_cache_ops:
            lines.append("  - Cache: No impact on operators found")
        else:
            lines.append("  - Cache: Affects which operators are found - investigate")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run split tests on skills")
    parser.add_argument("--query", help="Single query to test")
    parser.add_argument("--queries", help="File with queries (one per line)")
    parser.add_argument(
        "--plugin-dir",
        default="./claude-code-plugin",
        help="Path to Claude Code plugin directory",
    )
    parser.add_argument("--mock-file", help="Mock responses file for DRY_RUN mode")
    parser.add_argument("--output", help="Output file for JSON results")
    parser.add_argument("--config", action="append", help="Specific config(s) to test")

    args = parser.parse_args()

    # Get queries
    if args.query:
        queries = [args.query]
    elif args.queries:
        queries = Path(args.queries).read_text().strip().split("\n")
    else:
        print("Error: Must provide --query or --queries")
        sys.exit(1)

    # Filter configs if specified
    configs = CONFIGURATIONS
    if args.config:
        configs = [c for c in CONFIGURATIONS if c.name in args.config]
        if not configs:
            print(f"Error: No matching configs found for {args.config}")
            sys.exit(1)

    # Run tests
    results = run_split_test(
        queries=queries,
        plugin_dir=args.plugin_dir,
        configs=configs,
        mock_file=args.mock_file,
    )

    # Output results
    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"\nResults saved to {args.output}")

    # Print analysis
    print(analyze_results(results))


if __name__ == "__main__":
    main()
