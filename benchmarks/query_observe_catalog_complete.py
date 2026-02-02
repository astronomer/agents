#!/usr/bin/env python3
"""
Query the Observe MCP catalog to find ALL tables across Snowflake, Databricks, and BigQuery.

This script fetches all pages of results (not just the first 100) for a complete inventory.
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


def fetch_all_tables(client, asset_type, display_name):
    """Fetch all tables for a given asset type with pagination."""
    all_tables = []
    offset = 0
    limit = 100
    total_count = None

    while True:
        try:
            response = client.search_assets(
                asset_types=[asset_type],
                limit=limit,
                offset=offset,
            )

            assets = response.get("assets", [])
            if not assets:
                break

            # Get total count from first request
            if total_count is None:
                total_count = response.get("totalCount", 0)

            # Extract table names
            for asset in assets:
                asset_id = asset.get("assetId", "unknown")
                asset_name = asset.get("name", asset_id)
                all_tables.append({
                    "name": asset_name,
                    "asset_id": asset_id,
                    "asset_type": asset_type,
                })

            print(f"  {display_name}: Fetched {len(all_tables)} of {total_count} tables...")

            # Check if we've fetched all results
            if len(all_tables) >= total_count or len(assets) < limit:
                break

            offset += limit

        except Exception as e:
            print(f"  Error fetching {display_name} tables at offset {offset}: {e}")
            break

    return all_tables, total_count or 0


def query_all_tables():
    """Query ALL tables by warehouse type from the Observe MCP catalog."""

    # Get configuration from astro CLI
    org_id = get_org_id_from_config()
    token = get_token_from_config()
    api_url = get_api_url_from_config()

    if not org_id:
        print("Error: Unable to get organization ID from astro CLI config.")
        print("Please run 'astro login' first to authenticate.")
        sys.exit(1)

    if not token:
        print("Error: Unable to get authentication token.")
        print("Please run 'astro login' first to authenticate.")
        sys.exit(1)

    print(f"Connecting to Astro Cloud...")
    print(f"  Organization ID: {org_id}")
    print(f"  API URL: {api_url or 'default'}")
    print()

    # Configure the MCP server with the Astro CLI credentials
    configure(
        organization_id=org_id,
        token=token,
        api_url=api_url,
    )

    # Get the client and search for tables
    client = _get_client()

    warehouse_types = {
        "snowflakeTable": "Snowflake",
        "databricksTable": "Databricks",
        "bigQueryTable": "BigQuery",
    }

    results = {}
    total_tables_returned = 0

    print("Fetching all tables from Astro Catalog...")
    print()

    for asset_type, display_name in warehouse_types.items():
        print(f"Fetching all {display_name} tables...")

        try:
            tables, total_count = fetch_all_tables(client, asset_type, display_name)

            table_names = sorted([t["name"] for t in tables])

            results[display_name] = {
                "total_count": total_count,
                "returned_count": len(tables),
                "table_names": table_names,
            }

            total_tables_returned += len(tables)
            print(f"  {display_name}: Complete! Fetched {len(tables)} of {total_count} tables")
            print()

        except Exception as e:
            print(f"  Error fetching {display_name} tables: {e}")
            results[display_name] = {
                "error": str(e),
            }
            print()

    print()
    print("=" * 80)
    print("COMPLETE SUMMARY: All Tables by Warehouse Type")
    print("=" * 80)
    print()

    grand_total = 0

    for warehouse_name, data in results.items():
        if "error" in data:
            print(f"{warehouse_name}:")
            print(f"  Error: {data['error']}")
            print()
        else:
            print(f"{warehouse_name}:")
            print(f"  Total catalog count: {data['total_count']}")
            print(f"  Returned/fetched: {data['returned_count']}")

            if data['table_names']:
                print(f"  Sample tables (first 10):")
                for table_name in data['table_names'][:10]:
                    print(f"    - {table_name}")
                if len(data['table_names']) > 10:
                    print(f"    ... and {len(data['table_names']) - 10} more")
            else:
                print(f"  No tables found")

            grand_total += data['returned_count']
            print()

    print("=" * 80)
    print(f"GRAND TOTAL TABLES RETURNED: {total_tables_returned}")
    print("=" * 80)

    # Save detailed results to JSON file
    output_file = Path(__file__).parent / "observe_catalog_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print()
    print(f"Detailed results saved to: {output_file}")

    # Also print statistics summary
    stats_file = Path(__file__).parent / "observe_catalog_stats.json"
    stats = {}
    for warehouse_name, data in results.items():
        if "error" not in data:
            stats[warehouse_name] = {
                "total_count": data['total_count'],
                "fetched_count": data['returned_count'],
                "table_count": len(data['table_names']),
            }

    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"Statistics saved to: {stats_file}")


if __name__ == "__main__":
    query_all_tables()
