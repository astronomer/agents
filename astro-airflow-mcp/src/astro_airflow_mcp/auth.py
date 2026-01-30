"""Authentication utilities for Airflow API access."""

from __future__ import annotations

import time

import httpx

from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Buffer time before token expiry to trigger refresh (5 minutes)
TOKEN_REFRESH_BUFFER_SECONDS = 300


class TokenManager:
    """Manages JWT token lifecycle for Airflow API authentication.

    Handles fetching tokens from /auth/token endpoint (Airflow 3.x),
    automatic refresh when tokens expire, and supports both credential-based
    and credential-less (all_admins mode) authentication.

    For Airflow 2.x (which doesn't have /auth/token), this manager will detect
    the 404 and stop attempting token fetches, falling back to basic auth.
    """

    def __init__(
        self,
        airflow_url: str,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialize the token manager.

        Args:
            airflow_url: Base URL of the Airflow webserver
            username: Optional username for token authentication
            password: Optional password for token authentication
            timeout: HTTP request timeout in seconds (default 30.0)
        """
        self.airflow_url = airflow_url
        self.username = username
        self.password = password
        self._timeout = timeout
        self._token: str | None = None
        self._token_fetched_at: float | None = None
        # Default token lifetime of 30 minutes if not provided by server
        self._token_lifetime_seconds: float = 1800
        # Track if token endpoint is available (False for Airflow 2.x)
        self._token_endpoint_available: bool | None = None

    def get_token(self) -> str | None:
        """Get current token, fetching/refreshing if needed.

        Returns:
            JWT token string, or None if token fetch fails or endpoint unavailable
        """
        # If we've determined the endpoint doesn't exist, don't try again
        if self._token_endpoint_available is False:
            return None
        if self._should_refresh():
            self._fetch_token()
        return self._token

    def get_basic_auth(self) -> tuple[str, str] | None:
        """Get basic auth credentials for Airflow 2.x fallback.

        Returns:
            Tuple of (username, password) if available, None otherwise
        """
        if self.username and self.password:
            return (self.username, self.password)
        return None

    def is_token_endpoint_available(self) -> bool | None:
        """Check if the token endpoint is available.

        Returns:
            True if available (Airflow 3.x), False if not (Airflow 2.x),
            None if not yet determined.
        """
        return self._token_endpoint_available

    def invalidate(self) -> None:
        """Force token refresh on next request."""
        self._token = None
        self._token_fetched_at = None

    def _should_refresh(self) -> bool:
        """Check if token needs refresh (expired or not yet fetched).

        Returns:
            True if token should be refreshed
        """
        if self._token is None:
            return True
        if self._token_fetched_at is None:
            return True
        # Refresh if we're within the buffer time of expiry
        elapsed = time.time() - self._token_fetched_at
        return elapsed >= (self._token_lifetime_seconds - TOKEN_REFRESH_BUFFER_SECONDS)

    def _fetch_token(self) -> None:
        """Fetch new token from /auth/token endpoint.

        Tries credential-less GET first if no username/password provided,
        otherwise uses POST with credentials.

        For Airflow 2.x (404 response), marks the endpoint as unavailable
        and stops future attempts.
        """
        token_url = f"{self.airflow_url}/auth/token"

        try:
            with httpx.Client(timeout=self._timeout) as client:
                if self.username and self.password:
                    # Use credentials to fetch token
                    logger.debug("Fetching token with username/password credentials")
                    response = client.post(
                        token_url,
                        json={"username": self.username, "password": self.password},
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    # Try credential-less fetch (for all_admins mode)
                    logger.debug("Attempting credential-less token fetch")
                    response = client.get(token_url)

            # Check for 404 - indicates Airflow 2.x without token endpoint
            if response.status_code == 404:
                self._token_endpoint_available = False
                self._token = None
                # Default to admin:admin for Airflow 2.x if no credentials provided
                if not self.username and not self.password:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Defaulting to admin:admin for basic auth."
                    )
                    self.username = "admin"  # nosec B105 - default for local dev
                    self.password = "admin"  # nosec B105 - default for local dev
                else:
                    logger.info(
                        "Token endpoint not available (Airflow 2.x). "
                        "Using provided credentials for basic auth."
                    )
                return

            response.raise_for_status()
            data = response.json()

            # Extract token from response
            # Airflow returns {"access_token": "...", "token_type": "bearer"}
            if "access_token" in data:
                self._token = data["access_token"]
                self._token_fetched_at = time.time()
                self._token_endpoint_available = True
                # Use expires_in if provided, otherwise keep default
                if "expires_in" in data:
                    self._token_lifetime_seconds = float(data["expires_in"])
                logger.info("Successfully fetched Airflow API token")
            else:
                logger.warning("Unexpected token response format: %s", data)
                self._token = None

        except httpx.RequestError as e:
            logger.warning("Failed to fetch token from %s: %s", token_url, e)
            self._token = None
