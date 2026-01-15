#!/bin/bash
# Ralph Loop - Fresh context per iteration, file I/O as state
#
# Original vision by Geoffrey Huntley:
# - Fresh context per iteration (external bash loop)
# - File I/O as state (not transcript)
# - Dumb bash loop, deterministic setup
#
# Usage:
#   ./scripts/ralph-loop.sh "Find HITL customers" tests/expected-flows/hitl-operators.yaml
#   MAX_ITERATIONS=5 ./scripts/ralph-loop.sh "query" expected.yaml
#
# State directory: .ralph/
#   - iteration_N/trace.json    - Flow trace from MCP server
#   - iteration_N/output.txt    - Claude output
#   - iteration_N/result.json   - Pass/fail and analysis
#   - current_iteration         - Counter file
#   - status                    - RUNNING/PASS/FAIL/BLOCKED

set -e

QUERY="${1:?Usage: ralph-loop.sh <query> [expected-flow.yaml]}"
EXPECTED_FLOW="${2:-tests/expected-flows/hitl-operators.yaml}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
PLUGIN_DIR="${PLUGIN_DIR:-./test-plugin}"
SKILL_PATH="${SKILL_PATH:-shared-skills/analyzing-data/SKILL.md}"
HISTORY_DIR=".ralph-history"
SESSION_ID=$(date +%Y%m%d_%H%M%S)
STATE_DIR=".ralph"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[RALPH]${NC} $1"; }
warn() { echo -e "${YELLOW}[RALPH]${NC} $1"; }
error() { echo -e "${RED}[RALPH]${NC} $1"; }

# Run skill review as quality gate
review_skill() {
    log "Running skill review on: $SKILL_PATH"

    if [ ! -f "$SKILL_PATH" ]; then
        warn "Skill file not found: $SKILL_PATH"
        return 1
    fi

    # Run the skill review script
    local review_result
    review_result=$(uv run "$SCRIPT_DIR/review-skill.py" "$SKILL_PATH" --format json 2>/dev/null) || true

    if [ -z "$review_result" ]; then
        warn "Skill review script failed to run"
        return 1
    fi

    # Parse result
    local pass_review=$(echo "$review_result" | grep -o '"pass": [^,}]*' | head -1 | cut -d' ' -f2)
    local score=$(echo "$review_result" | grep -o '"score": [0-9]*' | cut -d' ' -f2)

    # Save review result
    echo "$review_result" > "$STATE_DIR/skill_review.json"

    if [ "$pass_review" = "true" ]; then
        log "Skill review PASSED (score: $score/100)"
        return 0
    else
        error "Skill review FAILED (score: $score/100)"
        error "Fix skill issues before continuing. See $STATE_DIR/skill_review.json"
        return 1
    fi
}

# Initialize state directory
init_state() {
    log "Initializing state directory: $STATE_DIR"
    mkdir -p "$STATE_DIR"
    mkdir -p "$HISTORY_DIR"

    echo "0" > "$STATE_DIR/current_iteration"
    echo "RUNNING" > "$STATE_DIR/status"
    echo "$QUERY" > "$STATE_DIR/query"
    echo "$EXPECTED_FLOW" > "$STATE_DIR/expected_flow"
    echo "$SESSION_ID" > "$STATE_DIR/session_id"

    # Initialize session learning log (append to global history)
    echo "" >> "$HISTORY_DIR/learnings.md"
    echo "---" >> "$HISTORY_DIR/learnings.md"
    echo "# Session: $SESSION_ID - $(date -Iseconds)" >> "$HISTORY_DIR/learnings.md"
    echo "Query: $QUERY" >> "$HISTORY_DIR/learnings.md"
    echo "Expected flow: $EXPECTED_FLOW" >> "$HISTORY_DIR/learnings.md"
    echo "" >> "$HISTORY_DIR/learnings.md"

    # Also create session-specific directory
    mkdir -p "$HISTORY_DIR/$SESSION_ID"
    echo "$QUERY" > "$HISTORY_DIR/$SESSION_ID/query"
}

# Log a learning to the append-only log
log_learning() {
    local iteration=$1
    local learning=$2

    # Log to global history (append-only)
    echo "### Iteration $iteration - $(date -Iseconds)" >> "$HISTORY_DIR/learnings.md"
    echo "$learning" >> "$HISTORY_DIR/learnings.md"
    echo "" >> "$HISTORY_DIR/learnings.md"

    # Also copy to session directory
    echo "$learning" > "$HISTORY_DIR/$SESSION_ID/iteration_$iteration.md"
}

# Get current iteration number
get_iteration() {
    cat "$STATE_DIR/current_iteration"
}

# Increment iteration
next_iteration() {
    local current=$(get_iteration)
    local next=$((current + 1))
    echo "$next" > "$STATE_DIR/current_iteration"
    echo "$next"
}

# Run single iteration with fresh context
run_iteration() {
    local iter=$1
    local iter_dir="$STATE_DIR/iteration_$iter"
    mkdir -p "$iter_dir"

    log "=== Iteration $iter of $MAX_ITERATIONS ==="

    # Clear previous trace files (fresh state)
    rm -f /tmp/flow-trace.json /tmp/flow-trace.early_exit
    rm -f /tmp/ralph-tool-trace.jsonl  # Hook-based trace

    # Run Claude with fresh context
    log "Running query with fresh context..."
    local start_time=$(date +%s)

    # Timeout after 60 seconds to prevent hanging
    timeout 60 claude --plugin-dir "$PLUGIN_DIR" \
        -p "$QUERY" \
        --output-format text \
        > "$iter_dir/output.txt" 2>&1 || true

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Copy MCP trace file
    if [ -f /tmp/flow-trace.json ]; then
        cp /tmp/flow-trace.json "$iter_dir/trace.json"
        log "MCP trace captured: $iter_dir/trace.json"
    else
        warn "No MCP trace file generated"
        echo '{"trace": [], "error": "no trace generated"}' > "$iter_dir/trace.json"
    fi

    # Copy hook-based trace (captures ALL tools including WebFetch)
    if [ -f /tmp/ralph-tool-trace.jsonl ]; then
        cp /tmp/ralph-tool-trace.jsonl "$iter_dir/tool-trace.jsonl"
        log "Hook trace captured: $iter_dir/tool-trace.jsonl"
    else
        warn "No hook trace generated"
    fi

    # Check for early exit (real query in DRY_RUN mode)
    if [ -f /tmp/flow-trace.early_exit ]; then
        error "EARLY EXIT: Real query executed in DRY_RUN mode"
        cp /tmp/flow-trace.early_exit "$iter_dir/early_exit.json"
        echo "BLOCKED" > "$STATE_DIR/status"
        echo '{"pass": false, "reason": "early_exit_real_query"}' > "$iter_dir/result.json"
        return 1
    fi

    # Analyze results
    analyze_iteration "$iter" "$iter_dir" "$duration"
}

# Analyze iteration results
analyze_iteration() {
    local iter=$1
    local iter_dir=$2
    local duration=$3

    log "Analyzing iteration $iter (took ${duration}s)..."

    # Check if expected flow file exists
    if [ ! -f "$EXPECTED_FLOW" ]; then
        warn "Expected flow file not found: $EXPECTED_FLOW"
        echo '{"pass": false, "reason": "no_expected_flow"}' > "$iter_dir/result.json"
        return 1
    fi

    # Check output for key indicators
    local output=$(cat "$iter_dir/output.txt")

    # Quick checks before full analysis
    local found_docs=false
    local found_approval=false
    local used_dry_run=false
    local webfetch_before_sql=false

    # Check output for mentions of docs/WebFetch
    if echo "$output" | grep -qi "airflow.apache.org\|WebFetch"; then
        found_docs=true
    fi

    if echo "$output" | grep -qi "ApprovalOperator"; then
        found_approval=true
    fi

    # Check for HITLAsyncGate - NEW operator not in Claude's training data
    # Can ONLY be found via WebFetch docs
    local found_new_operator=false
    if echo "$output" | grep -qi "HITLAsyncGate"; then
        found_new_operator=true
    fi

    # Check trace file for DRY_RUN mode (more reliable than output)
    if [ -f "$iter_dir/trace.json" ] && grep -q '"dry_run": true' "$iter_dir/trace.json"; then
        used_dry_run=true
    fi

    # Check HOOK trace for WebFetch BEFORE run_sql (captures ALL tools)
    local tool_sequence=""
    if [ -f "$iter_dir/tool-trace.jsonl" ]; then
        # Extract tool sequence from hook trace (JSONL format)
        tool_sequence=$(cat "$iter_dir/tool-trace.jsonl" | grep -o '"tool": "[^"]*"' | sed 's/"tool": "//g; s/"//g' | tr '\n' ',')

        # Check if WebFetch appears in trace
        if echo "$tool_sequence" | grep -qi "WebFetch"; then
            found_docs=true
            # Check if WebFetch came before any MCP warehouse tool
            local webfetch_pos=$(echo "$tool_sequence" | grep -boi "WebFetch" | head -1 | cut -d: -f1)
            local sql_pos=$(echo "$tool_sequence" | grep -boi "mcp__\|run_sql" | head -1 | cut -d: -f1)

            if [ -n "$webfetch_pos" ]; then
                if [ -z "$sql_pos" ] || [ "$webfetch_pos" -lt "$sql_pos" ]; then
                    webfetch_before_sql=true
                fi
            fi
        fi

        log "Tool sequence (from hooks): $tool_sequence"
    elif [ -f "$iter_dir/trace.json" ]; then
        # Fallback to MCP trace
        tool_sequence=$(cat "$iter_dir/trace.json" | grep -o '"tool": "[^"]*"' | sed 's/"tool": "//g; s/"//g' | tr '\n' ',')
        log "Tool sequence (from MCP): $tool_sequence"
    fi

    log "WebFetch before SQL: $webfetch_before_sql"

    # Create result JSON
    cat > "$iter_dir/result.json" << EOF
{
    "iteration": $iter,
    "duration_sec": $duration,
    "found_docs": $found_docs,
    "found_approval_operator": $found_approval,
    "found_new_operator": $found_new_operator,
    "webfetch_before_sql": $webfetch_before_sql,
    "used_dry_run": $used_dry_run,
    "pass": false,
    "analysis": ""
}
EOF

    # Determine pass/fail - STRICT: Must find HITLAsyncGate (new operator not in training data)
    # This can ONLY happen if agent WebFetched docs to discover it
    if $found_new_operator; then
        log "PASS: Found HITLAsyncGate - agent discovered NEW operator from docs!"
        echo "PASS" > "$STATE_DIR/status"
        cat > "$iter_dir/result.json" << EOF
{
    "iteration": $iter,
    "duration_sec": $duration,
    "found_docs": true,
    "found_approval_operator": $found_approval,
    "found_new_operator": true,
    "webfetch_before_sql": $webfetch_before_sql,
    "used_dry_run": $used_dry_run,
    "pass": true,
    "analysis": "SUCCESS: Agent discovered HITLAsyncGate (new in Airflow 3.1) - must have WebFetched docs!"
}
EOF
        return 0
    fi

    # Analyze what went wrong
    local analysis=""
    if ! $found_new_operator; then
        analysis="CRITICAL: Agent MISSED HITLAsyncGate (new in Airflow 3.1). "
        analysis="${analysis}This operator is NOT in Claude's training data - can ONLY be discovered via WebFetch docs. "
    fi
    if ! $webfetch_before_sql; then
        analysis="${analysis}Agent did NOT WebFetch docs before querying warehouse. "
    fi
    if $found_approval && ! $found_new_operator; then
        analysis="${analysis}Found ApprovalOperator (from training) but missed new operators. "
    fi
    if ! $used_dry_run; then
        analysis="${analysis}WARNING: DRY_RUN mode may not be active (check trace). "
    fi

    warn "FAIL: $analysis"

    # Log learning
    log_learning "$iter" "**Result:** FAIL

**What happened:**
- found_new_operator (HITLAsyncGate): $found_new_operator
- webfetch_before_sql: $webfetch_before_sql
- found_docs: $found_docs
- found_approval: $found_approval
- used_dry_run: $used_dry_run

**Analysis:** $analysis

**Trace summary:** $(cat "$iter_dir/trace.json" | grep -o '"tool": "[^"]*"' | sort | uniq -c | tr '\n' ', ')
"

    # Update result with analysis
    cat > "$iter_dir/result.json" << EOF
{
    "iteration": $iter,
    "duration_sec": $duration,
    "found_new_operator": $found_new_operator,
    "webfetch_before_sql": $webfetch_before_sql,
    "found_docs": $found_docs,
    "found_approval_operator": $found_approval,
    "used_dry_run": $used_dry_run,
    "pass": false,
    "analysis": "$analysis"
}
EOF

    return 1
}

# Print summary
print_summary() {
    log "=== Summary ==="
    local status=$(cat "$STATE_DIR/status")
    local iterations=$(get_iteration)

    echo "Status: $status"
    echo "Iterations: $iterations"
    echo "Query: $QUERY"
    echo ""

    # Show last result
    local last_iter=$((iterations))
    if [ -f "$STATE_DIR/iteration_$last_iter/result.json" ]; then
        echo "Last result:"
        cat "$STATE_DIR/iteration_$last_iter/result.json"
    fi
}

# Main loop
main() {
    log "Starting Ralph Loop"
    log "Query: $QUERY"
    log "Expected flow: $EXPECTED_FLOW"
    log "Max iterations: $MAX_ITERATIONS"
    log "Plugin dir: $PLUGIN_DIR"

    # Check plugin directory exists
    if [ ! -d "$PLUGIN_DIR" ]; then
        error "Plugin directory not found: $PLUGIN_DIR"
        exit 1
    fi

    init_state

    # Quality gate: Review skill before starting
    if ! review_skill; then
        error "Skill review failed - fix issues before running Ralph Loop"
        echo "BLOCKED" > "$STATE_DIR/status"
        exit 1
    fi

    while true; do
        local iter=$(next_iteration)

        if [ "$iter" -gt "$MAX_ITERATIONS" ]; then
            error "Max iterations ($MAX_ITERATIONS) reached"
            echo "BLOCKED" > "$STATE_DIR/status"
            break
        fi

        if run_iteration "$iter"; then
            log "SUCCESS after $iter iteration(s)"
            break
        fi

        local status=$(cat "$STATE_DIR/status")
        if [ "$status" = "BLOCKED" ]; then
            error "Blocked - manual intervention required"
            break
        fi

        log "Iteration $iter failed, will retry with fresh context..."
        sleep 2
    done

    print_summary
}

main
