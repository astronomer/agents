# Testing Scripts

Tools for testing and iterating on Claude skills.

## Scripts Overview

| Script | Purpose | Usage |
|--------|---------|-------|
| `ralph-loop.sh` | Iterate on skills with fresh context per turn | `./ralph-loop.sh "query" expected.yaml` |
| `split-test.py` | A/B test configurations | `uv run python split-test.py --queries tests/real-queries.txt` |
| `compare-flows.py` | Compare actual vs expected flows | `python compare-flows.py trace.json expected.yaml` |
| `review-skill.py` | Analyze skill and suggest improvements | `uv run python review-skill.py SKILL.md` |
| `run-flow-test.sh` | Run single flow test with mocks | `./run-flow-test.sh "query"` |
| `run-dry-warehouse.sh` | Start MCP server in dry-run mode | `./run-dry-warehouse.sh` |
| `test-dry-run.py` | Unit tests for mock system | `uv run python test-dry-run.py` |

## ralph-loop.sh

The Ralph Loop provides fresh context per iteration - essential for testing how Claude makes decisions without prior conversation bias.

```bash
# Basic usage
./scripts/ralph-loop.sh "Find HITL customers" tests/expected-flows/hitl-operators.yaml

# With custom iterations
MAX_ITERATIONS=5 ./scripts/ralph-loop.sh "query" expected.yaml

# With custom plugin directory
PLUGIN_DIR=./claude-code-plugin ./scripts/ralph-loop.sh "query" expected.yaml
```

**State directory:** `.ralph/`
- `iteration_N/trace.json` - Flow trace from MCP server
- `iteration_N/output.txt` - Claude output
- `current_iteration` - Counter file
- `status` - RUNNING/PASS/FAIL/BLOCKED

**History directory:** `.ralph-history/`
- Persists learnings across sessions
- Tracks what worked and what didn't

## split-test.py

A/B test different configurations to measure impact:

```bash
# Test single query across all configs
uv run python scripts/split-test.py --query "Find HITL operator customers"

# Test multiple queries from file
uv run python scripts/split-test.py \
  --queries tests/real-queries.txt \
  --plugin-dir ./claude-code-plugin \
  --timeout 300 \
  --output /tmp/eval-results.json
```

**Configurations tested:**
- `baseline` - All optimizations enabled
- `no_warehouse_md` - Without warehouse.md
- `no_cache` - Without pre-populated cache
- `neither` - Without both

**Output:** JSON with success rates, timing, and tool call counts per configuration.

## compare-flows.py

Compare actual agent behavior to expected flow:

```bash
python scripts/compare-flows.py /tmp/flow-trace.json tests/expected-flows/hitl-operators.yaml
```

**Output:**
```
Flow Comparison Results:
[OK] Step 1: read SKILL.md
[OK] Step 2: lookup_concept
[FAIL] Step 3: Expected run_sql with HITL, got list_schemas

Summary: 2/3 steps matched
```

## review-skill.py

Analyze a skill file and suggest improvements:

```bash
# Human-readable output
uv run python scripts/review-skill.py shared-skills/analyzing-data/SKILL.md

# JSON output (for automation)
uv run python scripts/review-skill.py shared-skills/analyzing-data/SKILL.md --format json
```

**Checks performed:**
- Required sections present
- Clear decision tree
- Reference file mentions
- Anti-pattern detection

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DRY_RUN_MODE` | Enable mock responses | `false` |
| `MOCK_RESPONSES_FILE` | Path to mock YAML | - |
| `FLOW_TRACE_FILE` | Path to write flow trace | `/tmp/flow-trace.json` |
| `MAX_ITERATIONS` | Ralph loop max iterations | `10` |
| `PLUGIN_DIR` | Claude plugin directory | `./test-plugin` |

## Workflow Example

1. **Define expected behavior:**
   ```bash
   vim tests/expected-flows/my-query.yaml
   ```

2. **Create mocks:**
   ```bash
   vim tests/mocks/my-query-mocks.yaml
   ```

3. **Run with Ralph Loop:**
   ```bash
   ./scripts/ralph-loop.sh "my query" tests/expected-flows/my-query.yaml
   ```

4. **Iterate until pass:**
   - Ralph Loop detects failures
   - Suggests skill modifications
   - Reruns with fresh context

5. **Validate with real warehouse:**
   ```bash
   uv run python scripts/split-test.py --query "my query"
   ```

## Dependencies

Scripts use `uv run` for Python dependencies. Ensure you have:
- `uv` package manager
- PyYAML (`uv pip install pyyaml`)
- Claude Code CLI

## See Also

- `docs/skill-testing.md` - Full framework documentation
- `tests/README.md` - Test data and fixtures
- `astro-dwh-mcp/src/mocks.py` - Mock response implementation
