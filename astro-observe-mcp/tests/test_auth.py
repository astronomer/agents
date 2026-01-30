"""Tests for authentication module."""

import os
from pathlib import Path
from unittest.mock import patch

from astro_observe_mcp.auth import (
    AstroTokenManager,
    get_current_context,
    get_org_id_from_config,
    get_token_from_config,
    load_astro_config,
)


class TestAstroTokenManager:
    """Tests for AstroTokenManager."""

    def test_direct_token_highest_priority(self):
        """Direct token should take precedence over other sources."""
        manager = AstroTokenManager(token="direct-token")

        with patch.dict(os.environ, {"ASTRO_API_TOKEN": "env-token"}):
            token = manager.get_token()

        assert token == "direct-token"
        assert manager.get_token_source() == "direct"

    def test_env_token_when_no_direct_token(self):
        """Environment variable should be used when no direct token."""
        manager = AstroTokenManager()

        with patch.dict(os.environ, {"ASTRO_API_TOKEN": "env-token"}, clear=False):
            # Clear any cached token
            manager.invalidate()
            token = manager.get_token()

        assert token == "env-token"
        assert manager.get_token_source() == "env:ASTRO_API_TOKEN"

    def test_token_caching(self):
        """Token should be cached after first retrieval."""
        manager = AstroTokenManager(token="cached-token")
        token1 = manager.get_token()
        token2 = manager.get_token()

        assert token1 == token2 == "cached-token"

    def test_invalidate_clears_cache(self):
        """Invalidate should clear cached token."""
        manager = AstroTokenManager(token="initial-token")
        manager.get_token()  # Cache the token

        manager.invalidate()

        assert manager._cached_token is None
        assert manager._token_source is None

    def test_has_token_returns_true_when_available(self):
        """has_token should return True when token is available."""
        manager = AstroTokenManager(token="some-token")
        assert manager.has_token() is True


class TestAstroConfigLoading:
    """Tests for Astro CLI config loading."""

    def test_load_astro_config_from_file(self, tmp_path: Path):
        """Should load config from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
context: test-context
contexts:
    test_context:
        token: Bearer test-token
        organization: test-org-id
        workspace: test-workspace
""")

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", config_file):
            config = load_astro_config()

        assert config is not None
        assert config["context"] == "test-context"
        assert "test_context" in config["contexts"]

    def test_get_current_context(self, tmp_path: Path):
        """Should get the current context configuration."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
context: my.domain.io
contexts:
    my_domain_io:
        token: Bearer my-token
        organization: my-org-id
        workspace: my-workspace
""")

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", config_file):
            context = get_current_context()

        assert context is not None
        assert context["organization"] == "my-org-id"
        assert context["token"] == "Bearer my-token"

    def test_get_org_id_from_config(self, tmp_path: Path):
        """Should extract org ID from current context."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
context: test.io
contexts:
    test_io:
        organization: extracted-org-id
""")

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", config_file):
            org_id = get_org_id_from_config()

        assert org_id == "extracted-org-id"

    def test_get_token_from_config_strips_bearer(self, tmp_path: Path):
        """Should strip 'Bearer ' prefix from token."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
context: test.io
contexts:
    test_io:
        token: Bearer actual-token-value
""")

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", config_file):
            token = get_token_from_config()

        assert token == "actual-token-value"

    def test_missing_config_file_returns_none(self, tmp_path: Path):
        """Should return None when config file doesn't exist."""
        nonexistent = tmp_path / "nonexistent.yaml"

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", nonexistent):
            config = load_astro_config()
            org_id = get_org_id_from_config()
            token = get_token_from_config()

        assert config is None
        assert org_id is None
        assert token is None

    def test_missing_context_returns_none(self, tmp_path: Path):
        """Should return None when context is not set."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
contexts:
    test_io:
        organization: test-org
""")

        with patch("astro_observe_mcp.auth.ASTRO_CONFIG_FILE", config_file):
            context = get_current_context()

        assert context is None
