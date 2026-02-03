#!/usr/bin/env python3
"""Fair Benchmark: Warehouse SQL vs Observe Semantic Search.

This benchmark tests scenarios that are fair to both approaches:
1. Uses prompts that don't assume SQL-specific concepts
2. Tests use cases where both approaches can reasonably compete
3. Measures speed, turns, cost (quality validation is separate)

Key insight: These approaches are complementary, not competitive:
- Warehouse: Best for precise schema queries, column search, data analysis
- Observe: Best for cross-warehouse discovery, semantic search, metadata lookup

Usage:
    python fair_benchmark.py --org-id <ORG_ID>
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""

    approach: str
    scenario: str
    prompt: str
    duration_ms: float
    num_turns: int
    total_cost_usd: float
    result_text: str
    success: bool
    error: str | None = None


@dataclass
class Scenario:
    """Benchmark scenario definition."""

    name: str
    prompt: str  # Same prompt for both approaches
    description: str
    expected_behavior: str  # What we expect each approach to do


SCENARIOS = [
    Scenario(
        name="find_customer_tables",
        prompt="What tables contain customer data? List the top 10.",
        description="Semantic search for customer-related tables",
        expected_behavior="Observe uses semantic search, Warehouse uses INFORMATION_SCHEMA.",
    ),
    Scenario(
        name="find_revenue_tables",
        prompt="What tables have revenue or billing data?",
        description="Semantic search for financial data",
        expected_behavior="Observe uses semantic search for revenue/billing concepts.",
    ),
    Scenario(
        name="find_deployment_tables",
        prompt="What tables track Airflow deployments and their metadata?",
        description="Semantic search for deployment/infrastructure data",
        expected_behavior="Observe uses semantic search for deployment concepts.",
    ),
    Scenario(
        name="find_usage_tables",
        prompt="What tables track product usage and feature adoption?",
        description="Semantic search for usage/adoption data",
        expected_behavior="Observe uses semantic search for usage/adoption concepts.",
    ),
    Scenario(
        name="find_sales_tables",
        prompt="What tables contain sales pipeline or opportunity data?",
        description="Semantic search for sales data",
        expected_behavior="Observe uses semantic search for sales/pipeline concepts.",
    ),
    Scenario(
        name="find_support_tables",
        prompt="What tables have support ticket or customer service data?",
        description="Semantic search for support data",
        expected_behavior="Observe uses semantic search for support/ticket concepts.",
    ),
    Scenario(
        name="find_marketing_tables",
        prompt="What tables track marketing leads and campaigns?",
        description="Semantic search for marketing data",
        expected_behavior="Observe uses semantic search for marketing/lead concepts.",
    ),
    Scenario(
        name="find_dag_tables",
        prompt="What tables contain DAG run history and task execution data?",
        description="Semantic search for Airflow execution data",
        expected_behavior="Observe uses semantic search for DAG/task concepts.",
    ),
    Scenario(
        name="find_metrics_tables",
        prompt="What tables have pre-aggregated metrics or KPIs?",
        description="Semantic search for metrics/analytics tables",
        expected_behavior="Observe uses semantic search for metrics concepts.",
    ),
    Scenario(
        name="find_contract_tables",
        prompt="What tables store contract and subscription information?",
        description="Semantic search for contract/subscription data",
        expected_behavior="Observe uses semantic search for contract concepts.",
    ),
]


def run_warehouse_scenario(scenario: Scenario, timeout: int = 120) -> BenchmarkResult:
    """Run scenario using warehouse SQL approach (NO Observe MCP)."""
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
        "plugins": [
            {
                "name": "data",
                "source": str(temp_dir),
                "strict": False,
                "description": "Warehouse SQL benchmark (no Observe)",
                "version": "0.1.0",
                "mcpServers": {
                    # Only airflow MCP - NO observe MCP
                    "airflow": {
                        "command": "uvx",
                        "args": [
                            "astro-airflow-mcp@0.2.3",
                            "--transport",
                            "stdio",
                            "--airflow-project-dir",
                            "${PWD}",
                        ],
                    }
                },
            }
        ],
    }

    config_path = plugin_dir / "marketplace.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    prompt = f"""/data:analyzing-data-benchmark

{scenario.prompt}"""

    cmd = [
        "claude",
        "--print",
        "--model",
        "haiku",
        "--output-format",
        "json",
        "--plugin-dir",
        str(temp_dir),
        "--no-session-persistence",
        "--permission-mode",
        "bypassPermissions",
    ]

    env = os.environ.copy()

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
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
                error=f"Claude failed: {result.stderr[:200]}",
            )

        output = json.loads(result.stdout)

        return BenchmarkResult(
            approach="warehouse",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=output.get("duration_ms", elapsed_ms),
            num_turns=output.get("num_turns", 0),
            total_cost_usd=output.get("total_cost_usd", 0),
            result_text=output.get("result", ""),
            success=not output.get("is_error", False),
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


def run_observe_scenario(
    scenario: Scenario, org_id: str, timeout: int = 120
) -> BenchmarkResult:
    """Run scenario using Observe semantic search approach."""
    agents_root = Path(__file__).parent.parent
    observe_path = agents_root / "astro-observe-mcp"

    # Create temp plugin config
    temp_dir = Path(tempfile.mkdtemp(prefix="observe_benchmark_"))
    plugin_dir = temp_dir / ".claude-plugin"
    plugin_dir.mkdir(parents=True)

    # Copy skills directory so plugin can find them
    skills_src = agents_root / "skills"
    skills_dst = temp_dir / "skills"
    shutil.copytree(skills_src, skills_dst)

    config = {
        "name": "observe-benchmark",
        "owner": {"name": "Benchmark", "email": "benchmark@test.io"},
        "plugins": [
            {
                "name": "data",
                "source": str(temp_dir),
                "strict": False,
                "description": "Catalog-based asset discovery",
                "version": "0.1.0",
                "mcpServers": {
                    "observe": {
                        "command": "uv",
                        "args": [
                            "--directory",
                            str(observe_path),
                            "run",
                            "astro-observe-mcp",
                            "--org-id",
                            org_id,
                        ],
                    }
                },
            }
        ],
    }

    config_path = plugin_dir / "marketplace.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    prompt = f"""/data:analyzing-data-observe-benchmark

{scenario.prompt}"""

    cmd = [
        "claude",
        "--print",
        "--model",
        "haiku",
        "--output-format",
        "json",
        "--plugin-dir",
        str(temp_dir),
        "--no-session-persistence",
        "--permission-mode",
        "bypassPermissions",
    ]

    env = os.environ.copy()

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
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
                error=f"Claude failed: {result.stderr[:200]}",
            )

        output = json.loads(result.stdout)

        return BenchmarkResult(
            approach="observe",
            scenario=scenario.name,
            prompt=scenario.prompt,
            duration_ms=output.get("duration_ms", elapsed_ms),
            num_turns=output.get("num_turns", 0),
            total_cost_usd=output.get("total_cost_usd", 0),
            result_text=output.get("result", ""),
            success=not output.get("is_error", False),
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


def print_comparison(
    warehouse: BenchmarkResult, observe: BenchmarkResult, scenario: Scenario
):
    """Print side-by-side comparison."""
    print(f"\n{'─' * 70}")
    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"{'─' * 70}")

    print(f"\n{'Metric':<15} {'Warehouse':<20} {'Observe':<20} {'Winner'}")
    print(f"{'─' * 65}")

    # Time comparison
    w_time = f"{warehouse.duration_ms:.0f}ms" if warehouse.success else "FAILED"
    o_time = f"{observe.duration_ms:.0f}ms" if observe.success else "FAILED"
    if warehouse.success and observe.success:
        time_winner = (
            "Warehouse" if warehouse.duration_ms < observe.duration_ms else "Observe"
        )
        speedup = max(warehouse.duration_ms, observe.duration_ms) / min(
            warehouse.duration_ms, observe.duration_ms
        )
        time_winner += f" ({speedup:.1f}x)"
    else:
        time_winner = "-"
    print(f"{'Time':<15} {w_time:<20} {o_time:<20} {time_winner}")

    # Turns comparison
    w_turns = str(warehouse.num_turns) if warehouse.success else "-"
    o_turns = str(observe.num_turns) if observe.success else "-"
    if warehouse.success and observe.success:
        turns_winner = (
            "Warehouse" if warehouse.num_turns < observe.num_turns else "Observe"
        )
        if warehouse.num_turns == observe.num_turns:
            turns_winner = "Tie"
    else:
        turns_winner = "-"
    print(f"{'Turns':<15} {w_turns:<20} {o_turns:<20} {turns_winner}")

    # Cost comparison
    w_cost = f"${warehouse.total_cost_usd:.4f}" if warehouse.success else "-"
    o_cost = f"${observe.total_cost_usd:.4f}" if observe.success else "-"
    if warehouse.success and observe.success:
        cost_winner = (
            "Warehouse"
            if warehouse.total_cost_usd < observe.total_cost_usd
            else "Observe"
        )
    else:
        cost_winner = "-"
    print(f"{'Cost':<15} {w_cost:<20} {o_cost:<20} {cost_winner}")

    # Show expected behavior
    print(f"\n📋 Expected: {scenario.expected_behavior}")

    # Show result previews
    if warehouse.success:
        print("\n🔧 Warehouse result preview:")
        print(f"   {warehouse.result_text[:150]}...")
    if observe.success:
        print("\n🔍 Observe result preview:")
        print(f"   {observe.result_text[:150]}...")


def save_results(all_runs: list, org_id: str, output_path: str, total_runs: int):
    """Save results to file (called incrementally as scenarios complete)."""
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "org_id": org_id,
        "total_runs": total_runs,
        "completed_runs": len(all_runs),
        "runs": [
            {
                "run_number": run_idx + 1,
                "results": [
                    {
                        "scenario": s.name,
                        "description": s.description,
                        "expected_behavior": s.expected_behavior,
                        "warehouse": {
                            "prompt": w.prompt,
                            "success": w.success,
                            "duration_ms": w.duration_ms,
                            "num_turns": w.num_turns,
                            "cost": w.total_cost_usd,
                            "result_preview": w.result_text[:500] if w.success else None,
                            "error": w.error,
                        },
                        "observe": {
                            "prompt": o.prompt,
                            "success": o.success,
                            "duration_ms": o.duration_ms,
                            "num_turns": o.num_turns,
                            "cost": o.total_cost_usd,
                            "result_preview": o.result_text[:500] if o.success else None,
                            "error": o.error,
                        },
                    }
                    for w, o, s in run_results
                ],
            }
            for run_idx, run_results in enumerate(all_runs)
        ],
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Fair benchmark: Warehouse vs Observe")
    parser.add_argument("--org-id", required=True, help="Astro organization ID")
    parser.add_argument("--scenarios", nargs="+", help="Specific scenarios to run")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per scenario")
    parser.add_argument(
        "--output", default="fair_benchmark_results.json", help="Output file"
    )
    parser.add_argument(
        "--runs", type=int, default=1, help="Number of times to run all scenarios"
    )

    args = parser.parse_args()

    # Filter scenarios
    scenarios = SCENARIOS
    if args.scenarios:
        scenarios = [s for s in SCENARIOS if s.name in args.scenarios]

    print("=" * 70)
    print("FAIR BENCHMARK: Warehouse SQL vs Observe Semantic Search")
    print("=" * 70)
    print(f"\nScenarios: {len(scenarios)}")
    print(f"Runs: {args.runs}")
    print(f"Org ID: {args.org_id}")
    print("\nNote: Each approach gets a tailored prompt for its strengths.")

    all_runs = []  # List of runs, each run is a list of (warehouse, observe, scenario)
    save_lock = threading.Lock()

    for run_num in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"\n{'#' * 70}")
            print(f"# RUN {run_num}/{args.runs}")
            print(f"{'#' * 70}")

        # Run all scenarios and both approaches concurrently
        print(f"\n🚀 Running all {len(scenarios)} scenarios concurrently...")

        future_to_info = {}
        with ThreadPoolExecutor(max_workers=len(scenarios) * 2) as executor:
            for scenario in scenarios:
                # Submit both approaches for each scenario
                w_future = executor.submit(
                    run_warehouse_scenario, scenario, args.timeout
                )
                o_future = executor.submit(
                    run_observe_scenario, scenario, args.org_id, args.timeout
                )
                future_to_info[w_future] = ("warehouse", scenario)
                future_to_info[o_future] = ("observe", scenario)

            # Print progress as each completes
            scenario_results = {}
            for future in as_completed(future_to_info):
                approach, scenario = future_to_info[future]
                result = future.result()

                # Print completion message
                if result.success:
                    print(
                        f"  ✓ [{scenario.name}] {approach}: {result.duration_ms:.0f}ms, {result.num_turns} turns"
                    )
                else:
                    print(f"  ✗ [{scenario.name}] {approach}: {result.error}")

                # Store result
                if scenario.name not in scenario_results:
                    scenario_results[scenario.name] = {"scenario": scenario}
                scenario_results[scenario.name][approach] = result

        # Collect results for this run
        run_results = []
        for scenario in scenarios:
            sr = scenario_results[scenario.name]
            warehouse_result = sr["warehouse"]
            observe_result = sr["observe"]
            run_results.append((warehouse_result, observe_result, scenario))
            print_comparison(warehouse_result, observe_result, scenario)

        all_runs.append(run_results)

        # Save after each run completes
        with save_lock:
            save_results(all_runs, args.org_id, args.output, args.runs)
            print(f"\n💾 Progress saved (run {run_num}/{args.runs})")

    # Summary - aggregate across all runs
    print(f"\n{'=' * 70}")
    print("SUMMARY" + (f" (across {args.runs} runs)" if args.runs > 1 else ""))
    print(f"{'=' * 70}")

    w_wins = o_wins = ties = 0
    w_total_time = o_total_time = 0
    w_total_turns = o_total_turns = 0
    w_total_cost = o_total_cost = 0
    w_count = o_count = 0

    for run_results in all_runs:
        for w, o, s in run_results:
            if w.success and o.success:
                if w.duration_ms < o.duration_ms * 0.8:
                    w_wins += 1
                elif o.duration_ms < w.duration_ms * 0.8:
                    o_wins += 1
                else:
                    ties += 1

            if w.success:
                w_total_time += w.duration_ms
                w_total_turns += w.num_turns
                w_total_cost += w.total_cost_usd
                w_count += 1

            if o.success:
                o_total_time += o.duration_ms
                o_total_turns += o.num_turns
                o_total_cost += o.total_cost_usd
                o_count += 1

    print(f"\nSpeed Wins: Warehouse={w_wins}, Observe={o_wins}, Ties={ties}")

    if w_count > 0:
        print(f"\nWarehouse Averages ({w_count} successful across {args.runs} run(s)):")
        print(f"  Time: {w_total_time / w_count:.0f}ms")
        print(f"  Turns: {w_total_turns / w_count:.1f}")
        print(f"  Cost: ${w_total_cost / w_count:.4f}")

    if o_count > 0:
        print(f"\nObserve Averages ({o_count} successful across {args.runs} run(s)):")
        print(f"  Time: {o_total_time / o_count:.0f}ms")
        print(f"  Turns: {o_total_turns / o_count:.1f}")
        print(f"  Cost: ${o_total_cost / o_count:.4f}")

    print(f"\n💾 Final results saved to: {args.output}")


if __name__ == "__main__":
    main()
