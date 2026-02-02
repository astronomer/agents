#!/usr/bin/env python3
"""Validation utilities for benchmark results.

Extracts table names from Claude's natural language responses and
calculates precision/recall/F1 against ground truth.
"""

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of validating against ground truth."""
    precision: float
    recall: float
    f1: float
    found_count: int
    expected_count: int
    true_positives: list[str]
    false_positives: list[str]
    false_negatives: list[str]


def extract_tables_from_response(text: str) -> set[str]:
    """Extract table names from Claude's natural language response.

    Handles various formats:
    - UPPER_CASE_TABLE_NAMES
    - Backtick-quoted: `table_name`
    - FQDN: database.schema.table
    - Bullet lists: - TABLE_NAME
    - Numbered lists: 1. TABLE_NAME

    Returns set of normalized table names (uppercase, no schema prefix).
    """
    tables = set()

    # Pattern 1: UPPER_CASE names (common for Snowflake)
    # Match words that are all uppercase with underscores, min 4 chars
    upper_pattern = r'\b([A-Z][A-Z0-9_]{3,})\b'
    for match in re.findall(upper_pattern, text):
        # Filter out common non-table words
        if match not in {'TRUE', 'FALSE', 'NULL', 'SELECT', 'FROM', 'WHERE',
                        'TABLE', 'TABLES', 'SCHEMA', 'DATABASE', 'COLUMN',
                        'WITH', 'INTO', 'JOIN', 'LEFT', 'RIGHT', 'INNER',
                        'OUTER', 'GROUP', 'ORDER', 'LIMIT', 'OFFSET',
                        'SNOWFLAKE', 'DATABRICKS', 'BIGQUERY', 'FOUND'}:
            tables.add(match)

    # Pattern 2: Backtick-quoted names
    backtick_pattern = r'`([^`]+)`'
    for match in re.findall(backtick_pattern, text):
        # Extract table name from potential FQDN
        parts = match.split('.')
        table_name = parts[-1].upper()
        if len(table_name) >= 3:
            tables.add(table_name)

    # Pattern 3: FQDN patterns (db.schema.table)
    fqdn_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)\b'
    for match in re.findall(fqdn_pattern, text):
        parts = match.split('.')
        table_name = parts[-1].upper()
        if len(table_name) >= 3:
            tables.add(table_name)

    # Pattern 4: Asset ID patterns (snowflake://account/db/schema/table)
    asset_pattern = r'snowflake://[^/]+/([^/]+)/([^/]+)/([^\s\)\"\']+)'
    for match in re.findall(asset_pattern, text):
        table_name = match[2].upper()
        if len(table_name) >= 3:
            tables.add(table_name)

    # Pattern 5: Mixed case table names in bullet/numbered lists
    # Look for lines like "- customer_table" or "1. CustomerTable"
    list_pattern = r'(?:^|\n)\s*(?:[-*•]|\d+\.)\s*([A-Za-z_][A-Za-z0-9_]+)'
    for match in re.findall(list_pattern, text):
        if len(match) >= 4:
            tables.add(match.upper())

    return tables


def extract_schemas_from_response(text: str) -> set[str]:
    """Extract schema names from Claude's response."""
    schemas = set()

    # Pattern 1: Explicit schema mentions
    schema_pattern = r'(?:schema[:\s]+|in\s+)([A-Z][A-Z0-9_]+)'
    for match in re.findall(schema_pattern, text, re.IGNORECASE):
        if len(match) >= 2:
            schemas.add(match.upper())

    # Pattern 2: From FQDNs (db.SCHEMA.table)
    fqdn_pattern = r'\b[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\b'
    for match in re.findall(fqdn_pattern, text):
        schemas.add(match.upper())

    return schemas


def extract_counts_from_response(text: str) -> dict[str, int]:
    """Extract numerical counts from Claude's response.

    Returns dict mapping context to count, e.g.:
    {"tables": 243, "schemas": 15, "snowflake": 18734}
    """
    counts = {}

    # Pattern: "X tables" or "X schemas" or "found X"
    patterns = [
        (r'(\d+)\s+tables?\b', 'tables'),
        (r'(\d+)\s+schemas?\b', 'schemas'),
        (r'found\s+(\d+)', 'found'),
        (r'total[:\s]+(\d+)', 'total'),
        (r'count[:\s]+(\d+)', 'count'),
        (r'snowflake[:\s]+(\d+)', 'snowflake'),
        (r'databricks[:\s]+(\d+)', 'databricks'),
        (r'bigquery[:\s]+(\d+)', 'bigquery'),
    ]

    for pattern, key in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Take the largest number found for this key
            counts[key] = max(int(m) for m in matches)

    return counts


def validate_tables(
    response_text: str,
    expected_tables: list[dict],
    fuzzy_match: bool = True,
) -> ValidationResult:
    """Validate extracted tables against ground truth.

    Args:
        response_text: Claude's response text
        expected_tables: List of {"name": "TABLE_NAME", ...} from ground truth
        fuzzy_match: If True, match substrings (CUSTOMER matches CUSTOMER_AIRFLOW)

    Returns:
        ValidationResult with precision, recall, F1, and detailed matches
    """
    found_tables = extract_tables_from_response(response_text)
    expected_names = {t["name"].upper() for t in expected_tables}

    if fuzzy_match:
        # Fuzzy matching: found table matches if it's a substring of expected
        # or expected is a substring of found
        true_positives = set()
        matched_expected = set()

        for found in found_tables:
            for expected in expected_names:
                if found in expected or expected in found:
                    true_positives.add(found)
                    matched_expected.add(expected)
                    break

        false_positives = found_tables - true_positives
        false_negatives = expected_names - matched_expected
    else:
        # Exact matching
        true_positives = found_tables & expected_names
        false_positives = found_tables - expected_names
        false_negatives = expected_names - found_tables

    # Calculate metrics
    precision = len(true_positives) / len(found_tables) if found_tables else 0.0
    recall = len(true_positives) / len(expected_names) if expected_names else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return ValidationResult(
        precision=precision,
        recall=recall,
        f1=f1,
        found_count=len(found_tables),
        expected_count=len(expected_names),
        true_positives=sorted(true_positives),
        false_positives=sorted(false_positives),
        false_negatives=sorted(false_negatives),
    )


def validate_count(
    response_text: str,
    expected_count: int,
    tolerance: float = 0.1,
) -> tuple[bool, int | None, str]:
    """Validate that response mentions approximately the expected count.

    Args:
        response_text: Claude's response
        expected_count: Expected count from ground truth
        tolerance: Acceptable deviation (0.1 = 10%)

    Returns:
        (is_valid, found_count, explanation)
    """
    counts = extract_counts_from_response(response_text)

    if not counts:
        return False, None, "No counts found in response"

    # Check if any extracted count is close to expected
    for key, found_count in counts.items():
        deviation = abs(found_count - expected_count) / expected_count if expected_count > 0 else 0
        if deviation <= tolerance:
            return True, found_count, f"Found {found_count} ({key}), expected {expected_count}"

    # Find closest match
    closest_key = min(counts.keys(), key=lambda k: abs(counts[k] - expected_count))
    closest_count = counts[closest_key]

    return False, closest_count, f"Found {closest_count} ({closest_key}), expected {expected_count}"


def format_validation_summary(result: ValidationResult) -> str:
    """Format validation result as human-readable summary."""
    lines = [
        f"Precision: {result.precision:.1%} ({len(result.true_positives)}/{result.found_count} correct)",
        f"Recall:    {result.recall:.1%} ({len(result.true_positives)}/{result.expected_count} found)",
        f"F1 Score:  {result.f1:.1%}",
    ]

    if result.false_positives:
        lines.append(f"\nFalse positives ({len(result.false_positives)}):")
        for fp in result.false_positives[:5]:
            lines.append(f"  - {fp}")
        if len(result.false_positives) > 5:
            lines.append(f"  ... and {len(result.false_positives) - 5} more")

    if result.false_negatives:
        lines.append(f"\nFalse negatives ({len(result.false_negatives)}):")
        for fn in result.false_negatives[:5]:
            lines.append(f"  - {fn}")
        if len(result.false_negatives) > 5:
            lines.append(f"  ... and {len(result.false_negatives) - 5} more")

    return "\n".join(lines)


# Test the extraction
if __name__ == "__main__":
    test_response = """
    I found 243 customer-related tables in your data warehouse:

    **Snowflake Tables (18,734 total)**:
    - CUSTOMER_AIRFLOW_VERSIONS (in REPORTING schema)
    - CURRENT_ASTRO_CUSTS (in MART_CUST schema)
    - `HQ.DELIVERY.CUSTOMER_BOT_COLLECTED_DETAILS`

    The table snowflake://fy02423/HQ/REPORTING/CUSTOMER_DATA contains customer information.

    Other tables include CUST_METRICS, USER_CUSTOMERS, and CUSTOMER_EVENTS.
    """

    print("Testing table extraction...")
    tables = extract_tables_from_response(test_response)
    print(f"Found {len(tables)} tables:")
    for t in sorted(tables):
        print(f"  - {t}")

    print("\nTesting count extraction...")
    counts = extract_counts_from_response(test_response)
    print(f"Counts: {counts}")

    print("\nTesting schema extraction...")
    schemas = extract_schemas_from_response(test_response)
    print(f"Schemas: {schemas}")
