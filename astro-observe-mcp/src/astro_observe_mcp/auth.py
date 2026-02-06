"""Authentication utilities for Astro Cloud API.

Supports multiple token sources:
1. Direct token (highest priority)
2. ASTRO_API_TOKEN environment variable
3. ~/.astro/config.yaml (created by `astro login`)
"""

import logging
import os
from pathlib import Path

import httpx
import yaml

logger = logging.getLogger(__name__)

# Default paths
ASTRO_CONFIG_FILE = Path.home() / ".astro" / "config.yaml"


def load_astro_config() -> dict | None:
    """Load the Astro CLI config from ~/.astro/config.yaml.

    Returns:
        Parsed config dict, or None if not found/invalid
    """
    if not ASTRO_CONFIG_FILE.exists():
        logger.debug("Astro config file not found: %s", ASTRO_CONFIG_FILE)
        return None

    try:
        with open(ASTRO_CONFIG_FILE) as f:
            config = yaml.safe_load(f)
            return config if isinstance(config, dict) else None
    except Exception as e:
        logger.warning("Failed to load Astro config: %s", e)
        return None


def get_current_context(config: dict | None = None) -> dict | None:
    """Get the current context configuration from Astro CLI config.

    Args:
        config: Pre-loaded config dict (loads from file if None)

    Returns:
        Context dict with token, organization, workspace, etc.
    """
    if config is None:
        config = load_astro_config()

    if not config:
        return None

    context_name = config.get("context")
    if not context_name:
        logger.debug("No current context set in Astro config")
        return None

    contexts = config.get("contexts", {})

    # Context names have dots replaced with underscores in the map
    context_key = context_name.replace(".", "_")

    context = contexts.get(context_key)
    if not context:
        logger.debug("Context '%s' not found in config", context_name)
        return None

    return context


def get_org_id_from_config() -> str | None:
    """Get the organization ID from the current Astro CLI context.

    Returns:
        Organization ID string, or None if not found
    """
    context = get_current_context()
    if context:
        org_id = context.get("organization")
        if org_id:
            logger.debug("Found org ID from Astro config: %s", org_id)
            return org_id
    return None


def get_api_url_from_config() -> str | None:
    """Get the API URL based on the current Astro CLI context.

    Derives the API URL from the context name:
    - "astronomer.io" -> "https://api.astronomer.io"
    - "astronomer-dev.io" -> "https://api.astronomer-dev.io"
    - "localhost" -> "http://localhost:8888"

    Returns:
        API URL string, or None if not determinable
    """
    config = load_astro_config()
    if not config:
        return None

    context_name = config.get("context")
    if not context_name:
        return None

    # Handle common context patterns
    if context_name == "localhost":
        return "http://localhost:8888"
    if "." in context_name:
        # Context name is the domain (e.g., "astronomer-dev.io")
        return f"https://api.{context_name}"

    return None


def get_token_from_config() -> str | None:
    """Get the bearer token from the current Astro CLI context.

    Returns:
        Bearer token string (without 'Bearer ' prefix), or None if not found
    """
    context = get_current_context()
    if context:
        token = context.get("token")
        if token:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]
            if token:
                logger.debug("Found token from Astro config")
                return token
    return None


def get_refresh_token_from_config() -> str | None:
    """Get the refresh token from the current Astro CLI context.

    Returns:
        Refresh token string, or None if not found
    """
    context = get_current_context()
    if context:
        return context.get("refreshtoken")
    return None


def refresh_access_token() -> str | None:
    """Use the refresh token to get a new access token from Auth0.

    Returns:
        New access token, or None if refresh failed
    """
    config = load_astro_config()
    if not config:
        return None

    context_name = config.get("context", "")
    context = get_current_context(config)
    if not context:
        return None

    refresh_token = context.get("refreshtoken")
    if not refresh_token:
        logger.warning("No refresh token found in config")
        return None

    # Determine Auth0 domain and client ID based on context
    if "dev" in context_name:
        auth_domain = "https://auth.astronomer-dev.io"
        client_id = "PH3Nac2DtpSx1Tx3IGQmh2zaRbF5ubZG"
    else:
        auth_domain = "https://auth.astronomer.io"
        client_id = "5XYJZYf5xZ0eKALgBH3O08WzgfUfz7y9"

    try:
        logger.info("Refreshing access token via Auth0...")
        response = httpx.post(
            f"{auth_domain}/oauth/token",
            json={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            new_token = data.get("access_token")
            if new_token:
                logger.info("Successfully refreshed access token")
                # Update the config file with new token
                _update_config_token(config, context_name, new_token)
                return new_token
        else:
            logger.warning("Token refresh failed: %s %s", response.status_code, response.text[:200])
    except Exception as e:
        logger.warning("Token refresh error: %s", e)

    return None


def _update_config_token(config: dict, context_name: str, new_token: str) -> None:
    """Update the token in the Astro config file.

    Args:
        config: The loaded config dict
        context_name: The context name (e.g., "astronomer.io")
        new_token: The new access token
    """
    try:
        context_key = context_name.replace(".", "_")
        if "contexts" in config and context_key in config["contexts"]:
            config["contexts"][context_key]["token"] = f"Bearer {new_token}"

            with open(ASTRO_CONFIG_FILE, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False)
            logger.info("Updated token in config file")
    except Exception as e:
        logger.warning("Failed to update config file: %s", e)


class AstroTokenManager:
    """Manages authentication tokens for Astro Cloud API.

    Token discovery order:
    1. Direct token (if provided)
    2. ASTRO_API_TOKEN environment variable
    3. ~/.astro/config.yaml (created by `astro login`)
    """

    def __init__(
        self,
        token: str | None = None,
    ):
        """Initialize the token manager.

        Args:
            token: Direct token to use (highest priority)
        """
        self._direct_token = token
        self._cached_token: str | None = None
        self._token_source: str | None = None

    def get_token(self) -> str | None:
        """Get the authentication token.

        Returns:
            The token string, or None if no token is available.
        """
        # Return cached token if available
        if self._cached_token:
            return self._cached_token

        # 1. Direct token (highest priority)
        if self._direct_token:
            self._cached_token = self._direct_token
            self._token_source = "direct"
            logger.debug("Using direct token")
            return self._cached_token

        # 2. Environment variable
        env_token = os.environ.get("ASTRO_API_TOKEN")
        if env_token:
            self._cached_token = env_token
            self._token_source = "env:ASTRO_API_TOKEN"
            logger.debug("Using token from ASTRO_API_TOKEN environment variable")
            return self._cached_token

        # 3. Astro CLI config (~/.astro/config.yaml)
        config_token = get_token_from_config()
        if config_token:
            self._cached_token = config_token
            self._token_source = f"file:{ASTRO_CONFIG_FILE}"
            return self._cached_token

        logger.warning(
            "No authentication token found. "
            "Set ASTRO_API_TOKEN environment variable, run 'astro login', "
            "or provide --token argument."
        )
        return None

    def get_token_source(self) -> str | None:
        """Get the source of the current token.

        Returns:
            Description of token source (e.g., "env:ASTRO_API_TOKEN", "file:~/.astro/token")
        """
        if not self._token_source:
            # Trigger token discovery
            self.get_token()
        return self._token_source

    def invalidate(self) -> None:
        """Clear cached token to force re-discovery on next request."""
        self._cached_token = None
        self._token_source = None

    def refresh(self) -> bool:
        """Attempt to refresh the token using the stored refresh token.

        Uses the refresh token from ~/.astro/config.yaml to get a new
        access token from Auth0, then updates the config file.

        Returns:
            True if refresh succeeded, False otherwise
        """
        logger.info("Token expired, attempting refresh via Auth0...")
        self.invalidate()

        # Try to refresh using the refresh token
        new_token = refresh_access_token()
        if new_token:
            self._cached_token = new_token
            self._token_source = f"refreshed:{ASTRO_CONFIG_FILE}"
            logger.info("Token refresh succeeded")
            return True
        logger.warning("Token refresh failed")
        return False

    def has_token(self) -> bool:
        """Check if a valid token is available.

        Returns:
            True if a token is available
        """
        return self.get_token() is not None
