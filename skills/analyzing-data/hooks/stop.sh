#!/bin/bash
# Hook: Stop - shut down the analyzing-data kernel if one is running.
#
# No-op if `uv` isn't on PATH. The kernel can only ever have been started
# via `uv run` (see cli.py's own start/status commands), so if `uv` is
# missing there is nothing to stop, and a hard failure here would just
# surface a raw "uv: not found" shell error on every Stop hook run.

if ! command -v uv > /dev/null 2>&1; then
    exit 0
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv run "$script_dir/../scripts/cli.py" stop
