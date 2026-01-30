"""Compare Catalog API (Observe MCP) vs Direct Warehouse Access (Data Plugin).

This benchmark compares two approaches for discovering data assets:
1. Catalog API: Uses Observe MCP to search centralized catalog
2. Warehouse: Uses data plugin to query INFORMATION_SCHEMA directly

Measures: Time, Tokens, Turns, Cost, Success Rate
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class BenchmarkResult:
    """Results from testing an approach."""
    approach: str
    model: str
    scenario: str
    prompt: str
    # Metrics
    duration_ms: float
    duration_api_ms: float
    num_turns: int
    total_cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    # Quality
    result_text: str
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Test scenarios for asset discovery
SCENARIOS = [
    {
        "name": "find_customer_tables",
        "prompt": "Find all tables related to customers in our data warehouse",
        "description": "Basic table discovery by keyword",
    },
    {
        "name": "list_all_tables",
        "prompt": "List all tables in the data warehouse",
        "description": "Full table enumeration",
    },
    {
        "name": "find_sales_tables",
        "prompt": "What tables contain sales or revenue data?",
        "description": "Semantic search for business concepts",
    },
    {
        "name": "table_ownership",
        "prompt": "Who owns the ORDERS table and when was it last updated?",
        "description": "Metadata and ownership lookup",
    },
]


def create_observe_only_config(org_id: str) -> Path:
    """Create MCP config with ONLY Observe MCP.

    Args:
        org_id: Astro organization ID

    Returns:
        Path to temporary MCP config file
    """
    # Point to local development version
    agents_root = Path(__file__).parent.parent
    observe_path = agents_root / "astro-observe-mcp"

    config = {
        "mcpServers": {
            "astro-observe": {
                "command": "uv",
                "args": [
                    "--directory",
                    str(observe_path),
                    "run",
                    "astro-observe-mcp",
                ],
                "env": {
                    "ASTRO_ORGANIZATION_ID": org_id
                }
            }
        }
    }

    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
    )
    json.dump(config, temp_file)
    temp_file.flush()
    temp_file.close()

    return Path(temp_file.name)


def run_with_catalog(
    prompt: str,
    model: str,
    org_id: str,
    timeout: int,
) -> dict[str, Any]:
    """Run prompt using Catalog API (Observe MCP only).

    Args:
        prompt: The prompt to run
        model: Model name
        org_id: Astro organization ID
        timeout: Timeout in seconds

    Returns:
        Parsed JSON output from Claude Code
    """
    # Create config with ONLY Observe MCP
    mcp_config = create_observe_only_config(org_id)

    try:
        cmd = [
            'claude',
            '--print',
            '--model', model,
            '--output-format', 'json',
            '--mcp-config', str(mcp_config),
            '--strict-mcp-config',  # ONLY use this config
            '--no-session-persistence',
            '--permission-mode', 'bypassPermissions',
            '--tools', 'default',  # Keep built-in tools
        ]

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Execution timed out after {timeout}s")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse output: {e}")
    finally:
        mcp_config.unlink(missing_ok=True)


def run_with_warehouse(
    prompt: str,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    """Run prompt using Warehouse access (data plugin).

    Args:
        prompt: The prompt to run
        model: Model name
        timeout: Timeout in seconds

    Returns:
        Parsed JSON output from Claude Code
    """
    # Use the data plugin which connects to Snowflake
    agents_root = Path(__file__).parent.parent
    plugin_dir = agents_root

    cmd = [
        'claude',
        '--print',
        '--model', model,
        '--output-format', 'json',
        '--plugin-dir', str(plugin_dir),
        '--no-session-persistence',
        '--permission-mode', 'bypassPermissions',
        '--tools', 'default',  # Keep built-in tools
    ]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Execution timed out after {timeout}s")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse output: {e}")


def parse_result(
    output: dict[str, Any],
    approach: str,
    model: str,
    scenario: str,
    prompt: str,
) -> BenchmarkResult:
    """Parse Claude Code JSON output."""
    usage = output.get('usage', {})

    return BenchmarkResult(
        approach=approach,
        model=model,
        scenario=scenario,
        prompt=prompt,
        duration_ms=output.get('duration_ms', 0),
        duration_api_ms=output.get('duration_api_ms', 0),
        num_turns=output.get('num_turns', 0),
        total_cost_usd=output.get('total_cost_usd', 0),
        input_tokens=usage.get('input_tokens', 0),
        output_tokens=usage.get('output_tokens', 0),
        cache_creation_tokens=usage.get('cache_creation_input_tokens', 0),
        cache_read_tokens=usage.get('cache_read_input_tokens', 0),
        result_text=output.get('result', ''),
        success=not output.get('is_error', False),
        metadata={
            'session_id': output.get('session_id'),
        },
    )


def run_benchmark(
    model: str,
    org_id: str,
    test_catalog: bool,
    test_warehouse: bool,
    timeout: int,
) -> list[BenchmarkResult]:
    """Run benchmark comparing approaches."""
    results = []

    # Test catalog approach
    if test_catalog:
        print(f"\n{'='*80}")
        print(f"Testing: Catalog API (Observe MCP)")
        print(f"Model: {model}")
        print(f"{'='*80}")

        for scenario in SCENARIOS:
            print(f"\n📝 {scenario['name']}: {scenario['description']}")
            print(f"   Prompt: {scenario['prompt'][:80]}...")

            try:
                output = run_with_catalog(
                    prompt=scenario['prompt'],
                    model=model,
                    org_id=org_id,
                    timeout=timeout,
                )

                result = parse_result(output, "catalog", model, scenario['name'], scenario['prompt'])
                results.append(result)

                print(f"   ✓ Completed in {result.duration_ms:.0f}ms")
                print(f"     Turns: {result.num_turns}, Cost: ${result.total_cost_usd:.6f}")
                print(f"     Result: {result.result_text[:100]}...")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                results.append(BenchmarkResult(
                    approach="catalog",
                    model=model,
                    scenario=scenario['name'],
                    prompt=scenario['prompt'],
                    duration_ms=0,
                    duration_api_ms=0,
                    num_turns=0,
                    total_cost_usd=0,
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    result_text='',
                    success=False,
                    error=str(e),
                ))

    # Test warehouse approach
    if test_warehouse:
        print(f"\n{'='*80}")
        print(f"Testing: Warehouse Direct (Data Plugin)")
        print(f"Model: {model}")
        print(f"{'='*80}")

        for scenario in SCENARIOS:
            print(f"\n📝 {scenario['name']}: {scenario['description']}")
            print(f"   Prompt: {scenario['prompt'][:80]}...")

            try:
                output = run_with_warehouse(
                    prompt=scenario['prompt'],
                    model=model,
                    timeout=timeout,
                )

                result = parse_result(output, "warehouse", model, scenario['name'], scenario['prompt'])
                results.append(result)

                print(f"   ✓ Completed in {result.duration_ms:.0f}ms")
                print(f"     Turns: {result.num_turns}, Cost: ${result.total_cost_usd:.6f}")
                print(f"     Result: {result.result_text[:100]}...")

            except Exception as e:
                print(f"   ❌ Error: {e}")
                results.append(BenchmarkResult(
                    approach="warehouse",
                    model=model,
                    scenario=scenario['name'],
                    prompt=scenario['prompt'],
                    duration_ms=0,
                    duration_api_ms=0,
                    num_turns=0,
                    total_cost_usd=0,
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_tokens=0,
                    cache_read_tokens=0,
                    result_text='',
                    success=False,
                    error=str(e),
                ))

    return results


def print_summary(results: list[BenchmarkResult]):
    """Print comparison summary."""
    print("\n" + "="*80)
    print("BENCHMARK SUMMARY: Catalog API vs Warehouse Direct")
    print("="*80)

    approaches = sorted(set(r.approach for r in results))
    successful = [r for r in results if r.success]

    if not successful:
        print("\n⚠️  No successful results")
        return

    print("\n📊 Performance Comparison:")
    print("-" * 80)
    print(f"{'Approach':<20} {'Avg Time':<12} {'Avg Turns':<12} {'Avg Cost':<12} {'Success'}")
    print("-" * 80)

    for approach in approaches:
        approach_results = [r for r in results if r.approach == approach]
        successful = [r for r in approach_results if r.success]

        if not successful:
            print(f"{approach:<20} {'FAILED':<12}")
            continue

        avg_time = sum(r.duration_ms for r in successful) / len(successful)
        avg_turns = sum(r.num_turns for r in successful) / len(successful)
        avg_cost = sum(r.total_cost_usd for r in successful) / len(successful)
        success_rate = len(successful) / len(approach_results)

        print(
            f"{approach:<20} "
            f"{avg_time:>10.0f}ms "
            f"{avg_turns:>11.1f} "
            f"${avg_cost:>10.6f} "
            f"{success_rate:>6.0%}"
        )

    # Speed comparison
    if len(approaches) == 2:
        catalog_results = [r for r in successful if r.approach == 'catalog']
        warehouse_results = [r for r in successful if r.approach == 'warehouse']

        if catalog_results and warehouse_results:
            catalog_avg = sum(r.duration_ms for r in catalog_results) / len(catalog_results)
            warehouse_avg = sum(r.duration_ms for r in warehouse_results) / len(warehouse_results)

            print("\n⚡ Speed Comparison:")
            print("-" * 80)
            if catalog_avg < warehouse_avg:
                speedup = warehouse_avg / catalog_avg
                print(f"Catalog API is {speedup:.2f}x faster than Warehouse Direct")
            else:
                speedup = catalog_avg / warehouse_avg
                print(f"Warehouse Direct is {speedup:.2f}x faster than Catalog API")


def main():
    """Run the catalog vs warehouse benchmark."""
    parser = argparse.ArgumentParser(
        description="Compare Catalog API vs Direct Warehouse Access"
    )
    parser.add_argument(
        '--model',
        default='haiku',
        help='Model to test (default: haiku)',
    )
    parser.add_argument(
        '--org-id',
        required=True,
        help='Astro organization ID',
    )
    parser.add_argument(
        '--catalog-only',
        action='store_true',
        help='Test only catalog approach',
    )
    parser.add_argument(
        '--warehouse-only',
        action='store_true',
        help='Test only warehouse approach',
    )
    parser.add_argument(
        '--output',
        default='catalog_vs_warehouse_results.json',
        help='Output file',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=180,
        help='Timeout per execution in seconds',
    )

    args = parser.parse_args()

    # Determine what to test
    test_catalog = not args.warehouse_only
    test_warehouse = not args.catalog_only

    print("="*80)
    print("CATALOG API vs WAREHOUSE DIRECT BENCHMARK")
    print("="*80)
    print(f"\nModel: {args.model}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print(f"Org ID: {args.org_id}")
    print(f"\nTesting:")
    if test_catalog:
        print("  ✓ Catalog API (Observe MCP)")
    if test_warehouse:
        print("  ✓ Warehouse Direct (Data Plugin)")

    # Run benchmark
    results = run_benchmark(
        model=args.model,
        org_id=args.org_id,
        test_catalog=test_catalog,
        test_warehouse=test_warehouse,
        timeout=args.timeout,
    )

    # Print summary
    print_summary(results)

    # Save results
    results_data = [
        {
            'approach': r.approach,
            'model': r.model,
            'scenario': r.scenario,
            'prompt': r.prompt,
            'duration_ms': r.duration_ms,
            'duration_api_ms': r.duration_api_ms,
            'num_turns': r.num_turns,
            'total_cost_usd': r.total_cost_usd,
            'input_tokens': r.input_tokens,
            'output_tokens': r.output_tokens,
            'cache_creation_tokens': r.cache_creation_tokens,
            'cache_read_tokens': r.cache_read_tokens,
            'result_text': r.result_text[:500],
            'success': r.success,
            'error': r.error,
            'metadata': r.metadata,
            'timestamp': datetime.now().isoformat(),
        }
        for r in results
    ]

    with open(args.output, 'w') as f:
        json.dump(results_data, f, indent=2)

    print(f"\n💾 Results saved to: {args.output}")


if __name__ == '__main__':
    main()
