# Skill Testing Framework

Test and iterate on Claude skills without hitting real data warehouses.

## Overview

This framework provides:
- **DRY_RUN mode**: Mock MCP responses to test skill flows without real queries
- **Flow tracing**: Capture tool calls to understand agent behavior
- **Expected flow comparison**: Define and verify correct agent decision paths
- **Ralph Loop**: Iterate on skills until they match expected behavior

## Quick Start

```bash
# 1. Set up mock mode
export DRY_RUN_MODE=true
export MOCK_RESPONSES_FILE=tests/mocks/hitl-mocks.yaml
export FLOW_TRACE_FILE=/tmp/flow-trace.json

# 2. Run a test query
claude --plugin-dir ./claude-code-plugin \
  "Find customers using Human-in-the-loop operators"

# 3. Compare actual flow to expected
python scripts/compare-flows.py \
  /tmp/flow-trace.json \
  tests/expected-flows/hitl-operators.yaml
```

## Components

### DRY_RUN Mode (`astro-dwh-mcp/src/mocks.py`)

When `DRY_RUN_MODE=true`, the MCP server returns mock responses instead of executing real queries:

```python
# Environment variables
DRY_RUN_MODE=true                    # Enable dry run
MOCK_RESPONSES_FILE=path/to/mocks.yaml  # Pattern-based responses
FLOW_TRACE_FILE=/tmp/trace.json     # Log all tool calls
```

Mock responses are pattern-based YAML:

```yaml
# tests/mocks/hitl-mocks.yaml
run_sql:
  - pattern: "OPERATOR.*ILIKE.*hitl"
    response: |
      shape: (3, 2)
      | OPERATOR | COUNT |
      | HITLOperator | 10 |
      | HITLBranchOperator | 5 |

list_schemas:
  - pattern: ".*"
    response: |
      {"schemas": [{"name": "MODEL_ASTRO", "table_count": 50}]}
```

### Flow Tracing

Every tool call is logged to `FLOW_TRACE_FILE`:

```json
{
  "dry_run": true,
  "trace": [
    {"tool": "lookup_concept", "action": "mock_response", "is_mock": true},
    {"tool": "run_sql", "action": "mock_response", "query": "SELECT..."}
  ]
}
```

Early exit detection: If a real query is executed in DRY_RUN mode, a `.early_exit` marker file is created.

### Expected Flow Definitions

Define expected behavior in `tests/expected-flows/`:

```yaml
# tests/expected-flows/hitl-operators.yaml
name: HITL Operators Query
description: Find customers using Human-in-the-loop operators

expected:
  - action: read
    pattern: "SKILL.md"
  - action: lookup_concept
  - action: run_sql
    pattern: "OPERATOR.*HITL"
```

### Flow Comparison (`scripts/compare-flows.py`)

Compare actual trace against expected flow:

```bash
python scripts/compare-flows.py actual-trace.json expected-flow.yaml
```

Output:
```
Flow Comparison Results:
[OK] Step 1: read SKILL.md
[OK] Step 2: lookup_concept
[FAIL] Step 3: Expected run_sql with HITL, got list_schemas
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/ralph-loop.sh` | Iterate on skills with fresh context per turn |
| `scripts/compare-flows.py` | Compare actual vs expected flows |
| `scripts/review-skill.py` | Analyze skill execution and suggest improvements |
| `scripts/split-test.py` | A/B test configurations (cache, warehouse.md, etc.) |
| `scripts/run-flow-test.sh` | Run single flow test with mocks |
| `scripts/run-dry-warehouse.sh` | Start MCP server in dry-run mode |
| `scripts/test-dry-run.py` | Unit tests for mock system |

## Directory Structure

```
agents/
├── astro-dwh-mcp/src/
│   ├── server.py          # MCP server with DRY_RUN support
│   └── mocks.py           # Mock response system
├── tests/
│   ├── expected-flows/    # Expected behavior definitions
│   │   └── hitl-operators.yaml
│   ├── mocks/             # Mock response files
│   │   └── hitl-mocks.yaml
│   ├── real-queries.txt   # Evaluation queries
│   └── evaluation-queries.yaml
├── scripts/               # Testing tools
│   ├── ralph-loop.sh
│   ├── compare-flows.py
│   ├── review-skill.py
│   └── split-test.py
└── docs/
    └── skill-testing.md   # This file
```

## Ralph Loop Pattern

The Ralph Loop provides fresh context per iteration, essential for testing Claude's decision-making:

```bash
# Run until skill passes expected flow
./scripts/ralph-loop.sh \
  --query "Find HITL customers" \
  --expected tests/expected-flows/hitl-operators.yaml \
  --max-iterations 5
```

Each iteration:
1. Starts with clean context (no prior conversation)
2. Runs the query against the skill
3. Captures the flow trace
4. Compares to expected behavior
5. If mismatch: reviews skill and suggests changes
6. Repeats until expected flow is achieved

State is persisted via files in `.ralph/`:
- `.ralph/current_iteration.txt` - Iteration counter
- `.ralph/last_trace.json` - Most recent flow trace
- `.ralph/suggestions.md` - Skill improvement suggestions

## A/B Testing with split-test.py

Compare different configurations:

```bash
uv run python scripts/split-test.py \
  --queries tests/real-queries.txt \
  --plugin-dir ./claude-code-plugin \
  --timeout 300 \
  --output /tmp/eval-results.json
```

Configurations tested:
- `baseline` - All optimizations enabled
- `no_warehouse_md` - Without warehouse.md
- `no_cache` - Without pre-populated cache
- `neither` - Without both

## Adding New Test Cases

### 1. Define Expected Flow

```yaml
# tests/expected-flows/my-query.yaml
name: My Test Query
description: What this tests

expected:
  - action: read
    pattern: "SKILL.md"
  - action: lookup_concept
  - action: run_sql
    pattern: "SELECT.*FROM.*MY_TABLE"
```

### 2. Create Mock Responses

```yaml
# tests/mocks/my-query-mocks.yaml
run_sql:
  - pattern: "MY_TABLE"
    response: |
      shape: (5, 3)
      | ID | NAME | VALUE |
      | 1 | Test | 100 |
```

### 3. Run Test

```bash
export DRY_RUN_MODE=true
export MOCK_RESPONSES_FILE=tests/mocks/my-query-mocks.yaml
export FLOW_TRACE_FILE=/tmp/my-test-trace.json

claude --plugin-dir ./claude-code-plugin "My test query"

python scripts/compare-flows.py /tmp/my-test-trace.json tests/expected-flows/my-query.yaml
```

## Troubleshooting

### Trace file is empty
Ensure `FLOW_TRACE_FILE` is set and the directory is writable.

### Mock not matching
Check pattern syntax - uses Python regex. Test patterns:
```python
import re
re.search("YOUR_PATTERN", "query text", re.IGNORECASE)
```

### Agent ignores skill instructions
This is the core problem this framework helps debug. Use flow tracing to identify where the agent deviates, then modify the skill's wording to guide it correctly.

## Success Metrics

From our testing, we found:
- **CLAUDE.md Quick Reference** is essential (100% success vs 25% without)
- **Pre-populated cache** adds ~39% speedup
- **warehouse.md alone** is often ignored by the agent
- **Strict tool limits** cause timeouts - use soft guidance instead
