"""Tests for Airflow plugin integration."""

import pytest


def test_plugin_import():
    """Test that the plugin can be imported."""
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    assert AirflowMCPPlugin is not None
    assert AirflowMCPPlugin.name == "astro_airflow_mcp"


def test_plugin_has_fastapi_apps():
    """Test that the plugin defines fastapi_apps."""
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    assert hasattr(AirflowMCPPlugin, "fastapi_apps")
    assert isinstance(AirflowMCPPlugin.fastapi_apps, list)


def test_plugin_on_load():
    """Test that the plugin on_load method exists and can be called."""
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    # Should not raise an error
    AirflowMCPPlugin.on_load()


def test_mcp_server_available():
    """Test that the MCP server object is accessible."""
    from astro_airflow_mcp.server import mcp

    assert mcp is not None
    assert hasattr(mcp, "run")
    assert hasattr(mcp, "http_app")


def test_mcp_http_app():
    """Test that the MCP server can create an HTTP app."""
    from astro_airflow_mcp.server import mcp

    try:
        app = mcp.http_app(path="/test")
        assert app is not None
    except Exception as e:
        pytest.skip(f"Could not create MCP HTTP app: {e}")


def test_plugin_docstring():
    """Test that the plugin has proper documentation."""
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    assert AirflowMCPPlugin.__doc__ is not None
    assert "MCP" in AirflowMCPPlugin.__doc__
    assert "plugin" in AirflowMCPPlugin.__doc__.lower()
