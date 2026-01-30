"""Tests for MCP server configuration."""

import pytest

from astro_observe_mcp.server import (
    _config,
    _reset_client,
    configure,
    get_organization_id,
)


class TestServerConfiguration:
    """Tests for server configuration."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset configuration before and after each test."""
        # Store original
        original_org_id = _config.organization_id
        original_api_url = _config.api_url
        original_token_manager = _config.token_manager

        # Reset before test
        _config.organization_id = None
        _config.api_url = "https://api.astronomer.io"
        _config.token_manager = None
        _reset_client()

        yield

        # Restore after test
        _config.organization_id = original_org_id
        _config.api_url = original_api_url
        _config.token_manager = original_token_manager
        _reset_client()

    def test_configure_sets_organization_id(self):
        """configure should set organization ID."""
        configure(organization_id="test-org-id", token="test-token")

        assert get_organization_id() == "test-org-id"

    def test_configure_sets_api_url(self):
        """configure should set custom API URL."""
        configure(
            organization_id="test-org-id",
            token="test-token",
            api_url="https://custom.api.com",
        )

        assert _config.api_url == "https://custom.api.com"

    def test_configure_creates_token_manager(self):
        """configure should create token manager."""
        configure(organization_id="test-org-id", token="test-token")

        assert _config.token_manager is not None
        assert _config.token_manager.get_token() == "test-token"

    def test_configure_resets_client(self):
        """configure should reset existing client."""
        # First configure
        configure(organization_id="org-1", token="token-1")

        # Reconfigure
        configure(organization_id="org-2", token="token-2")

        # Client should be reset
        from astro_observe_mcp.server import _client as new_client

        assert new_client is None
