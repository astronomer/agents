"""Pytest configuration for analyzing-data skill tests."""

import sys
from pathlib import Path

import pytest

# Add the scripts directory to the Python path for lib imports
scripts_dir = Path(__file__).parent.parent
sys.path.insert(0, str(scripts_dir))


@pytest.fixture(autouse=True)
def _no_config_dir_override(monkeypatch):
    """Keep a developer's ASTRO_AGENTS_CONFIG_DIR from leaking into tests."""
    monkeypatch.delenv("ASTRO_AGENTS_CONFIG_DIR", raising=False)
