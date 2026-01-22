#!/bin/bash
# Run integration tests locally against a running Airflow instance
#
# Usage:
#   ./scripts/run-integration-tests.sh [airflow_url] [username] [password]
#
# Examples:
#   # Airflow 2.x (default admin:admin)
#   ./scripts/run-integration-tests.sh http://localhost:8080
#
#   # Airflow 3.x (default admin:admin)
#   ./scripts/run-integration-tests.sh http://localhost:8081
#
#   # Custom credentials
#   ./scripts/run-integration-tests.sh http://localhost:8080 myuser mypass

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

AIRFLOW_URL="${1:-${AIRFLOW_URL:-http://localhost:8080}}"
AIRFLOW_USERNAME="${2:-${AIRFLOW_USERNAME:-admin}}"
AIRFLOW_PASSWORD="${3:-${AIRFLOW_PASSWORD:-admin}}"

echo -e "${YELLOW}Integration Test Runner${NC}"
echo "========================"
echo "Airflow URL: $AIRFLOW_URL"
echo "Username: $AIRFLOW_USERNAME"
echo ""

# Check if Airflow is reachable (try both health endpoints)
echo -e "${YELLOW}Checking Airflow connectivity...${NC}"
if curl -sf "$AIRFLOW_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Airflow is reachable${NC}"
elif curl -sf "$AIRFLOW_URL/api/v2/monitor/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Airflow is reachable${NC}"
else
    echo -e "${RED}✗ Cannot reach Airflow at $AIRFLOW_URL${NC}"
    exit 1
fi

# Detect Airflow version
echo -e "${YELLOW}Detecting Airflow version...${NC}"

# Try v2 API first (Airflow 3.x)
VERSION_RESPONSE=$(curl -sf "$AIRFLOW_URL/api/v2/version" 2>/dev/null || echo "")
if [ -n "$VERSION_RESPONSE" ]; then
    VERSION=$(echo "$VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('version', 'unknown'))")
    echo -e "${GREEN}✓ Detected Airflow 3.x: $VERSION${NC}"
else
    # Try v1 API (Airflow 2.x)
    VERSION_RESPONSE=$(curl -sf -u "$AIRFLOW_USERNAME:$AIRFLOW_PASSWORD" "$AIRFLOW_URL/api/v1/version" 2>/dev/null || echo "")
    if [ -n "$VERSION_RESPONSE" ]; then
        VERSION=$(echo "$VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('version', 'unknown'))")
        echo -e "${GREEN}✓ Detected Airflow 2.x: $VERSION${NC}"
    else
        echo -e "${RED}✗ Could not detect Airflow version${NC}"
        exit 1
    fi
fi

export AIRFLOW_URL
export AIRFLOW_USERNAME
export AIRFLOW_PASSWORD

echo ""
echo -e "${YELLOW}Running integration tests...${NC}"
echo ""

uv run pytest tests/integration/ -v --tb=short

echo ""
echo -e "${GREEN}✓ Integration tests completed${NC}"
