#!/usr/bin/env python3
"""
Find all tables with an 'email' column in the catalog.

This script queries the Observe MCP catalog, retrieves schema information
for each table, and identifies tables containing an 'email' column.
"""

import json
import sys
from pathlib import Path

# Add the astro-observe-mcp to path
mcp_path = Path(__file__).parent.parent / "astro-observe-mcp" / "src"
sys.path.insert(0, str(mcp_path))

from astro_observe_mcp.server import configure, _get_client
from astro_observe_mcp.auth import (
    get_org_id_from_config,
    get_token_from_config,
    get_api_url_from_config,
)


def find_tables_with_email_column(catalog_results_file: str) -> dict:
    """Find tables with 'email' columns from catalog results."""

    # Get configuration from astro CLI
    org_id = get_org_id_from_config()
    token = get_token_from_config()
    api_url = get_api_url_from_config()

    if not org_id or not token:
        print("Error: Unable to get organization ID and token from astro CLI config.")
        print("Please run 'astro login' first to authenticate.")
        sys.exit(1)

    print(f"Connecting to Astro Cloud...")
    print(f"  Organization ID: {org_id}")
    print()

    # Configure the MCP server with the Astro CLI credentials
    configure(
        organization_id=org_id,
        token=token,
        api_url=api_url,
    )

    # Get the client
    client = _get_client()

    # Load table names from catalog results
    with open(catalog_results_file, "r") as f:
        catalog_data = json.load(f)

    # Collect tables with email columns
    tables_with_email = {
        "Snowflake": [],
        "Databricks": [],
        "BigQuery": [],
    }

    # Map warehouse names to asset types
    warehouse_to_asset_type = {
        "Snowflake": "snowflakeTable",
        "Databricks": "databricksTable",
        "BigQuery": "bigQueryTable",
    }

    # Process each warehouse
    for warehouse_name, asset_type in warehouse_to_asset_type.items():
        if warehouse_name not in catalog_data:
            print(f"Skipping {warehouse_name} - not in catalog results")
            continue

        table_names = catalog_data[warehouse_name].get("table_names", [])
        print(f"Checking {warehouse_name} tables for 'email' columns...")
        print(f"  Total tables to check: {len(table_names)}")
        print()

        checked = 0
        found = 0
        failed = 0

        for idx, table_name in enumerate(table_names, 1):
            if idx % 100 == 0:
                print(f"  Progress: {idx}/{len(table_names)} tables checked...")

            try:
                # Get asset details
                asset = client.get_asset(table_name)

                # Check if the asset has column information
                columns = asset.get("attributes", {}).get("columns", [])

                # Search for 'email' column (case-insensitive)
                has_email = False
                for column in columns:
                    if isinstance(column, dict):
                        col_name = column.get("name", "").lower()
                    else:
                        col_name = str(column).lower()

                    if col_name == "email":
                        has_email = True
                        break

                if has_email:
                    tables_with_email[warehouse_name].append(table_name)
                    found += 1

                checked += 1

            except Exception as e:
                failed += 1
                # Silently skip errors for individual assets
                pass

        print(f"  {warehouse_name}: Checked {checked} tables, found {found} with 'email' column")
        if failed > 0:
            print(f"  {warehouse_name}: {failed} tables failed to retrieve")
        print()

    return tables_with_email


if __name__ == "__main__":
    # Use the cached catalog results
    catalog_file = Path(__file__).parent / "observe_catalog_results.json"

    if not catalog_file.exists():
        print(f"Error: Catalog results file not found at {catalog_file}")
        print("Please run query_observe_catalog_complete.py first.")
        sys.exit(1)

    results = find_tables_with_email_column(str(catalog_file))

    print("=" * 80)
    print("TABLES WITH 'EMAIL' COLUMN")
    print("=" * 80)
    print()

    for warehouse_name in ["Snowflake", "Databricks", "BigQuery"]:
        tables = results[warehouse_name]
        print(f"{warehouse_name}:")
        if tables:
            for table_name in sorted(tables):
                print(f"  - {table_name}")
        else:
            print(f"  No tables found with 'email' column")
        print()

    # Save results to JSON
    output_file = Path(__file__).parent / "tables_with_email_column.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Results saved to: {output_file}")
