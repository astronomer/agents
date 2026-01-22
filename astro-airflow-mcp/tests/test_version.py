"""Tests for version information."""

import astro_airflow_mcp


def test_version_exists():
    """Test that __version__ attribute exists."""
    assert hasattr(astro_airflow_mcp, "__version__")


def test_version_format():
    """Test that __version__ is a valid version string."""
    version = astro_airflow_mcp.__version__
    assert isinstance(version, str)
    assert len(version) > 0
    # Should follow semantic versioning (e.g., "0.1.0")
    parts = version.split(".")
    assert len(parts) >= 2, "Version should have at least major.minor"
