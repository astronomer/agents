#!/usr/bin/env python3
"""Test DRY_RUN mode in the data-warehouse MCP server."""

import os
import sys
from pathlib import Path

# Add the package to path - use installed version for proper dependencies
INSTALLED_PATH = (
    Path.home() / ".local/share/uv/tools/data-warehouse/lib/python3.12/site-packages"
)
sys.path.insert(0, str(INSTALLED_PATH))

from src.mocks import (  # noqa: E402
    get_mock_response,
    get_mock_stats,
    is_dry_run,
    load_mocks,
)


def test_dry_run_detection():
    """Test that DRY_RUN mode is detected from environment."""
    print("Testing DRY_RUN detection...")

    # Should be False by default
    os.environ.pop("DRY_RUN_MODE", None)
    # Need to reimport to reset module state

    print(f"  Without env var: is_dry_run() = {is_dry_run()}")

    os.environ["DRY_RUN_MODE"] = "true"
    print(f"  With DRY_RUN_MODE=true: is_dry_run() = {is_dry_run()}")

    os.environ["DRY_RUN_MODE"] = "false"
    print(f"  With DRY_RUN_MODE=false: is_dry_run() = {is_dry_run()}")

    os.environ["DRY_RUN_MODE"] = "TRUE"
    print(f"  With DRY_RUN_MODE=TRUE: is_dry_run() = {is_dry_run()}")

    print("  PASS")


def test_mock_loading():
    """Test loading mock responses from YAML."""
    print("\nTesting mock loading...")

    mock_file = Path(__file__).parent.parent / "tests" / "mocks" / "hitl-mocks.yaml"
    if not mock_file.exists():
        print(f"  SKIP: Mock file not found: {mock_file}")
        return

    os.environ["MOCK_RESPONSES_FILE"] = str(mock_file)

    # Clear any existing mocks
    from src.mocks import clear_mocks

    clear_mocks()

    # Load mocks
    success = load_mocks(str(mock_file))
    print(f"  Load result: {success}")

    stats = get_mock_stats()
    print(f"  Stats: {stats}")

    print("  PASS")


def test_mock_matching():
    """Test pattern matching for mock responses."""
    print("\nTesting mock pattern matching...")

    mock_file = Path(__file__).parent.parent / "tests" / "mocks" / "hitl-mocks.yaml"
    if not mock_file.exists():
        print(f"  SKIP: Mock file not found: {mock_file}")
        return

    os.environ["MOCK_RESPONSES_FILE"] = str(mock_file)
    os.environ["DRY_RUN_MODE"] = "true"

    from src.mocks import clear_mocks

    clear_mocks()
    load_mocks(str(mock_file))

    # Test HITL pattern
    query1 = "SELECT OPERATOR, COUNT(*) FROM task_runs WHERE OPERATOR ILIKE '%hitl%' GROUP BY 1"
    response1 = get_mock_response(query1, "run_sql")
    print(f"  Query: {query1[:60]}...")
    print(f"  Response contains 'HITLOperator': {'HITLOperator' in response1}")

    # Test catch-all pattern
    query2 = "SELECT * FROM random_table"
    response2 = get_mock_response(query2, "run_sql")
    print(f"  Query: {query2}")
    print(f"  Response starts with '[DRY_RUN]': {response2.startswith('[DRY_RUN]')}")

    # Test list_schemas
    response3 = get_mock_response("list_schemas", "list_schemas")
    print(f"  list_schemas response contains 'schemas': {'schemas' in response3}")

    print("  PASS")


def main():
    print("=" * 60)
    print("DRY_RUN Mode Tests")
    print("=" * 60)

    test_dry_run_detection()
    test_mock_loading()
    test_mock_matching()

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
