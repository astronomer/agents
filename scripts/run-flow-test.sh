#!/bin/bash
# Run a skill flow test with mocking enabled
#
# Usage:
#   ./scripts/run-flow-test.sh "Find HITL operator customers"
#   ./scripts/run-flow-test.sh "Find HITL customers" tests/expected-flows/hitl-operators.yaml
#
# Environment:
#   MOCK_FILE - Path to mock responses YAML (default: tests/mocks/hitl-mocks.yaml)
#   PLUGIN_DIR - Path to Claude Code plugin (default: ./claude-code-plugin)
#   TRACE_FILE - Output trace file (default: /tmp/flow-trace.json)

set -e

QUERY="${1:-Find customers using Human-in-the-loop operators}"
EXPECTED_FLOW="${2:-tests/expected-flows/hitl-operators.yaml}"
MOCK_FILE="${MOCK_FILE:-tests/mocks/hitl-mocks.yaml}"
PLUGIN_DIR="${PLUGIN_DIR:-./claude-code-plugin}"
TRACE_FILE="${TRACE_FILE:-/tmp/flow-trace-$(date +%s).json}"

echo "=== Flow Test ==="
echo "Query: $QUERY"
echo "Expected flow: $EXPECTED_FLOW"
echo "Mock file: $MOCK_FILE"
echo "Trace output: $TRACE_FILE"
echo ""

# Check prerequisites
if [ ! -f "$MOCK_FILE" ]; then
    echo "Error: Mock file not found: $MOCK_FILE"
    exit 1
fi

if [ ! -d "$PLUGIN_DIR" ]; then
    echo "Error: Plugin directory not found: $PLUGIN_DIR"
    exit 1
fi

# Run with DRY_RUN mode
echo "Running test..."
export DRY_RUN_MODE=true
export MOCK_RESPONSES_FILE="$MOCK_FILE"

# Note: This requires a way to capture the trace from Claude Code
# For now, we run the query and manually check the output
claude --plugin-dir "$PLUGIN_DIR" -p "$QUERY" | tee /tmp/flow-output.txt

echo ""
echo "=== Output saved to /tmp/flow-output.txt ==="
echo ""

# If expected flow file exists and we have a trace, compare them
if [ -f "$EXPECTED_FLOW" ] && [ -f "$TRACE_FILE" ]; then
    echo "Comparing with expected flow..."
    python scripts/compare-flows.py "$TRACE_FILE" "$EXPECTED_FLOW"
else
    echo "Note: To compare flows, provide a trace file and expected flow YAML"
    echo "  TRACE_FILE=/path/to/trace.json ./scripts/run-flow-test.sh ..."
fi
