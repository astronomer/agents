#!/bin/bash
# Run Claude Code benchmark with real execution

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================================="
echo "Claude Code Real Execution Benchmark"
echo "=================================================="
echo ""

# Check Claude Code is installed
if ! command -v claude &> /dev/null; then
    echo -e "${RED}❌ Claude Code not found${NC}"
    echo "Install from: https://code.claude.com"
    exit 1
fi

echo -e "${GREEN}✓ Claude Code found${NC}"

# Check if logged in to Astro
if ! astro auth whoami &> /dev/null; then
    echo -e "${YELLOW}⚠️  Not logged in to Astro${NC}"
    echo "Run: astro login"
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ Logged in to Astro${NC}"
fi

# Get org ID from config
ORG_ID=$(grep -A 1 "context: astronomer.io" ~/.astro/config.yaml | grep "organization:" | awk '{print $2}' || echo "")

# Parse arguments
MODELS="haiku sonnet"
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --all-models)
            MODELS="haiku sonnet opus"
            shift
            ;;
        --fast)
            MODELS="haiku"
            shift
            ;;
        --org-id)
            ORG_ID="$2"
            shift 2
            ;;
        --output)
            OUTPUT="--output $2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all-models    Test Haiku, Sonnet, and Opus"
            echo "  --fast          Test only Haiku (fastest)"
            echo "  --org-id ID     Specify Astro organization ID"
            echo "  --output FILE   Output file path"
            exit 1
            ;;
    esac
done

echo ""
echo "Configuration:"
echo "  Models: $MODELS"
echo "  Org ID: ${ORG_ID:-'Will use astro CLI context'}"
echo ""

# Build command
CMD="python3 claude_code_benchmark.py --models $MODELS"
if [ -n "$ORG_ID" ]; then
    CMD="$CMD --org-id $ORG_ID"
fi
if [ -n "$OUTPUT" ]; then
    CMD="$CMD $OUTPUT"
fi

echo -e "${GREEN}Starting benchmark...${NC}"
echo ""

eval $CMD

echo ""
echo -e "${GREEN}✓ Benchmark complete!${NC}"
