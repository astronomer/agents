#!/bin/bash
# Hook: UserPromptSubmit - Suggest Airflow skills when relevant keywords detected
# Routes to specific skills based on context, with the general airflow skill as fallback

# Read user prompt from stdin
USER_PROMPT=$(cat)

PROMPT_LOWER=$(echo "$USER_PROMPT" | tr '[:upper:]' '[:lower:]')

# Check if user already explicitly mentioned using a skill
if echo "$PROMPT_LOWER" | grep -q "use.*skill\|/astronomer-data:"; then
    exit 0
fi

# --- Route 1: Deploy keywords -> deploying-airflow skill ---
DEPLOY_KEYWORDS=(
    "astro deploy"
    "deploy.*dag"
    "deploy.*airflow"
    "deploy.*pipeline"
    "dag-only deploy"
    "dags-only deploy"
    "airflow.*ci/cd"
    "airflow.*ci cd"
)

for keyword in "${DEPLOY_KEYWORDS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -qE "$keyword"; then
        cat <<'EOF'
Deployment request detected.

IMPORTANT: Use the `/astronomer-data:deploying-airflow` skill for deployment operations. This skill covers:
- Astro deploy commands (full, DAG-only, image-only, dbt)
- CI/CD setup and GitHub integration
- Open-source deployment (Docker Compose, Kubernetes Helm chart)

Load the skill: `/astronomer-data:deploying-airflow`

Then proceed with the user's request.
EOF
        exit 0
    fi
done

# --- Route 2: Local dev / setup keywords -> managing-astro-local-env ---
LOCAL_KEYWORDS=(
    "run airflow locally"
    "run airflow local"
    "local airflow"
    "start airflow"
    "install airflow"
    "set up airflow"
    "setup airflow"
    "astro dev start"
    "astro dev init"
    "astro dev"
    "airflow local"
)

for keyword in "${LOCAL_KEYWORDS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -qE "$keyword"; then
        cat <<'EOF'
Local Airflow environment request detected.

IMPORTANT: Use the `/astronomer-data:managing-astro-local-env` skill for local environment management. The Astro CLI is the recommended way to run Airflow locally:
- `astro dev init` to initialize a project
- `astro dev start` to start a local Airflow environment
- `astro dev parse` to validate DAGs
- `astro dev pytest` to run tests

Load the skill: `/astronomer-data:managing-astro-local-env`

Then proceed with the user's request.
EOF
        exit 0
    fi
done

# --- Route 3: General Airflow keywords -> airflow skill ---
# Split into strong signals (compound phrases, one match fires) and
# weak signals (single words with word boundaries, need 2+ to fire
# or 1 if the prompt doesn't look like a data query).

STRONG_SIGNALS=(
    "trigger dag"
    "test dag"
    "debug dag"
    "list dags"
    "show dags"
    "get dag"
    "dag status"
    "dag fail"
    "task instance"
    "airflow.*connection"
    "airflow.*variable"
    "airflow.*pool"
    "airflow.*pipeline"
    "airflow.*workflow"
)

for keyword in "${STRONG_SIGNALS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -qE "$keyword"; then
        cat <<'EOF'
Airflow operation detected.

IMPORTANT: Use the `/astronomer-data:airflow` skill for Airflow operations. This skill provides:
- Structured workflow guidance
- Best practices for MCP tool usage
- Routing to specialized skills (testing, debugging, authoring, deploying)
- Prevention of bash/CLI antipatterns

Load the skill first: `/astronomer-data:airflow`

Then proceed with the user's request.
EOF
        exit 0
    fi
done

# Weak signals — need 2+ matches to fire, or 1 if no data-query context
WEAK_SIGNALS=(
    '\bdag\b'
    '\bdags\b'
    '\bairflow\b'
    '\bdag.run\b'
    '\btask.run\b'
)

WEAK_COUNT=0
for keyword in "${WEAK_SIGNALS[@]}"; do
    if echo "$PROMPT_LOWER" | grep -qE "$keyword"; then
        ((WEAK_COUNT++))
    fi
done

if [ "$WEAK_COUNT" -gt 0 ]; then
    # Data-query signals — suppress when only 1-2 weak signals match
    DATA_QUERY_SIGNALS=(
        "how many"
        "show me"
        "query"
        "profile"
        "freshness"
        "count of"
        "trend"
        "customer"
        "volume"
        "percentage"
        '\btable\b'
        "select "
        "warehouse"
        "what.*percent"
        "what.*number"
    )

    IS_DATA_QUERY=false
    for keyword in "${DATA_QUERY_SIGNALS[@]}"; do
        if echo "$PROMPT_LOWER" | grep -qE "$keyword"; then
            IS_DATA_QUERY=true
            break
        fi
    done

    SHOULD_FIRE=false
    if [ "$WEAK_COUNT" -ge 3 ]; then
        # 3+ weak signals — fire regardless of data-query context
        SHOULD_FIRE=true
    elif [ "$WEAK_COUNT" -ge 2 ] && [ "$IS_DATA_QUERY" = false ]; then
        # 2 weak signals and not a data query
        SHOULD_FIRE=true
    elif [ "$WEAK_COUNT" -ge 1 ] && [ "$IS_DATA_QUERY" = false ]; then
        # 1 weak signal and not a data query
        SHOULD_FIRE=true
    fi

    if [ "$SHOULD_FIRE" = true ]; then
        cat <<'EOF'
Airflow operation detected.

IMPORTANT: Use the `/astronomer-data:airflow` skill for Airflow operations. This skill provides:
- Structured workflow guidance
- Best practices for MCP tool usage
- Routing to specialized skills (testing, debugging, authoring, deploying)
- Prevention of bash/CLI antipatterns

Load the skill first: `/astronomer-data:airflow`

Then proceed with the user's request.
EOF
        exit 0
    fi
fi

# No keywords found, pass through
exit 0
