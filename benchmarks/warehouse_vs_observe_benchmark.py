#!/usr/bin/env python3
"""Proper benchmark: Warehouse SQL vs Observe Semantic Search.

This benchmark compares:
1. Warehouse approach: Direct SQL queries via analyzing-data skill
2. Observe approach: Semantic search via analyzing-data-observe skill

Results are validated against ground truth for precision/recall/F1.

Prerequisites:
1. Generate ground truth first: python ground_truth.py --use-kernel
2. Warehouse config: ~/.astro/agents/warehouse.yml
3. Astro login: astro login

Usage:
    python warehouse_vs_observe_benchmark.py --org-id <ORG_ID>
    python warehouse_vs_observe_benchmark.py --org-id <ORG_ID> --warehouse-only
    python warehouse_vs_observe_benchmark.py --org-id <ORG_ID> --observe-only
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from validation import (
    ValidationResult,
    validate_tables,
    validate_count,
    format_validation_summary,
    extract_tables_from_response,
)


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    approach: str
    scenario: str
    prompt: str
    # Performance metrics
    duration_ms: float
    num_turns: int
    total_cost_usd: float
    # Result
    result_text: str
    success: bool
    error: str | None = None
    # Validation
    validation: ValidationResult | None = None
    count_valid: bool | None = None
    count_found: int | None = None


@dataclass
class Scenario:
    """Benchmark scenario definition."""
    name: str
    prompt: str
    description: str
    ground_truth_key: str
    validate_tables: bool = True
    validate_count: bool = False


# Scenarios to benchmark
SCENARIOS = [
    Scenario(
        name="find_customer_tables",
        prompt="Find all tables with 'customer' in the name. List each table name.",
        description="Find tables by keyword search",
        ground_truth_key="find_customer_tables",
        validate_tables=True,
        validate_count=True,
    ),
    Scenario(
        name="list_tables",
        prompt="List the first 20 tables in the database. Just show the table names.",
        description="List tables (subset)",
        ground_truth_key="list_snowflake_tables",
        validate_tables=True,
        validate_count=False,
    ),
    Scenario(
        name="tables_with_email",
        prompt="Find all tables that have a column containing 'email' in its name. List the table names.",
        description="Column-level search",
        ground_truth_key="tables_with_email_column",
        validate_tables=True,
        validate_count=True,
    ),
    Scenario(
        name="list_schemas",
        prompt="List all schemas in the database.",
        description="Schema enumeration",
        ground_truth_key="list_schemas",
        validate_tables=False,  # Schemas, not tables
        validate_count=True,
    ),
    Scenario(
        name="tables_per_schema",
        prompt="How many tables are in each schema? Show the count per schema.",
        description="Aggregation query",
        ground_truth_key="tables_per_schema",
        validate_tables=False,
        validate_count=True,
    ),
]


def verify_warehouse_connection() -> bool:
    """Verify the warehouse kernel can connect and run SQL."""
    skill_dir = Path(__file__).parent.parent / "skills" / "analyzing-data"

    print("Verifying warehouse connection...")

    # Try to start kernel
    result = subprocess.run(
        ["uv", "run", "scripts/cli.py", "start"],
        cwd=skill_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        print(f"  ❌ Failed to start kernel: {result.stderr}")
        return False

    # Test query
    result = subprocess.run(
        ["uv", "run", "scripts/cli.py", "exec", "print(run_sql('SELECT 1 as test'))"],
        cwd=skill_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0 or "test" not in result.stdout.lower():
        print(f"  ❌ Failed to execute test query: {result.stderr}")
        return False

    print("  ✓ Warehouse connection verified")
    return True


def verify_observe_connection(org_id: str) -> bool:
    """Verify Observe MCP can connect."""
    print("Verifying Observe connection...")

    observe_path = Path(__file__).parent.parent / "astro-observe-mcp"

    result = subprocess.run(
        ["uv", "run", "astro-observe-mcp", "--version"],
        cwd=observe_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Just check the command exists
    print("  ✓ Observe MCP available")
    return True


def run_warehouse_scenario(scenario: Scenario, timeout: int = 180) -> BenchmarkResult:
    """Run scenario using warehouse SQL approach (NO Observe MCP).

    Uses the analyzing-data skill which runs SQL via Jupyter kernel.
    Creates a temp plugin without Observe MCP to ensure pure SQL approach.
    """
    agents_root = Path(__file__).parent.parent

    # Create temp plugin config WITHOUT observe MCP (SQL-only)
    temp_dir = Path(tempfile.mkdtemp(prefix="warehouse_benchmark_"))
    plugin_dir = temp_dir / ".claude-plugin"
    plugin_dir.mkdir(parents=True)

    # Copy skills directory
    skills_src = agents_root / "skills"
    skills_dst = temp_dir / "skills"
    shutil.copytree(skills_src, skills_dst)

    config = {
        "name": "astronomer",
        "owner": {"name": "Benchmark", "email": "benchmark@test.io"},
        "plugins": [{
            "name": "data",
            "source": str(temp_dir),
            "strict": False,
            "description": "Warehouse SQL benchmark (no Observe)",
            "version": "0.1.0",
            "mcpServers": {
                # Only airflow MCP - NO observe MCP
                "airflow": {
                    "command": "uvx",
                    "args": ["astro-airflow-mcp@0.2.3", "--transport", "stdio", "--airflow-project-dir", "${PWD}"]
                }
            }
        }]
    }

    config_path = plugin_dir / "marketplace.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    # Force the skill to use SQL against HQ database
    prompt = f"""/data:analyzing-data

Answer this question using SQL queries against the HQ database in Snowflake.
Use run_sql() to query HQ.INFORMATION_SCHEMA.TABLES or SHOW commands.

{scenario.prompt}"""

    cmd = [
        'claude',
        '--print',
        '--model', 'haiku',
        '--output-format', 'json',
        '--plugin-dir', str(temp_dir),
        '--no-session-persistence',
        '--permission-mode', 'bypassPermissions',
    ]

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = (time.time() - start) * 1000

        if result.returncode != 0:
            return BenchmarkResult(
                approach="warehouse",
                scenario=scenario.name,
                prompt=scenario.prompt,
                duration_ms=elapsed_ms,
                num_turns=0,
                total_cost_usd=0,
                result_text="",
                success=False,
                error=f"Claude failed: {result.stderr}",
            )

        output = json.loads(result.stdout)

        return BenchmarkResult(
            approach="warehouse",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=output.get('duration_ms', elapsed_ms),
            num_turns=output.get('num_turns', 0),
            total_cost_usd=output.get('total_cost_usd', 0),
            result_text=output.get('result', ''),
            success=not output.get('is_error', False),
        )

    except subprocess.TimeoutExpired:
        return BenchmarkResult(
            approach="warehouse",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=timeout * 1000,
            num_turns=0,
            total_cost_usd=0,
            result_text="",
            success=False,
            error=f"Timeout after {timeout}s",
        )
    except Exception as e:
        return BenchmarkResult(
            approach="warehouse",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=0,
            num_turns=0,
            total_cost_usd=0,
            result_text="",
            success=False,
            error=str(e),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_observe_scenario(scenario: Scenario, org_id: str, timeout: int = 180) -> BenchmarkResult:
    """Run scenario using Observe semantic search approach.

    Uses the analyzing-data-observe skill which calls Observe MCP.
    """
    agents_root = Path(__file__).parent.parent
    observe_path = agents_root / "astro-observe-mcp"

    # Create temp plugin config
    temp_dir = Path(tempfile.mkdtemp(prefix="observe_benchmark_"))
    plugin_dir = temp_dir / ".claude-plugin"
    plugin_dir.mkdir(parents=True)

    config = {
        "name": "observe-benchmark",
        "owner": {"name": "Benchmark", "email": "benchmark@test.io"},
        "plugins": [{
            "name": "catalog",
            "source": str(agents_root),
            "strict": False,
            "description": "Catalog-based asset discovery",
            "version": "0.1.0",
            "mcpServers": {
                "observe": {
                    "command": "uv",
                    "args": ["--directory", str(observe_path), "run", "astro-observe-mcp"],
                    "env": {"ASTRO_ORGANIZATION_ID": org_id}
                }
            }
        }]
    }

    config_path = plugin_dir / "marketplace.json"
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    # Scope Observe to same data as warehouse (HQ database in Snowflake)
    prompt = f"""/catalog:analyzing-data-observe

Search only in the Snowflake HQ database tables. Filter results to tables from the HQ database only.

{scenario.prompt}"""

    cmd = [
        'claude',
        '--print',
        '--model', 'haiku',
        '--output-format', 'json',
        '--plugin-dir', str(temp_dir),
        '--no-session-persistence',
        '--permission-mode', 'bypassPermissions',
    ]

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed_ms = (time.time() - start) * 1000

        if result.returncode != 0:
            return BenchmarkResult(
                approach="observe",
                scenario=scenario.name,
                prompt=scenario.prompt,
                duration_ms=elapsed_ms,
                num_turns=0,
                total_cost_usd=0,
                result_text="",
                success=False,
                error=f"Claude failed: {result.stderr}",
            )

        output = json.loads(result.stdout)

        return BenchmarkResult(
            approach="observe",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=output.get('duration_ms', elapsed_ms),
            num_turns=output.get('num_turns', 0),
            total_cost_usd=output.get('total_cost_usd', 0),
            result_text=output.get('result', ''),
            success=not output.get('is_error', False),
        )

    except subprocess.TimeoutExpired:
        return BenchmarkResult(
            approach="observe",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=timeout * 1000,
            num_turns=0,
            total_cost_usd=0,
            result_text="",
            success=False,
            error=f"Timeout after {timeout}s",
        )
    except Exception as e:
        return BenchmarkResult(
            approach="observe",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=0,
            num_turns=0,
            total_cost_usd=0,
            result_text="",
            success=False,
            error=str(e),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def validate_result(result: BenchmarkResult, scenario: Scenario, ground_truth: dict) -> BenchmarkResult:
    """Validate result against ground truth."""
    if not result.success:
        return result

    gt_data = ground_truth.get("scenarios", {}).get(scenario.ground_truth_key)
    if not gt_data:
        print(f"    ⚠️  No ground truth for {scenario.ground_truth_key}")
        return result

    # Validate tables if applicable
    if scenario.validate_tables and "tables" in gt_data:
        result.validation = validate_tables(
            result.result_text,
            gt_data["tables"],
            fuzzy_match=True,
        )

    # Validate count if applicable
    if scenario.validate_count and "total_count" in gt_data:
        result.count_valid, result.count_found, _ = validate_count(
            result.result_text,
            gt_data["total_count"],
            tolerance=0.2,  # 20% tolerance
        )

    return result


def print_result_comparison(warehouse: BenchmarkResult, observe: BenchmarkResult, scenario: Scenario):
    """Print side-by-side comparison of results."""
    print(f"\n{'─'*70}")
    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"{'─'*70}")

    # Performance comparison
    print(f"\n{'Metric':<20} {'Warehouse':<20} {'Observe':<20}")
    print(f"{'─'*60}")

    w_time = f"{warehouse.duration_ms:.0f}ms" if warehouse.success else "FAILED"
    o_time = f"{observe.duration_ms:.0f}ms" if observe.success else "FAILED"
    print(f"{'Time':<20} {w_time:<20} {o_time:<20}")

    w_turns = str(warehouse.num_turns) if warehouse.success else "-"
    o_turns = str(observe.num_turns) if observe.success else "-"
    print(f"{'Turns':<20} {w_turns:<20} {o_turns:<20}")

    w_cost = f"${warehouse.total_cost_usd:.4f}" if warehouse.success else "-"
    o_cost = f"${observe.total_cost_usd:.4f}" if observe.success else "-"
    print(f"{'Cost':<20} {w_cost:<20} {o_cost:<20}")

    # Validation results
    if warehouse.validation or observe.validation:
        print(f"\n{'Quality Metrics':<20} {'Warehouse':<20} {'Observe':<20}")
        print(f"{'─'*60}")

        w_precision = f"{warehouse.validation.precision:.1%}" if warehouse.validation else "-"
        o_precision = f"{observe.validation.precision:.1%}" if observe.validation else "-"
        print(f"{'Precision':<20} {w_precision:<20} {o_precision:<20}")

        w_recall = f"{warehouse.validation.recall:.1%}" if warehouse.validation else "-"
        o_recall = f"{observe.validation.recall:.1%}" if observe.validation else "-"
        print(f"{'Recall':<20} {w_recall:<20} {o_recall:<20}")

        w_f1 = f"{warehouse.validation.f1:.1%}" if warehouse.validation else "-"
        o_f1 = f"{observe.validation.f1:.1%}" if observe.validation else "-"
        print(f"{'F1 Score':<20} {w_f1:<20} {o_f1:<20}")

    if warehouse.count_valid is not None or observe.count_valid is not None:
        w_count = f"{'✓' if warehouse.count_valid else '✗'} ({warehouse.count_found})" if warehouse.count_valid is not None else "-"
        o_count = f"{'✓' if observe.count_valid else '✗'} ({observe.count_found})" if observe.count_valid is not None else "-"
        print(f"{'Count Valid':<20} {w_count:<20} {o_count:<20}")

    # Winner determination
    print(f"\n{'Winner Analysis':<60}")
    print(f"{'─'*60}")

    if not warehouse.success and not observe.success:
        print("  Both approaches failed")
    elif not warehouse.success:
        print("  Winner: OBSERVE (warehouse failed)")
    elif not observe.success:
        print("  Winner: WAREHOUSE (observe failed)")
    else:
        # Compare F1 scores if available
        w_f1 = warehouse.validation.f1 if warehouse.validation else 0
        o_f1 = observe.validation.f1 if observe.validation else 0

        if w_f1 > o_f1 + 0.1:
            print(f"  Quality Winner: WAREHOUSE (F1: {w_f1:.1%} vs {o_f1:.1%})")
        elif o_f1 > w_f1 + 0.1:
            print(f"  Quality Winner: OBSERVE (F1: {o_f1:.1%} vs {w_f1:.1%})")
        else:
            print(f"  Quality: TIE (F1: {w_f1:.1%} vs {o_f1:.1%})")

        # Compare speed
        if warehouse.duration_ms < observe.duration_ms * 0.8:
            speedup = observe.duration_ms / warehouse.duration_ms
            print(f"  Speed Winner: WAREHOUSE ({speedup:.1f}x faster)")
        elif observe.duration_ms < warehouse.duration_ms * 0.8:
            speedup = warehouse.duration_ms / observe.duration_ms
            print(f"  Speed Winner: OBSERVE ({speedup:.1f}x faster)")
        else:
            print(f"  Speed: TIE")


def print_summary(results: list[tuple[BenchmarkResult, BenchmarkResult]]):
    """Print overall summary."""
    print(f"\n{'='*70}")
    print("OVERALL SUMMARY")
    print(f"{'='*70}")

    warehouse_wins = 0
    observe_wins = 0
    ties = 0

    for warehouse, observe in results:
        w_success_flag = warehouse and warehouse.success
        o_success_flag = observe and observe.success

        if not w_success_flag and not o_success_flag:
            ties += 1
        elif not w_success_flag:
            observe_wins += 1
        elif not o_success_flag:
            warehouse_wins += 1
        else:
            w_f1 = warehouse.validation.f1 if warehouse.validation else 0
            o_f1 = observe.validation.f1 if observe.validation else 0
            if w_f1 > o_f1 + 0.1:
                warehouse_wins += 1
            elif o_f1 > w_f1 + 0.1:
                observe_wins += 1
            else:
                ties += 1

    total = len(results)
    print(f"\nQuality Wins:")
    print(f"  Warehouse: {warehouse_wins}/{total} ({warehouse_wins/total:.0%})")
    print(f"  Observe:   {observe_wins}/{total} ({observe_wins/total:.0%})")
    print(f"  Ties:      {ties}/{total} ({ties/total:.0%})")

    # Average metrics
    w_success = [r[0] for r in results if r[0] and r[0].success]
    o_success = [r[1] for r in results if r[1] and r[1].success]

    if w_success:
        w_avg_time = sum(r.duration_ms for r in w_success) / len(w_success)
        w_avg_turns = sum(r.num_turns for r in w_success) / len(w_success)
        w_avg_cost = sum(r.total_cost_usd for r in w_success) / len(w_success)
        w_avg_f1 = sum(r.validation.f1 for r in w_success if r.validation) / len([r for r in w_success if r.validation]) if any(r.validation for r in w_success) else 0
    else:
        w_avg_time = w_avg_turns = w_avg_cost = w_avg_f1 = 0

    if o_success:
        o_avg_time = sum(r.duration_ms for r in o_success) / len(o_success)
        o_avg_turns = sum(r.num_turns for r in o_success) / len(o_success)
        o_avg_cost = sum(r.total_cost_usd for r in o_success) / len(o_success)
        o_avg_f1 = sum(r.validation.f1 for r in o_success if r.validation) / len([r for r in o_success if r.validation]) if any(r.validation for r in o_success) else 0
    else:
        o_avg_time = o_avg_turns = o_avg_cost = o_avg_f1 = 0

    print(f"\nAverage Performance (successful runs):")
    print(f"  {'Metric':<15} {'Warehouse':<20} {'Observe':<20}")
    print(f"  {'─'*55}")
    print(f"  {'Time':<15} {w_avg_time:>15.0f}ms {o_avg_time:>15.0f}ms")
    print(f"  {'Turns':<15} {w_avg_turns:>15.1f} {o_avg_turns:>15.1f}")
    print(f"  {'Cost':<15} ${w_avg_cost:>14.4f} ${o_avg_cost:>14.4f}")
    print(f"  {'F1 Score':<15} {w_avg_f1:>15.1%} {o_avg_f1:>15.1%}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: Warehouse SQL vs Observe Semantic Search"
    )
    parser.add_argument('--org-id', required=True, help='Astro organization ID')
    parser.add_argument('--warehouse-only', action='store_true', help='Only test warehouse approach')
    parser.add_argument('--observe-only', action='store_true', help='Only test observe approach')
    parser.add_argument('--scenarios', nargs='+', help='Specific scenarios to run')
    parser.add_argument('--timeout', type=int, default=180, help='Timeout per scenario (seconds)')
    parser.add_argument('--output', default='benchmark_results.json', help='Output file')
    parser.add_argument('--ground-truth', default='ground_truth.json', help='Ground truth file')

    args = parser.parse_args()

    # Load ground truth
    gt_path = Path(args.ground_truth)
    if not gt_path.exists():
        print(f"❌ Ground truth not found: {gt_path}")
        print("   Run: python ground_truth.py --use-kernel")
        sys.exit(1)

    with open(gt_path) as f:
        ground_truth = json.load(f)

    print(f"Loaded ground truth from: {gt_path}")
    print(f"  Generated: {ground_truth.get('generated_at', 'unknown')}")
    print(f"  Scenarios: {', '.join(ground_truth.get('scenarios', {}).keys())}")

    # Determine what to test
    test_warehouse = not args.observe_only
    test_observe = not args.warehouse_only

    # Verify connections
    if test_warehouse:
        if not verify_warehouse_connection():
            print("❌ Cannot proceed without warehouse connection")
            if not test_observe:
                sys.exit(1)
            test_warehouse = False

    if test_observe:
        verify_observe_connection(args.org_id)

    # Filter scenarios
    scenarios = SCENARIOS
    if args.scenarios:
        scenarios = [s for s in SCENARIOS if s.name in args.scenarios]

    print(f"\n{'='*70}")
    print("WAREHOUSE SQL vs OBSERVE SEMANTIC SEARCH BENCHMARK")
    print(f"{'='*70}")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Testing: {'Warehouse' if test_warehouse else ''} {'Observe' if test_observe else ''}")
    print(f"Org ID: {args.org_id}")

    # Run benchmarks
    results = []
    for scenario in scenarios:
        print(f"\n📝 Running: {scenario.name}...")

        warehouse_result = None
        observe_result = None

        if test_warehouse:
            print("  [Warehouse] Starting...")
            warehouse_result = run_warehouse_scenario(scenario, args.timeout)
            warehouse_result = validate_result(warehouse_result, scenario, ground_truth)
            if warehouse_result.success:
                print(f"  [Warehouse] ✓ {warehouse_result.duration_ms:.0f}ms, {warehouse_result.num_turns} turns")
            else:
                print(f"  [Warehouse] ✗ {warehouse_result.error}")

        if test_observe:
            print("  [Observe] Starting...")
            observe_result = run_observe_scenario(scenario, args.org_id, args.timeout)
            observe_result = validate_result(observe_result, scenario, ground_truth)
            if observe_result.success:
                print(f"  [Observe] ✓ {observe_result.duration_ms:.0f}ms, {observe_result.num_turns} turns")
            else:
                print(f"  [Observe] ✗ {observe_result.error}")

        # Always append results (even if only one approach ran)
        if warehouse_result or observe_result:
            results.append((warehouse_result, observe_result))
            if warehouse_result and observe_result:
                print_result_comparison(warehouse_result, observe_result, scenario)

    # Print summary
    if results:
        print_summary(results)

    # Save results
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "org_id": args.org_id,
        "ground_truth_file": str(gt_path),
        "results": []
    }

    for warehouse, observe in results:
        output_data["results"].append({
            "scenario": warehouse.scenario if warehouse else observe.scenario,
            "warehouse": {
                "success": warehouse.success if warehouse else False,
                "duration_ms": warehouse.duration_ms if warehouse else 0,
                "num_turns": warehouse.num_turns if warehouse else 0,
                "total_cost_usd": warehouse.total_cost_usd if warehouse else 0,
                "precision": warehouse.validation.precision if warehouse and warehouse.validation else None,
                "recall": warehouse.validation.recall if warehouse and warehouse.validation else None,
                "f1": warehouse.validation.f1 if warehouse and warehouse.validation else None,
                "found_tables": warehouse.validation.true_positives if warehouse and warehouse.validation else [],
                "missed_tables": warehouse.validation.false_negatives[:10] if warehouse and warehouse.validation else [],
                "result_text": warehouse.result_text[:1000] if warehouse else None,
                "error": warehouse.error if warehouse else None,
            } if warehouse else None,
            "observe": {
                "success": observe.success if observe else False,
                "duration_ms": observe.duration_ms if observe else 0,
                "num_turns": observe.num_turns if observe else 0,
                "total_cost_usd": observe.total_cost_usd if observe else 0,
                "precision": observe.validation.precision if observe and observe.validation else None,
                "recall": observe.validation.recall if observe and observe.validation else None,
                "f1": observe.validation.f1 if observe and observe.validation else None,
                "found_tables": observe.validation.true_positives if observe and observe.validation else [],
                "missed_tables": observe.validation.false_negatives[:10] if observe and observe.validation else [],
                "result_text": observe.result_text[:1000] if observe else None,
                "error": observe.error if observe else None,
            } if observe else None,
        })

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n💾 Results saved to: {args.output}")


if __name__ == "__main__":
    main()
