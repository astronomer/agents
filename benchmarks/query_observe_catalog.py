#!/usr/bin/env python3
"""
Query the Observe MCP catalog to find all tables across Snowflake, Databricks, and BigQuery.

This script directly imports and uses the Observe MCP tools without running a server.
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


def query_tables():
    """Query all tables by warehouse type from the Observe MCP catalog."""

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
    total_tables = 0

    for asset_type, display_name in warehouse_types.items():
        print(f"Searching for {display_name} tables...")

        try:
            response = client.search_assets(
                asset_types=[asset_type],
                limit=100,
            )

            assets = response.get("assets", [])
            total_count = response.get("totalCount", len(assets))

            # Extract table names
            table_names = []
            for asset in assets:
                # Get the asset ID or name
                asset_id = asset.get("assetId", "unknown")
                asset_name = asset.get("name", asset_id)
                table_names.append(asset_name)

            results[display_name] = {
                "total_count": total_count,
                "returned_count": len(assets),
                "table_names": sorted(table_names),
            }

            total_tables += len(assets)

            print(f"  Found {total_count} total {display_name} tables ({len(assets)} returned)")

        except Exception as e:
            print(f"  Error searching for {display_name} tables: {e}")
            results[display_name] = {
                "error": str(e),
            }

    print()
    print("=" * 80)
    print("SUMMARY: Tables by Warehouse Type")
    print("=" * 80)
    print()

    for warehouse_name, data in results.items():
        if "error" in data:
            print(f"{warehouse_name}:")
            print(f"  Error: {data['error']}")
            print()
        else:
            print(f"{warehouse_name}:")
            print(f"  Total count: {data['total_count']}")
            print(f"  Returned: {data['returned_count']}")

            if data['table_names']:
                print(f"  Tables:")
                for table_name in data['table_names']:
                    print(f"    - {table_name}")
            else:
                print(f"  No tables found")
            print()

    print("=" * 80)
    print(f"TOTAL TABLES RETURNED: {total_tables}")
    print("=" * 80)

    # Output detailed results as JSON
    print()
    print("Detailed Results (JSON):")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    query_tables()
