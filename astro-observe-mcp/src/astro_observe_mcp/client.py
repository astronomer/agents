"""Astro Cloud API client for Observability endpoints.

Provides HTTP client for interacting with Astro Cloud Observability API,
including asset search, retrieval, and filter discovery.
"""

import base64
import logging
from typing import Any

import httpx

from astro_observe_mcp.auth import AstroTokenManager

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_API_URL = "https://api.astronomer.io"
DEFAULT_TIMEOUT = 30.0
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class AstroClientError(Exception):
    """Base exception for Astro API client errors."""


class AstroAuthenticationError(AstroClientError):
    """Raised when authentication fails."""


class AstroNotFoundError(AstroClientError):
    """Raised when a resource is not found."""


class AstroClient:
    """HTTP client for Astro Cloud Observability API.

    Provides methods for searching, listing, and retrieving catalog assets
    from the Astro Cloud Observability platform.
    """

    def __init__(
        self,
        organization_id: str,
        token_manager: AstroTokenManager,
        api_url: str = DEFAULT_API_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """Initialize the Astro API client.

        Args:
            organization_id: The Astro organization ID (cuid format)
            token_manager: Token manager for authentication
            api_url: Base URL for Astro Cloud API
            timeout: Request timeout in seconds
        """
        self.organization_id = organization_id
        self.token_manager = token_manager
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication.

        Returns:
            Headers dict with Authorization and Content-Type

        Raises:
            AstroAuthenticationError: If no token is available
        """
        token = self.token_manager.get_token()
        if not token:
            raise AstroAuthenticationError(
                "No authentication token found. "
                "Please tell the user to run 'astro login' in their terminal to authenticate with Astro Cloud, "
                "then try this request again."
            )
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Astro-Client-Identifier": "cli",
        }

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response, raising appropriate exceptions.

        Args:
            response: The HTTP response

        Returns:
            Parsed JSON response

        Raises:
            AstroAuthenticationError: For 401 responses
            AstroNotFoundError: For 404 responses
            AstroClientError: For other error responses
        """
        if response.status_code == 401:
            raise AstroAuthenticationError(
                "Authentication failed - the token is expired or invalid. "
                "Please tell the user to run 'astro login' in their terminal to re-authenticate, "
                "then try this request again."
            )
        if response.status_code == 403:
            raise AstroAuthenticationError(
                "Access denied - the user may not have Observability permissions for this organization. "
                "Please ask the user to verify they have access to the Observability feature in Astro Cloud, "
                "or contact their Astro administrator."
            )
        if response.status_code == 404:
            raise AstroNotFoundError("Resource not found.")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_body = response.json()
                error_detail = f": {error_body.get('message', error_body)}"
            except Exception:
                pass
            raise AstroClientError(
                f"API request failed with status {response.status_code}{error_detail}"
            ) from e

        return response.json()

    @staticmethod
    def encode_asset_id(asset_id: str) -> str:
        """Encode an asset ID for use in API URLs.

        The API expects asset IDs to be base64url encoded (without padding).

        Args:
            asset_id: The raw asset ID

        Returns:
            Base64url encoded asset ID
        """
        return base64.urlsafe_b64encode(asset_id.encode()).decode().rstrip("=")

    @staticmethod
    def decode_asset_id(encoded_id: str) -> str:
        """Decode a base64url encoded asset ID.

        Args:
            encoded_id: Base64url encoded asset ID

        Returns:
            Decoded asset ID
        """
        # Add padding if needed
        padding = 4 - (len(encoded_id) % 4)
        if padding != 4:
            encoded_id += "=" * padding
        return base64.urlsafe_b64decode(encoded_id).decode()

    def search_assets(
        self,
        search: str | None = None,
        asset_ids: list[str] | None = None,
        asset_types: list[str] | None = None,
        namespaces: list[str] | None = None,
        dags: list[str] | None = None,
        dag_tags: list[str] | None = None,
        owners: list[str] | None = None,
        include_only_leaf_assets: bool = False,
        include_only_root_assets: bool = False,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        sorts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search and filter catalog assets.

        Args:
            search: Full-text search query
            asset_ids: Filter by specific asset IDs
            asset_types: Filter by asset types (databricksTable, snowflakeTable, etc.)
            namespaces: Filter by deployment namespaces
            dags: Filter by DAG IDs
            dag_tags: Filter by DAG tags
            owners: Filter by DAG owners
            include_only_leaf_assets: Only return leaf assets (no downstream deps)
            include_only_root_assets: Only return root assets (no upstream deps)
            limit: Maximum results to return (default: 20, max: 100)
            offset: Pagination offset
            sorts: Sort criteria (e.g., ["assetId:asc", "timestamp:desc"])

        Returns:
            API response with assets and pagination info
        """
        # Validate limit
        limit = min(max(1, limit), MAX_LIMIT)

        # Build query parameters
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if search:
            params["search"] = search

        if asset_ids:
            # Encode asset IDs as base64
            params["assetIdHashes"] = [self.encode_asset_id(aid) for aid in asset_ids]

        if asset_types:
            params["assetTypes"] = asset_types

        if namespaces:
            params["namespaces"] = namespaces

        if dags:
            params["dags"] = dags

        if dag_tags:
            params["dagTags"] = dag_tags

        if owners:
            params["owners"] = owners

        if include_only_leaf_assets:
            params["includeOnlyLeafAssets"] = "true"

        if include_only_root_assets:
            params["includeOnlyRootAssets"] = "true"

        if sorts:
            params["sorts"] = sorts

        url = f"{self.api_url}/private/v1alpha1/organizations/{self.organization_id}/observability/assets"

        logger.debug("Searching assets: %s", params)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._get_headers(), params=params)

        return self._handle_response(response)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        """Get detailed information about a specific asset.

        Args:
            asset_id: The asset ID to retrieve

        Returns:
            Asset details including metadata, deployment info, etc.
        """
        encoded_id = self.encode_asset_id(asset_id)
        url = f"{self.api_url}/private/v1alpha1/organizations/{self.organization_id}/observability/assets/{encoded_id}"

        logger.debug("Getting asset: %s", asset_id)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._get_headers())

        return self._handle_response(response)

    def list_asset_filters(
        self,
        filter_type: str,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get available filter values for asset search.

        Args:
            filter_type: Type of filter (namespace, dag_id, dag_tag, owner)
            search: Search within filter values
            limit: Maximum results (default: 100)
            offset: Pagination offset

        Returns:
            List of available filter values
        """
        # Validate filter type
        valid_filters = {"namespace", "dag_id", "dag_tag", "owner"}
        if filter_type not in valid_filters:
            raise ValueError(f"Invalid filter type: {filter_type}. Must be one of: {valid_filters}")

        params: dict[str, Any] = {
            "limit": min(max(1, limit), MAX_LIMIT),
            "offset": offset,
        }

        if search:
            params["search"] = search

        url = f"{self.api_url}/private/v1alpha1/organizations/{self.organization_id}/observability/asset-filters/{filter_type}"

        logger.debug("Listing asset filters: type=%s, params=%s", filter_type, params)

        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._get_headers(), params=params)

        return self._handle_response(response)
