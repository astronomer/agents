#!/bin/bash
# Hook: SessionStart - Warm the af / uvx cache so the first real call is fast.
#
# `af` on PATH is typically a thin shell wrapper that exec's
# `uvx --from 'astro-airflow-mcp==<pin>' af`, so invoking it once warms the
# uvx cache for whichever pin the wrapper installs. No-op if `af` isn't on
# PATH (the skill's body tells the user how to install it).

(af --version > /dev/null 2>&1 &)

exit 0
