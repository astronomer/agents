"""Interactive ground truth collection.

Run this with Claude Code to interactively collect ground truth data
from the actual Astro Cloud catalog and Airflow instance.

Usage:
    claude --plugin-dir ../.. --run collect_ground_truth_interactive.py
"""

import json
from datetime import datetime
from pathlib import Path


def main():
    """Guide through ground truth collection."""
    print("="*80)
    print("GROUND TRUTH COLLECTION - Interactive Mode")
    print("="*80)
    print("\nThis script will help Claude Code query your catalog and collect")
    print("ground truth data for benchmark validation.\n")

    # Load template
    template_path = Path(__file__).parent / 'ground_truth_template.json'

    if not template_path.exists():
        print(f"❌ Template not found: {template_path}")
        print("Run this script from the benchmarks/ directory.")
        return

    with open(template_path) as f:
        ground_truth = json.load(f)

    print("Template loaded. Starting collection...")
    print("\n" + "="*80)

    # Instructions for Claude
    print("\n📝 INSTRUCTIONS FOR CLAUDE:")
    print("-" * 80)
    print("""
To collect ground truth data, Claude should:

1. For each scenario below, run the appropriate MCP tool queries
2. Record the actual results (table names, DAG names, metadata)
3. Populate the ground_truth data structure
4. Save to ground_truth_data.json

SCENARIOS TO COLLECT:
""")

    scenarios = ground_truth['scenarios']
    for i, (scenario_name, scenario_config) in enumerate(scenarios.items(), 1):
        print(f"\n{i}. {scenario_name}")
        print(f"   Prompt: {scenario_config['prompt']}")
        print(f"   Catalog Query: {json.dumps(scenario_config.get('catalog_query', {}), indent=6)}")

    print("\n" + "="*80)
    print("\nClaude will now collect the data...")
    print("=" * 80)

    # At this point, Claude (the assistant) should take over and:
    # 1. Use mcp__plugin_data_observe__search_assets for table scenarios
    # 2. Use mcp__plugin_data_airflow tools for DAG scenarios
    # 3. Populate the ground_truth structure
    # 4. Save to ground_truth_data.json

    return ground_truth


if __name__ == '__main__':
    ground_truth = main()

    print("\n\n⚠️  ATTENTION CLAUDE:")
    print("-" * 80)
    print("Please now collect the ground truth data by:")
    print("1. Running the appropriate MCP queries for each scenario")
    print("2. Extracting table/DAG names from the results")
    print("3. Populating the expected_results in the template")
    print("4. Saving to ground_truth_data.json")
    print("\nStart with scenario 1: simple_keyword_search")
    print("Query: search_assets(search='customer')")
