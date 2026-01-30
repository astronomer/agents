"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def reset_server_state():
    """Reset server state before and after test.

    Use this fixture explicitly in tests that modify server state.
    Not autouse to avoid interfering with httpx_mock teardown.
    """
    from astro_observe_mcp.server import _config, _reset_client

    # Store original values
    original_org_id = _config.organization_id
    original_api_url = _config.api_url
    original_token_manager = _config.token_manager

    # Reset before test
    _config.organization_id = None
    _config.api_url = "https://api.astronomer.io"
    _config.token_manager = None
    _reset_client()

    yield

    # Restore original values
    _config.organization_id = original_org_id
    _config.api_url = original_api_url
    _config.token_manager = original_token_manager
    _reset_client()
