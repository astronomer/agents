#!/usr/bin/env python3
"""Generate ground truth for benchmark validation.

This script queries the warehouse directly to get expected results
for each benchmark scenario. Run this once to generate ground_truth.json.

Usage:
    # Using the analyzing-data kernel
    uv run ground_truth.py --use-kernel

    # Or provide connection details directly
    uv run ground_truth.py --account xxx --user xxx --password xxx --database HQ
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class GroundTruth:
    """Ground truth for a scenario."""
    scenario: str
    description: str
    query: str
    tables: list[dict]
    total_count: int
    generated_at: str


def run_sql_via_kernel(query: str) -> list[dict]:
    """Execute SQL using the analyzing-data kernel."""
    # Ensure kernel is running
    skill_dir = Path(__file__).parent.parent / "skills" / "analyzing-data"

    # Start kernel if needed
    subprocess.run(
        ["uv", "run", "scripts/cli.py", "ensure"],
        cwd=skill_dir,
        capture_output=True,
    )

    # Execute query and get results as JSON
    code = f'''
import json
df = run_sql("""{query}""", limit=10000)
# Convert to list of dicts
records = df.to_dicts() if hasattr(df, 'to_dicts') else df.to_dict('records')
print("__RESULTS_START__")
print(json.dumps(records))
print("__RESULTS_END__")
'''

    result = subprocess.run(
        ["uv", "run", "scripts/cli.py", "exec", code],
        cwd=skill_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Query failed: {result.stderr}")

    # Parse results
    output = result.stdout
    start = output.find("__RESULTS_START__")
    end = output.find("__RESULTS_END__")

    if start == -1 or end == -1:
        raise RuntimeError(f"Could not parse results: {output}")

    json_str = output[start + len("__RESULTS_START__"):end].strip()
    return json.loads(json_str)


def generate_ground_truth_kernel() -> dict[str, GroundTruth]:
    """Generate ground truth using the kernel."""
    scenarios = {}

    print("Generating ground truth via kernel...")

    # Scenario 1: Find customer tables
    print("  1. find_customer_tables...")
    query = """
        SELECT table_schema, table_name
        FROM HQ.INFORMATION_SCHEMA.TABLES
        WHERE table_type = 'BASE TABLE'
          AND (LOWER(table_name) LIKE '%customer%' OR LOWER(table_name) LIKE '%cust%')
        ORDER BY table_schema, table_name
    """
    try:
        results = run_sql_via_kernel(query)
        scenarios["find_customer_tables"] = GroundTruth(
            scenario="find_customer_tables",
            description="Find all tables with 'customer' or 'cust' in the name",
            query=query.strip(),
            tables=[{"schema": r.get("TABLE_SCHEMA", r.get("table_schema")),
                    "name": r.get("TABLE_NAME", r.get("table_name"))} for r in results],
            total_count=len(results),
            generated_at=datetime.now().isoformat(),
        )
        print(f"     Found {len(results)} tables")
    except Exception as e:
        print(f"     Error: {e}")

    # Scenario 2: List Snowflake tables (first 50)
    print("  2. list_snowflake_tables...")
    query = """
        SELECT table_schema, table_name
        FROM HQ.INFORMATION_SCHEMA.TABLES
        WHERE table_type = 'BASE TABLE'
        ORDER BY table_schema, table_name
        LIMIT 50
    """
    try:
        results = run_sql_via_kernel(query)
        scenarios["list_snowflake_tables"] = GroundTruth(
            scenario="list_snowflake_tables",
            description="List first 50 Snowflake tables",
            query=query.strip(),
            tables=[{"schema": r.get("TABLE_SCHEMA", r.get("table_schema")),
                    "name": r.get("TABLE_NAME", r.get("table_name"))} for r in results],
            total_count=len(results),
            generated_at=datetime.now().isoformat(),
        )
        print(f"     Found {len(results)} tables")
    except Exception as e:
        print(f"     Error: {e}")

    # Scenario 3: Tables with email column
    print("  3. tables_with_email_column...")
    query = """
        SELECT DISTINCT table_schema, table_name
        FROM HQ.INFORMATION_SCHEMA.COLUMNS
        WHERE LOWER(column_name) LIKE '%email%'
        ORDER BY table_schema, table_name
    """
    try:
        results = run_sql_via_kernel(query)
        scenarios["tables_with_email_column"] = GroundTruth(
            scenario="tables_with_email_column",
            description="Find tables containing an email column",
            query=query.strip(),
            tables=[{"schema": r.get("TABLE_SCHEMA", r.get("table_schema")),
                    "name": r.get("TABLE_NAME", r.get("table_name"))} for r in results],
            total_count=len(results),
            generated_at=datetime.now().isoformat(),
        )
        print(f"     Found {len(results)} tables")
    except Exception as e:
        print(f"     Error: {e}")

    # Scenario 4: List schemas
    print("  4. list_schemas...")
    query = """
        SELECT schema_name
        FROM HQ.INFORMATION_SCHEMA.SCHEMATA
        WHERE schema_name NOT IN ('INFORMATION_SCHEMA', 'PUBLIC')
        ORDER BY schema_name
    """
    try:
        results = run_sql_via_kernel(query)
        scenarios["list_schemas"] = GroundTruth(
            scenario="list_schemas",
            description="List all schemas in the database",
            query=query.strip(),
            tables=[{"name": r.get("SCHEMA_NAME", r.get("schema_name"))} for r in results],
            total_count=len(results),
            generated_at=datetime.now().isoformat(),
        )
        print(f"     Found {len(results)} schemas")
    except Exception as e:
        print(f"     Error: {e}")

    # Scenario 5: Count tables per schema
    print("  5. tables_per_schema...")
    query = """
        SELECT table_schema, COUNT(*) as table_count
        FROM HQ.INFORMATION_SCHEMA.TABLES
        WHERE table_type = 'BASE TABLE'
        GROUP BY table_schema
        ORDER BY table_count DESC
    """
    try:
        results = run_sql_via_kernel(query)
        scenarios["tables_per_schema"] = GroundTruth(
            scenario="tables_per_schema",
            description="Count of tables per schema",
            query=query.strip(),
            tables=[{"schema": r.get("TABLE_SCHEMA", r.get("table_schema")),
                    "count": r.get("TABLE_COUNT", r.get("table_count"))} for r in results],
            total_count=sum(r.get("TABLE_COUNT", r.get("table_count", 0)) for r in results),
            generated_at=datetime.now().isoformat(),
        )
        print(f"     Found {len(results)} schemas with tables")
    except Exception as e:
        print(f"     Error: {e}")

    return scenarios


def save_ground_truth(scenarios: dict[str, GroundTruth], output_path: Path):
    """Save ground truth to JSON file."""
    data = {
        "generated_at": datetime.now().isoformat(),
        "scenarios": {}
    }

    for name, gt in scenarios.items():
        data["scenarios"][name] = {
            "description": gt.description,
            "query": gt.query,
            "tables": gt.tables,
            "total_count": gt.total_count,
            "generated_at": gt.generated_at,
        }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nGround truth saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate ground truth for benchmarks")
    parser.add_argument("--use-kernel", action="store_true",
                       help="Use the analyzing-data kernel (requires warehouse.yml)")
    parser.add_argument("--output", default="ground_truth.json",
                       help="Output file path")

    args = parser.parse_args()

    if args.use_kernel:
        scenarios = generate_ground_truth_kernel()
    else:
        print("Error: --use-kernel is required (direct connection not yet implemented)")
        print("Make sure ~/.astro/agents/warehouse.yml is configured")
        sys.exit(1)

    if scenarios:
        save_ground_truth(scenarios, Path(args.output))
    else:
        print("No ground truth generated!")
        sys.exit(1)


if __name__ == "__main__":
    main()
