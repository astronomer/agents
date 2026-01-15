# Skill Testing Resources

Test data and fixtures for skill flow testing.

## Directory Structure

```
tests/
├── README.md              # This file
├── expected-flows/        # Expected agent behavior definitions
│   └── hitl-operators.yaml
├── mocks/                 # Mock responses for DRY_RUN mode
│   └── hitl-mocks.yaml
├── real-queries.txt       # Evaluation queries (real warehouse)
└── evaluation-queries.yaml # Structured query definitions
```

## Expected Flows

Define expected agent behavior in YAML format:

```yaml
name: hitl-operator-query
description: |
  When user asks about HITL operators, agent should:
  1. Recognize product-specific query
  2. Fetch Airflow docs to discover all operators
  3. Query warehouse with complete list

expected_flow:
  - action: read
    file_pattern: "SKILL.md"
    required: true
  - action: webfetch
    url_pattern: "airflow.apache.org.*hitl"
    required: true
  - action: run_sql
    query_pattern: "OPERATOR.*ApprovalOperator"
    required: true
```

## Mock Responses

Pattern-based mock responses for DRY_RUN mode:

```yaml
run_sql:
  - pattern: "ApprovalOperator"
    response: |
      shape: (5, 4)
      | OPERATOR | COUNT |
      | HITLOperator | 15 |
      ...
```

Patterns are Python regex matched with `re.IGNORECASE`.

## Usage

### Run with mocks (dry run)

```bash
export DRY_RUN_MODE=true
export MOCK_RESPONSES_FILE=tests/mocks/hitl-mocks.yaml
export FLOW_TRACE_FILE=/tmp/trace.json

claude --plugin-dir ./claude-code-plugin "Find HITL customers"
```

### Compare to expected flow

```bash
python scripts/compare-flows.py /tmp/trace.json tests/expected-flows/hitl-operators.yaml
```

### Run real evaluation

```bash
uv run python scripts/split-test.py \
  --queries tests/real-queries.txt \
  --plugin-dir ./claude-code-plugin
```

## Adding Test Cases

1. Create expected flow: `tests/expected-flows/my-query.yaml`
2. Create mocks: `tests/mocks/my-query-mocks.yaml`
3. Add query to `real-queries.txt` for real warehouse testing

See `docs/skill-testing.md` for detailed framework documentation.
