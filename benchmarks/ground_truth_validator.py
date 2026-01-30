"""Ground truth validation for benchmark results.

Compares benchmark outputs against expected results to measure accuracy,
precision, and recall in addition to performance metrics.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    """Quality metrics for a benchmark result."""
    scenario: str
    model: str

    # Correctness metrics
    accuracy: float  # Overall correctness score (0-1)
    precision: float  # % of returned items that are correct
    recall: float  # % of expected items that were found
    f1_score: float  # Harmonic mean of precision and recall

    # Item tracking
    true_positives: list[str] = field(default_factory=list)
    false_positives: list[str] = field(default_factory=list)
    false_negatives: list[str] = field(default_factory=list)

    # Qualitative assessment
    contains_key_info: bool = True  # Does it mention critical information?
    correct_count: bool = True  # Is the count/quantity correct?
    notes: str = ""


def normalize_table_name(name: str) -> str:
    """Normalize table names for comparison.

    Handles variations like:
    - Full URIs vs simple names
    - Case differences
    - Schema prefixes
    """
    # Extract table name from URI if present
    # e.g., "snowflake://account/db/schema/table" -> "table"
    if '://' in name:
        name = name.split('/')[-1]

    # Remove schema prefix if present
    # e.g., "schema.table" -> "table"
    if '.' in name:
        parts = name.split('.')
        name = parts[-1]

    return name.lower().strip()


def extract_table_names(text: str) -> set[str]:
    """Extract table names from Claude's response text.

    Looks for patterns like:
    - "table_name"
    - TABLE_NAME
    - database.schema.table
    - URIs: snowflake://...
    """
    tables = set()

    # Pattern 1: URI format (snowflake://account/db/schema/table)
    uri_pattern = r'(?:snowflake|databricks|bigquery)://[^\s]+'
    for match in re.finditer(uri_pattern, text, re.IGNORECASE):
        uri = match.group(0)
        table_name = normalize_table_name(uri)
        tables.add(table_name)

    # Pattern 2: Quoted names ("table_name" or 'table_name')
    quoted_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
    for match in re.finditer(quoted_pattern, text):
        table_name = normalize_table_name(match.group(1))
        tables.add(table_name)

    # Pattern 3: Schema.table or database.schema.table
    qualified_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\b'
    for match in re.finditer(qualified_pattern, text):
        table_name = normalize_table_name(match.group(1))
        tables.add(table_name)

    # Pattern 4: Common table name patterns (all caps or snake_case)
    # More conservative - must be 3+ chars and common data warehouse naming
    name_pattern = r'\b([A-Z_]{3,}|[a-z]+_[a-z_]+)\b'
    for match in re.finditer(name_pattern, text):
        candidate = match.group(1)
        # Filter out common words that aren't table names
        if candidate.lower() not in {'the', 'and', 'for', 'with', 'from', 'select'}:
            table_name = normalize_table_name(candidate)
            tables.add(table_name)

    return tables


def extract_dag_names(text: str) -> set[str]:
    """Extract DAG names from Claude's response text."""
    dags = set()

    # Pattern 1: "dag_name" or 'dag_name'
    quoted_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
    for match in re.finditer(quoted_pattern, text):
        dag_name = match.group(1).lower()
        # DAGs often have _dag suffix or contain specific keywords
        if '_dag' in dag_name or 'dag' in dag_name.split('_'):
            dags.add(dag_name)

    # Pattern 2: dag://namespace/dag_id
    uri_pattern = r'dag://[^/]+/([^\s]+)'
    for match in re.finditer(uri_pattern, text):
        dag_name = match.group(1).lower()
        dags.add(dag_name)

    return dags


def validate_table_discovery(
    result_text: str,
    expected_tables: list[str],
    scenario: str,
    model: str,
) -> ValidationResult:
    """Validate table discovery scenarios.

    Args:
        result_text: Claude's response text
        expected_tables: List of expected table names
        scenario: Scenario name
        model: Model name

    Returns:
        Validation result with metrics
    """
    # Extract tables from response
    actual_tables = extract_table_names(result_text)
    expected_set = {normalize_table_name(t) for t in expected_tables}

    # Calculate metrics
    true_positives = list(actual_tables & expected_set)
    false_positives = list(actual_tables - expected_set)
    false_negatives = list(expected_set - actual_tables)

    tp_count = len(true_positives)
    fp_count = len(false_positives)
    fn_count = len(false_negatives)

    # Precision: Of what we returned, how much was correct?
    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0

    # Recall: Of what we should have found, how much did we find?
    recall = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0

    # F1 score: Harmonic mean
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    # Accuracy: Simple correctness score
    # High if we found most tables and didn't add many wrong ones
    accuracy = (tp_count / len(expected_set)) * (1 - (fp_count / max(len(actual_tables), 1)))
    accuracy = max(0.0, accuracy)  # Clamp to [0, 1]

    # Check if response contains key information
    contains_key_info = len(true_positives) > 0 or 'table' in result_text.lower()

    # Check if count is approximately correct (within 20%)
    expected_count = len(expected_tables)
    if expected_count == 0:
        correct_count = len(actual_tables) == 0
    else:
        count_ratio = len(actual_tables) / expected_count
        correct_count = 0.8 <= count_ratio <= 1.2

    notes = []
    if not contains_key_info:
        notes.append("Response doesn't mention any tables")
    if not correct_count:
        notes.append(f"Count mismatch: found {len(actual_tables)}, expected ~{expected_count}")
    if fp_count > tp_count:
        notes.append(f"High false positive rate: {fp_count} incorrect vs {tp_count} correct")

    return ValidationResult(
        scenario=scenario,
        model=model,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        contains_key_info=contains_key_info,
        correct_count=correct_count,
        notes="; ".join(notes) if notes else "Good",
    )


def validate_dag_discovery(
    result_text: str,
    expected_dags: list[str],
    scenario: str,
    model: str,
) -> ValidationResult:
    """Validate DAG discovery scenarios."""
    actual_dags = extract_dag_names(result_text)
    expected_set = {dag.lower() for dag in expected_dags}

    true_positives = list(actual_dags & expected_set)
    false_positives = list(actual_dags - expected_set)
    false_negatives = list(expected_set - actual_dags)

    tp_count = len(true_positives)
    fp_count = len(false_positives)
    fn_count = len(false_negatives)

    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    recall = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp_count / len(expected_set)) * (1 - (fp_count / max(len(actual_dags), 1))) if expected_set else 0.0
    accuracy = max(0.0, accuracy)

    contains_key_info = len(true_positives) > 0 or 'dag' in result_text.lower()
    correct_count = abs(len(actual_dags) - len(expected_dags)) <= max(1, len(expected_dags) * 0.2)

    return ValidationResult(
        scenario=scenario,
        model=model,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1,
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        contains_key_info=contains_key_info,
        correct_count=correct_count,
    )


def validate_detailed_inspection(
    result_text: str,
    expected_metadata: dict,
    scenario: str,
    model: str,
) -> ValidationResult:
    """Validate detailed table inspection scenarios."""
    # Check if response contains expected metadata fields
    required_fields = ['owner', 'deployment', 'updated']
    found_fields = []
    missing_fields = []

    text_lower = result_text.lower()
    for field in required_fields:
        if field in text_lower or field + 's' in text_lower:
            found_fields.append(field)
        else:
            missing_fields.append(field)

    # Calculate accuracy based on field coverage
    accuracy = len(found_fields) / len(required_fields)

    # For this scenario, precision/recall are based on metadata completeness
    precision = accuracy  # If we mention it, assume it's correct
    recall = accuracy  # Did we find all required fields?
    f1 = accuracy

    contains_key_info = len(found_fields) >= 2
    correct_count = True  # Not applicable for this scenario

    notes = f"Found {len(found_fields)}/{len(required_fields)} required fields"
    if missing_fields:
        notes += f"; Missing: {', '.join(missing_fields)}"

    return ValidationResult(
        scenario=scenario,
        model=model,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1,
        true_positives=found_fields,
        false_positives=[],
        false_negatives=missing_fields,
        contains_key_info=contains_key_info,
        correct_count=correct_count,
        notes=notes,
    )


def validate_benchmark_result(
    scenario_name: str,
    result_text: str,
    model: str,
    ground_truth: dict,
) -> ValidationResult:
    """Validate a single benchmark result against ground truth.

    Args:
        scenario_name: Name of the scenario
        result_text: Claude's response text
        model: Model name
        ground_truth: Ground truth data for all scenarios

    Returns:
        Validation result with quality metrics
    """
    scenario_data = ground_truth.get('scenarios', {}).get(scenario_name, {})
    expected = scenario_data.get('expected_results', {})

    # Route to appropriate validator based on scenario type
    if 'lineage' in scenario_name or 'dag' in scenario_name.lower():
        expected_dags = expected.get('dags', [])
        return validate_dag_discovery(result_text, expected_dags, scenario_name, model)

    elif 'detailed_inspection' in scenario_name:
        return validate_detailed_inspection(result_text, expected, scenario_name, model)

    else:
        # Table discovery scenarios
        expected_tables = expected.get('tables', [])

        # For cross-warehouse, flatten the dictionary
        if isinstance(expected_tables, dict):
            flat_tables = []
            for warehouse_tables in expected_tables.values():
                if isinstance(warehouse_tables, list):
                    flat_tables.extend(warehouse_tables)
            expected_tables = flat_tables

        return validate_table_discovery(result_text, expected_tables, scenario_name, model)


def load_ground_truth(ground_truth_path: Path | str) -> dict:
    """Load ground truth data from JSON file."""
    with open(ground_truth_path) as f:
        return json.load(f)


def validate_benchmark_results(
    results: list[dict],
    ground_truth_path: Path | str,
) -> list[ValidationResult]:
    """Validate all benchmark results against ground truth.

    Args:
        results: List of benchmark results
        ground_truth_path: Path to ground truth JSON file

    Returns:
        List of validation results with quality metrics
    """
    ground_truth = load_ground_truth(ground_truth_path)
    validations = []

    for result in results:
        validation = validate_benchmark_result(
            scenario_name=result['scenario'],
            result_text=result['result_text'],
            model=result['model'],
            ground_truth=ground_truth,
        )
        validations.append(validation)

    return validations
