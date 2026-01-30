"""Tests for Astro Cloud API client."""

import os
import re

import pytest
from pytest_httpx import HTTPXMock

from astro_observe_mcp.auth import AstroTokenManager
from astro_observe_mcp.client import (
    AstroAuthenticationError,
    AstroClient,
    AstroClientError,
    AstroNotFoundError,
)


@pytest.fixture
def token_manager():
    """Create a token manager with a test token."""
    return AstroTokenManager(token="test-token")


@pytest.fixture
def client(token_manager):
    """Create a test client."""
    return AstroClient(
        organization_id="test-org-id",
        token_manager=token_manager,
        api_url="https://api.test.astronomer.io",
    )


class TestAstroClient:
    """Tests for AstroClient."""

    def test_encode_asset_id(self):
        """Asset IDs should be base64url encoded."""
        asset_id = "snowflake://account/db/schema/table"
        encoded = AstroClient.encode_asset_id(asset_id)

        # Should be base64url without padding
        assert "=" not in encoded
        assert "+" not in encoded
        assert "/" not in encoded

    def test_decode_asset_id(self):
        """Encoded asset IDs should decode correctly."""
        original = "snowflake://account/db/schema/table"
        encoded = AstroClient.encode_asset_id(original)
        decoded = AstroClient.decode_asset_id(encoded)

        assert decoded == original

    def test_search_assets_success(self, client: AstroClient, httpx_mock: HTTPXMock):
        """search_assets should return results on success."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            json={
                "assets": [
                    {"id": "asset-1", "name": "table1", "type": "snowflakeTable"},
                    {"id": "asset-2", "name": "table2", "type": "snowflakeTable"},
                ],
                "totalCount": 2,
                "limit": 20,
                "offset": 0,
            },
        )

        result = client.search_assets(search="table")

        assert len(result["assets"]) == 2
        assert result["totalCount"] == 2

    def test_search_assets_with_filters(self, client: AstroClient, httpx_mock: HTTPXMock):
        """search_assets should pass filters as query params."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            json={"assets": [], "totalCount": 0},
        )

        client.search_assets(
            search="test",
            asset_types=["snowflakeTable"],
            namespaces=["prod"],
            limit=50,
        )

        request = httpx_mock.get_request()
        assert "search=test" in str(request.url)
        assert "assetTypes=snowflakeTable" in str(request.url)
        assert "namespaces=prod" in str(request.url)
        assert "limit=50" in str(request.url)

    def test_search_assets_limit_capped(self, client: AstroClient, httpx_mock: HTTPXMock):
        """search_assets should cap limit at 100."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            json={"assets": [], "totalCount": 0},
        )

        client.search_assets(limit=500)

        request = httpx_mock.get_request()
        assert "limit=100" in str(request.url)

    def test_get_asset_success(self, client: AstroClient, httpx_mock: HTTPXMock):
        """get_asset should return asset details on success."""
        asset_id = "snowflake://account/db/schema/table"
        encoded_id = AstroClient.encode_asset_id(asset_id)

        httpx_mock.add_response(
            url=f"https://api.test.astronomer.io/private/v1alpha1/organizations/test-org-id/observability/assets/{encoded_id}",
            json={"id": asset_id, "name": "table", "type": "snowflakeTable"},
        )

        result = client.get_asset(asset_id)

        assert result["id"] == asset_id

    def test_get_asset_not_found(self, client: AstroClient, httpx_mock: HTTPXMock):
        """get_asset should raise AstroNotFoundError on 404."""
        asset_id = "nonexistent"
        encoded_id = AstroClient.encode_asset_id(asset_id)

        httpx_mock.add_response(
            url=f"https://api.test.astronomer.io/private/v1alpha1/organizations/test-org-id/observability/assets/{encoded_id}",
            status_code=404,
        )

        with pytest.raises(AstroNotFoundError):
            client.get_asset(asset_id)

    def test_list_asset_filters_success(self, client: AstroClient, httpx_mock: HTTPXMock):
        """list_asset_filters should return filter values."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/asset-filters/namespace.*"),
            json={
                "assetFilters": [
                    {"value": "prod", "label": "Production"},
                    {"value": "dev", "label": "Development"},
                ],
                "totalCount": 2,
            },
        )

        result = client.list_asset_filters(filter_type="namespace")

        assert len(result["assetFilters"]) == 2

    def test_list_asset_filters_invalid_type(self, client: AstroClient):
        """list_asset_filters should raise ValueError for invalid filter type."""
        with pytest.raises(ValueError, match="Invalid filter type"):
            client.list_asset_filters(filter_type="invalid")

    def test_authentication_error_on_401(self, client: AstroClient, httpx_mock: HTTPXMock):
        """Should raise AstroAuthenticationError on 401."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            status_code=401,
        )

        with pytest.raises(AstroAuthenticationError):
            client.search_assets()

    def test_authentication_error_on_403(self, client: AstroClient, httpx_mock: HTTPXMock):
        """Should raise AstroAuthenticationError on 403."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            status_code=403,
        )

        with pytest.raises(AstroAuthenticationError):
            client.search_assets()

    def test_client_error_on_500(self, client: AstroClient, httpx_mock: HTTPXMock):
        """Should raise AstroClientError on server error."""
        httpx_mock.add_response(
            url=re.compile(r".*/private/v1alpha1/.*/observability/assets.*"),
            status_code=500,
            json={"message": "Internal server error"},
        )

        with pytest.raises(AstroClientError, match="500"):
            client.search_assets()

    def test_no_token_raises_error(self, tmp_path):
        """Should raise AstroAuthenticationError when no token available."""
        from unittest.mock import patch

        # Use a nonexistent config file to prevent reading from ~/.astro/config.yaml
        nonexistent_config = tmp_path / "nonexistent.yaml"

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", nonexistent_config):
            token_manager = AstroTokenManager()  # No token configured
            client = AstroClient(
                organization_id="test-org",
                token_manager=token_manager,
                api_url="https://api.test.astronomer.io",
            )

            # Clear any env vars
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop("ASTRO_API_TOKEN", None)
                token_manager.invalidate()

                with pytest.raises(AstroAuthenticationError, match="No authentication token found"):
                    client._get_headers()
