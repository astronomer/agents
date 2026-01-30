"""Benchmark Claude Code performance using real execution.

This benchmark runs prompts through the actual Claude Code CLI,
measuring real-world performance with the Observe MCP.

Key advantages over API-based benchmarks:
- Uses real Claude Code infrastructure
- Measures actual MCP overhead
- Tests real Observe API integration
- Captures real-world token usage including system prompts
- Validates result quality against ground truth
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from ground_truth_validator import validate_benchmark_results, ValidationResult
    HAS_VALIDATOR = True
except ImportError:
    HAS_VALIDATOR = False
    ValidationResult = None


@dataclass
class BenchmarkResult:
    """Results from a Claude Code execution."""
    model: str
    scenario: str
    prompt: str
    # From Claude Code JSON output
    duration_ms: float
    duration_api_ms: float
    num_turns: int
    total_cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    # Additional metadata
    result_text: str
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Test prompts for asset discovery
PROMPTS = [
    {
        "name": "simple_keyword_search",
        "prompt": "Find all tables related to customers in our data warehouse",
        "description": "Basic keyword search",
    },
    {
        "name": "filtered_snowflake_search",
        "prompt": "Show me all Snowflake tables that contain 'revenue' in the name",
        "description": "Filtered search with asset type",
    },
    {
        "name": "cross_warehouse_search",
        "prompt": "What tables do we have across Snowflake, Databricks, and BigQuery that store sales data?",
        "description": "Cross-warehouse discovery",
    },
    {
        "name": "lineage_discovery",
        "prompt": "Find all the Airflow DAGs that write to customer tables",
        "description": "Lineage and dependency discovery",
    },
    {
        "name": "detailed_inspection",
        "prompt": "Tell me about the customers table - who owns it, when was it last updated, and what deployment does it belong to?",
        "description": "Detailed asset inspection",
    },
]


def create_mcp_config(org_id: str | None = None) -> Path:
    """Create MCP config file for Observe.

    Args:
        org_id: Optional organization ID to pass to MCP server

    Returns:
        Path to temporary MCP config file
    """
    config = {
        "mcpServers": {
            "astro-observe": {
                "command": "uvx",
                "args": ["astro-observe-mcp"],
            }
        }
    }

    if org_id:
        config["mcpServers"]["astro-observe"]["env"] = {
            "ASTRO_ORGANIZATION_ID": org_id
        }

    # Write to temp file
    temp_file = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
    )
    json.dump(config, temp_file)
    temp_file.flush()
    temp_file.close()

    return Path(temp_file.name)


def run_claude_code(
    prompt: str,
    model: str,
    mcp_config_path: Path,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run a prompt through Claude Code and capture metrics.

    Args:
        prompt: The prompt to run
        model: Model name (haiku, sonnet, opus)
        mcp_config_path: Path to MCP config file
        timeout_seconds: Timeout for execution

    Returns:
        Parsed JSON output from Claude Code
    """
    cmd = [
        'claude',
        '--print',
        '--model', model,
        '--output-format', 'json',
        '--mcp-config', str(mcp_config_path),
        '--no-session-persistence',  # Don't save sessions
        '--permission-mode', 'bypassPermissions',  # Auto-approve MCP tool use
    ]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {result.stderr}")

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Execution timed out after {timeout_seconds}s")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Claude Code output: {e}\nOutput: {result.stdout[:500]}")


def parse_result(output: dict[str, Any], model: str, scenario: str, prompt: str) -> BenchmarkResult:
    """Parse Claude Code JSON output into BenchmarkResult.

    Args:
        output: Parsed JSON from Claude Code
        model: Model name
        scenario: Scenario name
        prompt: Original prompt

    Returns:
        Structured benchmark result
    """
    usage = output.get('usage', {})
    model_usage = output.get('modelUsage', {})

    # Extract model-specific usage (there's one entry per model)
    model_specific = next(iter(model_usage.values()), {})

    return BenchmarkResult(
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
            'model_specific_usage': model_specific,
        },
    )


def run_benchmark(
    models: list[str],
    org_id: str | None = None,
    timeout: int = 120,
) -> list[BenchmarkResult]:
    """Run benchmark across all models and prompts.

    Args:
        models: List of model names to test
        org_id: Optional Astro organization ID
        timeout: Timeout per execution

    Returns:
        List of benchmark results
    """
    results = []

    # Create MCP config
    print("Setting up MCP configuration...")
    mcp_config = create_mcp_config(org_id)
    print(f"MCP config: {mcp_config}")

    try:
        for model in models:
            print(f"\n{'='*80}")
            print(f"Testing Model: {model}")
            print(f"{'='*80}")

            for scenario in PROMPTS:
                print(f"\n📝 {scenario['name']}: {scenario['description']}")
                print(f"   Prompt: {scenario['prompt'][:80]}...")

                try:
                    start = time.time()
                    output = run_claude_code(
                        prompt=scenario['prompt'],
                        model=model,
                        mcp_config_path=mcp_config,
                        timeout_seconds=timeout,
                    )
                    elapsed = (time.time() - start) * 1000

                    result = parse_result(output, model, scenario['name'], scenario['prompt'])
                    results.append(result)

                    print(f"   ✓ Completed in {result.duration_ms:.0f}ms (total: {elapsed:.0f}ms)")
                    print(f"     Turns: {result.num_turns}")
                    print(f"     Tokens: {result.input_tokens} in, {result.output_tokens} out")
                    print(f"     Cache: {result.cache_creation_tokens} created, {result.cache_read_tokens} read")
                    print(f"     Cost: ${result.total_cost_usd:.6f}")
                    print(f"     Result preview: {result.result_text[:100]}...")

                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    results.append(BenchmarkResult(
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

    finally:
        # Cleanup MCP config
        mcp_config.unlink(missing_ok=True)

    return results


def print_validation_summary(validations: list[ValidationResult]):
    """Print quality metrics summary."""
    print("\n" + "="*80)
    print("QUALITY METRICS - Ground Truth Validation")
    print("="*80)

    models = sorted(set(v.model for v in validations))

    print("\n🎯 Accuracy by Model:")
    print("-" * 80)
    print(f"{'Model':<15} {'Accuracy':<12} {'Precision':<12} {'Recall':<12} {'F1 Score'}")
    print("-" * 80)

    for model in models:
        model_validations = [v for v in validations if v.model == model]

        if not model_validations:
            continue

        avg_accuracy = sum(v.accuracy for v in model_validations) / len(model_validations)
        avg_precision = sum(v.precision for v in model_validations) / len(model_validations)
        avg_recall = sum(v.recall for v in model_validations) / len(model_validations)
        avg_f1 = sum(v.f1_score for v in model_validations) / len(model_validations)

        print(
            f"{model:<15} "
            f"{avg_accuracy:>10.1%}  "
            f"{avg_precision:>10.1%}  "
            f"{avg_recall:>10.1%}  "
            f"{avg_f1:>10.3f}"
        )

    print("\n📋 Detailed Results by Scenario:")
    print("-" * 80)

    scenarios = sorted(set(v.scenario for v in validations))
    for scenario in scenarios:
        print(f"\n{scenario}:")
        for model in models:
            model_val = next((v for v in validations if v.scenario == scenario and v.model == model), None)
            if not model_val:
                continue

            print(f"  {model}:")
            print(f"    Accuracy: {model_val.accuracy:.1%} | Precision: {model_val.precision:.1%} | Recall: {model_val.recall:.1%}")
            print(f"    True Positives: {len(model_val.true_positives)} | False Positives: {len(model_val.false_positives)} | False Negatives: {len(model_val.false_negatives)}")

            if model_val.false_negatives:
                print(f"    ⚠️  Missed: {', '.join(model_val.false_negatives[:5])}")
            if model_val.false_positives:
                print(f"    ⚠️  Incorrect: {', '.join(model_val.false_positives[:5])}")
            if model_val.notes:
                print(f"    Note: {model_val.notes}")


def print_summary(results: list[BenchmarkResult], validations: list[ValidationResult] | None = None):
    """Print summary comparison across models."""
    print("\n" + "="*80)
    print("BENCHMARK SUMMARY - Claude Code Real Execution")
    print("="*80)

    models = sorted(set(r.model for r in results))
    successful_results = [r for r in results if r.success]

    if not successful_results:
        print("\n⚠️  No successful results to summarize")
        return

    print("\n📊 Performance Comparison:")
    print("-" * 80)
    print(f"{'Model':<15} {'Avg Time':<12} {'Avg Turns':<12} {'Avg Cost':<12} {'Success Rate'}")
    print("-" * 80)

    for model in models:
        model_results = [r for r in results if r.model == model]
        successful = [r for r in model_results if r.success]

        if not successful:
            success_rate = 0
            print(f"{model:<15} {'N/A':<12} {'N/A':<12} {'N/A':<12} {success_rate:>11.0%}")
            continue

        avg_time = sum(r.duration_ms for r in successful) / len(successful)
        avg_turns = sum(r.num_turns for r in successful) / len(successful)
        avg_cost = sum(r.total_cost_usd for r in successful) / len(successful)
        success_rate = len(successful) / len(model_results)

        print(
            f"{model:<15} "
            f"{avg_time:>10.0f}ms "
            f"{avg_turns:>11.1f} "
            f"${avg_cost:>10.6f} "
            f"{success_rate:>11.0%}"
        )

    print("\n💰 Total Cost by Model:")
    print("-" * 80)
    for model in models:
        model_results = [r for r in results if r.model == model and r.success]
        total_cost = sum(r.total_cost_usd for r in model_results)
        print(f"{model:<15} ${total_cost:>10.6f}")

    print("\n🎯 Token Usage by Model:")
    print("-" * 80)
    for model in models:
        model_results = [r for r in results if r.model == model and r.success]
        if not model_results:
            continue
        total_input = sum(r.input_tokens for r in model_results)
        total_output = sum(r.output_tokens for r in model_results)
        total_cache_create = sum(r.cache_creation_tokens for r in model_results)
        total_cache_read = sum(r.cache_read_tokens for r in model_results)
        print(
            f"{model:<15} "
            f"In: {total_input:>8,}  "
            f"Out: {total_output:>8,}  "
            f"Cache: {total_cache_create:>8,} created, {total_cache_read:>8,} read"
        )

    print("\n⚡ Real vs API Time:")
    print("-" * 80)
    print("(duration_ms includes all Claude Code overhead, duration_api_ms is pure API time)")
    for model in models:
        model_results = [r for r in results if r.model == model and r.success]
        if not model_results:
            continue
        avg_total = sum(r.duration_ms for r in model_results) / len(model_results)
        avg_api = sum(r.duration_api_ms for r in model_results) / len(model_results)
        overhead_pct = ((avg_total - avg_api) / avg_total * 100) if avg_total > 0 else 0
        print(
            f"{model:<15} "
            f"Total: {avg_total:>8.0f}ms  "
            f"API: {avg_api:>8.0f}ms  "
            f"Overhead: {overhead_pct:>5.1f}%"
        )


def main():
    """Run the Claude Code benchmark."""
    parser = argparse.ArgumentParser(
        description="Benchmark Claude Code with real Observe MCP execution"
    )
    parser.add_argument(
        '--models',
        nargs='+',
        default=['haiku', 'sonnet'],
        help='Models to test (default: haiku sonnet)',
    )
    parser.add_argument(
        '--org-id',
        help='Astro organization ID (optional, for real MCP calls)',
    )
    parser.add_argument(
        '--output',
        default='claude_code_benchmark_results.json',
        help='Output file (default: claude_code_benchmark_results.json)',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=120,
        help='Timeout per execution in seconds (default: 120)',
    )
    parser.add_argument(
        '--ground-truth',
        help='Path to ground truth JSON file for validation (optional)',
    )

    args = parser.parse_args()

    # Check if ground truth validation is available
    if args.ground_truth and not HAS_VALIDATOR:
        print("\n⚠️  Warning: ground_truth_validator.py not found. Validation disabled.")
        args.ground_truth = None

    print("="*80)
    print("CLAUDE CODE BENCHMARK - Real Execution with Observe MCP")
    print("="*80)
    print(f"\nTesting models: {', '.join(args.models)}")
    print(f"Scenarios: {len(PROMPTS)}")
    print(f"Org ID: {args.org_id or 'Not specified (will use astro CLI context)'}")
    print(f"Timeout: {args.timeout}s per scenario")

    # Check if Claude Code is available
    try:
        subprocess.run(['claude', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n❌ Error: 'claude' command not found")
        print("Please install Claude Code: https://code.claude.com")
        sys.exit(1)

    # Check if observe MCP is available
    try:
        subprocess.run(['uvx', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n⚠️  Warning: 'uvx' not found. The observe MCP may not work.")

    # Run benchmarks
    results = run_benchmark(
        models=args.models,
        org_id=args.org_id,
        timeout=args.timeout,
    )

    # Validate against ground truth if provided
    validations = None
    if args.ground_truth:
        ground_truth_path = Path(args.ground_truth)
        if ground_truth_path.exists():
            print("\n" + "="*80)
            print("VALIDATING RESULTS AGAINST GROUND TRUTH")
            print("="*80)

            try:
                results_for_validation = [
                    {
                        'model': r.model,
                        'scenario': r.scenario,
                        'result_text': r.result_text,
                    }
                    for r in results if r.success
                ]

                validations = validate_benchmark_results(results_for_validation, ground_truth_path)
                print(f"✓ Validated {len(validations)} results")

            except Exception as e:
                print(f"❌ Validation failed: {e}")
        else:
            print(f"\n⚠️  Ground truth file not found: {ground_truth_path}")

    # Print summaries
    print_summary(results, validations)

    if validations:
        print_validation_summary(validations)

    # Save results with validation metrics
    results_data = []
    for r in results:
        result_dict = {
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
            'result_text': r.result_text[:500],  # Truncate for storage
            'success': r.success,
            'error': r.error,
            'metadata': r.metadata,
            'timestamp': datetime.now().isoformat(),
        }

        # Add validation metrics if available
        if validations:
            matching_validation = next(
                (v for v in validations if v.scenario == r.scenario and v.model == r.model),
                None
            )
            if matching_validation:
                result_dict['validation'] = {
                    'accuracy': matching_validation.accuracy,
                    'precision': matching_validation.precision,
                    'recall': matching_validation.recall,
                    'f1_score': matching_validation.f1_score,
                    'true_positives_count': len(matching_validation.true_positives),
                    'false_positives_count': len(matching_validation.false_positives),
                    'false_negatives_count': len(matching_validation.false_negatives),
                    'notes': matching_validation.notes,
                }

        results_data.append(result_dict)

    # Save combined results
    output_data = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'models': args.models,
            'scenarios': len(PROMPTS),
            'ground_truth_used': args.ground_truth is not None,
        },
        'results': results_data,
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n💾 Results saved to: {args.output}")


if __name__ == '__main__':
    main()
