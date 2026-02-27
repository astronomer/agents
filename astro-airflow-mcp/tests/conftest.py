"""Root test configuration."""

import os

# Disable telemetry during all tests to avoid firing real events
os.environ["AF_TELEMETRY_DISABLED"] = "1"
