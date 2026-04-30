"""Tests for AdapterManager wiring of auth flows."""

from __future__ import annotations

from astro_airflow_mcp.adapter_manager import AdapterManager
from astro_airflow_mcp.astro_pat import AstroPATAuth


class TestAdapterManagerAuthRouting:
    def test_astro_pat_constructs_pat_auth(self):
        m = AdapterManager()
        m.configure(
            url="https://example.com",
            auth_kind="astro_pat",
            astro_context="astronomer.io",
        )
        assert isinstance(m._auth_handler, AstroPATAuth)
        # The token_manager should NOT be created in this mode.
        assert m._token_manager is None
        assert m._auth_token is None

    def test_static_token_does_not_construct_pat_auth(self):
        m = AdapterManager()
        m.configure(url="https://example.com", auth_token="static-bearer")
        assert m._auth_handler is None
        assert m._auth_token == "static-bearer"

    def test_basic_auth_does_not_construct_pat_auth(self):
        m = AdapterManager()
        m.configure(url="https://example.com", username="u", password="p")
        assert m._auth_handler is None
        assert m._auth_token is None
        assert m._token_manager is not None

    def test_reconfigure_clears_prior_auth(self):
        # First configure for PAT, then for static token: prior PAT handler
        # must be cleared so we don't double-attach.
        m = AdapterManager()
        m.configure(url="https://x", auth_kind="astro_pat", astro_context="astronomer.io")
        assert isinstance(m._auth_handler, AstroPATAuth)
        m.configure(url="https://x", auth_token="t")
        assert m._auth_handler is None
        assert m._auth_token == "t"

    def test_pat_with_no_context_uses_active(self):
        # No astro_context → resolver uses active context from disk at
        # request time. Manager should still construct the handler.
        m = AdapterManager()
        m.configure(url="https://example.com", auth_kind="astro_pat")
        assert isinstance(m._auth_handler, AstroPATAuth)
        assert m._auth_handler._resolver.domain is None

    def test_get_adapter_passes_handler_through(self, mocker):
        # AdapterManager.get_adapter() must thread auth_handler into
        # create_adapter so the adapter uses it on every HTTP call.
        m = AdapterManager()
        m.configure(
            url="https://example.com",
            auth_kind="astro_pat",
            astro_context="astronomer.io",
        )

        captured = {}

        def fake_create_adapter(**kwargs):
            captured.update(kwargs)
            adapter = mocker.Mock()
            adapter.version = "3.2.0"
            return adapter

        mocker.patch(
            "astro_airflow_mcp.adapter_manager.create_adapter",
            side_effect=fake_create_adapter,
        )
        m.get_adapter()
        assert isinstance(captured["auth_handler"], AstroPATAuth)
