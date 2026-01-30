"""Authentication utilities for Astro Cloud API.

Supports multiple token sources:
1. Direct token (highest priority)
2. ASTRO_API_TOKEN environment variable
3. ~/.astro/config.yaml (created by `astro login`)
"""

import logging
import os
from pathlib import Path

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

    def has_token(self) -> bool:
        """Check if a valid token is available.

        Returns:
            True if a token is available
        """
        return self.get_token() is not None
