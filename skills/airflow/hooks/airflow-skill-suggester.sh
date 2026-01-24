#!/bin/bash
# Hook: UserPromptSubmit - Suggest Airflow skill when Airflow keywords detected
# This hook runs before Claude processes the user's prompt and can inject context

# Read user prompt from stdin
USER_PROMPT=$(cat)

# Define Airflow-related keywords (case insensitive)
AIRFLOW_KEYWORDS=(
    "airflow"
    "dag"
    "dags"
    "pipeline"
    "pipelines"
    "workflow"
    "workflows"
    "task instance"
    "task run"
    "connection"
    "variable"
    "pool"
    "trigger dag"
    "test dag"
    "debug dag"
    "dag fail"
    "list dags"
    "show dags"
    "get dag"
    "dag status"
    "dag run"
    "astro dev"
)

# Check if prompt contains any Airflow keywords
MATCHED=false
PROMPT_LOWER=$(echo "$USER_PROMPT" | tr '[:upper:]' '[:lower:]')

for keyword in "${AIRFLOW_KEYWORDS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -q "$keyword"; then
        MATCHED=true
        break
    fi
done

# If Airflow keywords detected, inject skill suggestion
if [ "$MATCHED" = true ]; then
    # Check if user already explicitly mentioned using the skill
    if echo "$PROMPT_LOWER" | grep -q "use.*skill\|/data:airflow"; then
        # User already wants to use the skill, no need to inject
        exit 0
    fi

    # Inject context to suggest using the Airflow skill
    cat <<'EOF'
🎯 Airflow operation detected!

IMPORTANT: Use the `/data:airflow` skill for Airflow operations. This skill provides:
- Structured workflow guidance
- Best practices for MCP tool usage
- Routing to specialized skills (testing, debugging, authoring)
- Prevention of bash/CLI antipatterns

Load the skill first: `/data:airflow`

Then proceed with the user's request.
EOF
    exit 0
fi

# No Airflow keywords found, pass through
exit 0
