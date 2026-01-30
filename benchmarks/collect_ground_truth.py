"""Collect ground truth data from the actual Astro Cloud catalog.

This script queries the real catalog and warehouse to establish expected
results for benchmark validation.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_claude_query(prompt: str, timeout: int = 60) -> dict:
    """Run a query through Claude Code with observe MCP.

    Args:
        prompt: The query to run
        timeout: Timeout in seconds

    Returns:
        Parsed JSON output
    """
    agents_root = Path(__file__).parent.parent

    cmd = [
        'claude',
        '--print',
        '--model', 'haiku',  # Fast model for ground truth collection
        '--output-format', 'json',
        '--plugin-dir', str(agents_root),
        '--no-session-persistence',
        '--permission-mode', 'bypassPermissions',
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
        raise RuntimeError(f"Query timed out after {timeout}s")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse output: {e}")


def collect_scenario_data(scenario_name: str, scenario_config: dict) -> dict:
    """Collect ground truth for a single scenario.

    Args:
        scenario_name: Name of the scenario
        scenario_config: Scenario configuration

    Returns:
        Updated scenario config with actual results
    """
    print(f"\n{'='*80}")
    print(f"Collecting: {scenario_name}")
    print(f"{'='*80}")

    prompt = scenario_config['prompt']
    print(f"Prompt: {prompt}")

    try:
        print("Running query...")
        output = run_claude_query(prompt)

        result_text = output.get('result', '')
        print(f"✓ Got response ({len(result_text)} chars)")
        print(f"Preview: {result_text[:200]}...")

        # Store the actual result
        scenario_config['actual_response'] = result_text
        scenario_config['collected_at'] = datetime.now().isoformat()
        scenario_config['success'] = not output.get('is_error', False)

        # Try to extract structured data from the response
        # This is a best-effort extraction - may need manual refinement
        if 'customer' in scenario_name.lower():
            # Count table mentions
            table_count = result_text.lower().count('table')
            scenario_config['expected_results']['total_tables'] = table_count

        return scenario_config

    except Exception as e:
        print(f"❌ Error: {e}")
        scenario_config['collection_error'] = str(e)
        return scenario_config


def main():
    """Collect ground truth data for all scenarios."""
    print("="*80)
    print("GROUND TRUTH COLLECTION")
    print("="*80)
    print("\nThis script queries the actual catalog to establish benchmark")
    print("ground truth. Ensure you're authenticated with 'astro login'.\n")

    # Load template
    template_path = Path(__file__).parent / 'ground_truth_template.json'
    output_path = Path(__file__).parent / 'ground_truth_data.json'

    if not template_path.exists():
        print(f"❌ Template not found: {template_path}")
        sys.exit(1)

    with open(template_path) as f:
        ground_truth = json.load(f)

    # Update metadata
    ground_truth['metadata']['queries_run_at'] = datetime.now().isoformat()

    # Collect data for each scenario
    scenarios = ground_truth['scenarios']

    for scenario_name, scenario_config in scenarios.items():
        scenarios[scenario_name] = collect_scenario_data(scenario_name, scenario_config)

    # Save results
    with open(output_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✓ Ground truth collected and saved to: {output_path}")
    print(f"{'='*80}")
    print("\nNext steps:")
    print("1. Review the collected data in ground_truth_data.json")
    print("2. Manually refine any structured data extraction")
    print("3. Use this as reference for validating benchmark results")


if __name__ == '__main__':
    main()
