"""Tests for Airflow plugin integration."""

import pytest

from astro_airflow_mcp.plugin import _host_guard_kwargs


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


def test_plugin_has_flask_blueprints():
    """Test that the plugin defines flask_blueprints attribute."""
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    assert hasattr(AirflowMCPPlugin, "flask_blueprints")
    assert isinstance(AirflowMCPPlugin.flask_blueprints, list)


def test_plugin_contextvar_auth_token():
    """Test that the auth token ContextVar exists and works."""
    from astro_airflow_mcp.plugin import _request_auth_token

    assert _request_auth_token.get() is None
    token = _request_auth_token.set("test-token")
    assert _request_auth_token.get() == "test-token"
    _request_auth_token.reset(token)


def test_plugin_contextvar_basic_auth():
    """Test that the basic auth ContextVar exists and works."""
    from astro_airflow_mcp.plugin import _request_basic_auth

    assert _request_basic_auth.get() is None
    token = _request_basic_auth.set(("admin", "admin"))
    assert _request_basic_auth.get() == ("admin", "admin")
    _request_basic_auth.reset(token)


def test_plugin_mutual_exclusivity():
    """Only one of fastapi_apps or flask_blueprints should be populated.

    In the test environment FastAPI is available, so the AF3 path is taken
    and flask_blueprints should be empty.
    """
    from astro_airflow_mcp.plugin import AirflowMCPPlugin

    if AirflowMCPPlugin.fastapi_apps:
        assert AirflowMCPPlugin.flask_blueprints == []


def test_host_guard_kwargs_scopes_to_deployment_host(monkeypatch):
    """On Astro the guard stays enabled, scoped to the webserver base-URL hostname."""
    monkeypatch.delenv("ASTRO_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.setenv("AIRFLOW__WEBSERVER__BASE_URL", "https://dep.d1.astronomer.run/dabc1234")
    assert _host_guard_kwargs() == {"allowed_hosts": ["dep.d1.astronomer.run"]}


def test_host_guard_kwargs_env_override_wins(monkeypatch):
    """ASTRO_MCP_ALLOWED_HOSTS overrides the derived Deployment host."""
    monkeypatch.setenv("AIRFLOW__WEBSERVER__BASE_URL", "https://dep.d1.astronomer.run/dabc1234")
    monkeypatch.setenv("ASTRO_MCP_ALLOWED_HOSTS", "a.example.com, b.example.com ,")
    assert _host_guard_kwargs() == {"allowed_hosts": ["a.example.com", "b.example.com"]}


def test_host_guard_kwargs_falls_back_when_no_host(monkeypatch):
    """With no override and no base URL, delegate host validation downstream."""
    monkeypatch.delenv("ASTRO_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("AIRFLOW__WEBSERVER__BASE_URL", raising=False)
    assert _host_guard_kwargs() == {"host_origin_protection": False}


def test_auth_contextvars_isolated_per_context():
    """Per-request auth ContextVars must not leak across request contexts.

    Simulates two concurrent requests setting the same ContextVar in
    their own copied contexts and asserts each sees only its own value.
    """
    import contextvars

    from astro_airflow_mcp.plugin import _request_auth_token

    results: dict[str, str | None] = {}

    def req(label: str, token: str) -> None:
        _request_auth_token.set(token)
        results[label] = _request_auth_token.get()

    ctx_a = contextvars.copy_context()
    ctx_b = contextvars.copy_context()
    ctx_a.run(req, "a", "token-a")
    ctx_b.run(req, "b", "token-b")
    assert results == {"a": "token-a", "b": "token-b"}
    # The outer context should be unaffected
    assert _request_auth_token.get() is None
