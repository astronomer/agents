"""Tests for af registry CLI commands."""

import json
import time

import httpx
from typer.testing import CliRunner

from astro_airflow_mcp.cli.main import app
from astro_airflow_mcp.cli.registry import (
    CACHE_TTL_LATEST,
    CACHE_TTL_VERSIONED,
    _read_cache,
    _write_cache,
)

runner = CliRunner()

# --- Fixture data ---

PROVIDERS_RESPONSE = {
    "providers": [
        {
            "id": "amazon",
            "name": "Amazon",
            "version": "9.22.0",
            "lifecycle": "stable",
            "description": "Amazon Web Services (AWS) integration",
        },
        {
            "id": "google",
            "name": "Google",
            "version": "12.0.0",
            "lifecycle": "stable",
            "description": "Google Cloud integration",
        },
    ]
}

MODULES_RESPONSE = {
    "provider_id": "amazon",
    "provider_name": "Amazon",
    "version": "9.22.0",
    "modules": [
        {"name": "S3Hook", "type": "hook", "import_path": "airflow.providers.amazon.aws.hooks.s3"},
        {
            "name": "S3ToRedshiftOperator",
            "type": "operator",
            "import_path": "airflow.providers.amazon.aws.transfers.s3_to_redshift",
        },
    ],
}

PARAMETERS_RESPONSE = {
    "provider_id": "ftp",
    "classes": {
        "airflow.providers.ftp.hooks.ftp.FTPHook": {
            "name": "FTPHook",
            "type": "hook",
            "mro": ["FTPHook", "BaseHook"],
            "parameters": [
                {"name": "ftp_conn_id", "type": "str", "default": "ftp_default"},
            ],
        }
    },
}

CONNECTIONS_RESPONSE = {
    "provider_id": "amazon",
    "connection_types": [
        {
            "connection_type": "aws",
            "hook_class": "airflow.providers.amazon.aws.hooks.base_aws.AwsBaseHook",
            "standard_fields": ["login", "password"],
            "custom_fields": [{"name": "region_name", "type": "str"}],
        }
    ],
}


def _mock_httpx_get(mocker, response_data, status_code=200):
    """Helper to mock httpx.get with a given response."""
    mock_response = mocker.Mock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.json.return_value = response_data
    return mocker.patch("astro_airflow_mcp.cli.registry.httpx.get", return_value=mock_response)


class TestProvidersCommand:
    """Tests for af registry providers."""

    def test_list_providers(self, mocker):
        """Test listing all providers returns formatted JSON."""
        _mock_httpx_get(mocker, PROVIDERS_RESPONSE)

        result = runner.invoke(app, ["registry", "providers", "--no-cache"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["total_providers"] == 2
        assert len(output["providers"]) == 2
        assert output["providers"][0]["id"] == "amazon"
        assert output["providers"][1]["id"] == "google"

    def test_list_providers_custom_url(self, mocker):
        """Test --registry-url overrides the base URL."""
        mock_get = _mock_httpx_get(mocker, PROVIDERS_RESPONSE)

        result = runner.invoke(
            app,
            [
                "registry",
                "providers",
                "--registry-url",
                "https://custom.example.com/registry",
                "--no-cache",
            ],
        )

        assert result.exit_code == 0
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://custom.example.com/registry/api/providers.json")

    def test_list_providers_env_url(self, mocker):
        """Test AF_REGISTRY_URL env var overrides the base URL."""
        mock_get = _mock_httpx_get(mocker, PROVIDERS_RESPONSE)

        result = runner.invoke(
            app,
            ["registry", "providers", "--no-cache"],
            env={"AF_REGISTRY_URL": "https://env.example.com/registry"},
        )

        assert result.exit_code == 0
        called_url = mock_get.call_args[0][0]
        assert called_url.startswith("https://env.example.com/registry/api/providers.json")


class TestModulesCommand:
    """Tests for af registry modules."""

    def test_list_modules(self, mocker):
        """Test listing modules for a provider."""
        _mock_httpx_get(mocker, MODULES_RESPONSE)

        result = runner.invoke(app, ["registry", "modules", "amazon", "--no-cache"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["provider_id"] == "amazon"
        assert output["total_modules"] == 2
        assert len(output["modules"]) == 2

    def test_list_modules_with_version(self, mocker):
        """Test --version flag builds correct URL."""
        mock_get = _mock_httpx_get(mocker, MODULES_RESPONSE)

        result = runner.invoke(
            app, ["registry", "modules", "amazon", "--version", "9.22.0", "--no-cache"]
        )

        assert result.exit_code == 0
        called_url = mock_get.call_args[0][0]
        assert "/providers/amazon/9.22.0/modules.json" in called_url

    def test_list_modules_without_version(self, mocker):
        """Test URL without version uses latest."""
        mock_get = _mock_httpx_get(mocker, MODULES_RESPONSE)

        result = runner.invoke(app, ["registry", "modules", "amazon", "--no-cache"])

        assert result.exit_code == 0
        called_url = mock_get.call_args[0][0]
        assert "/providers/amazon/modules.json" in called_url


class TestParametersCommand:
    """Tests for af registry parameters."""

    def test_list_parameters(self, mocker):
        """Test listing parameters for a provider."""
        _mock_httpx_get(mocker, PARAMETERS_RESPONSE)

        result = runner.invoke(app, ["registry", "parameters", "ftp", "--no-cache"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["provider_id"] == "ftp"
        assert output["total_classes"] == 1
        assert "airflow.providers.ftp.hooks.ftp.FTPHook" in output["classes"]

    def test_list_parameters_with_version(self, mocker):
        """Test --version flag on parameters command."""
        mock_get = _mock_httpx_get(mocker, PARAMETERS_RESPONSE)

        result = runner.invoke(
            app, ["registry", "parameters", "ftp", "--version", "3.12.0", "--no-cache"]
        )

        assert result.exit_code == 0
        called_url = mock_get.call_args[0][0]
        assert "/providers/ftp/3.12.0/parameters.json" in called_url


class TestConnectionsCommand:
    """Tests for af registry connections."""

    def test_list_connections(self, mocker):
        """Test listing connection types for a provider."""
        _mock_httpx_get(mocker, CONNECTIONS_RESPONSE)

        result = runner.invoke(app, ["registry", "connections", "amazon", "--no-cache"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["provider_id"] == "amazon"
        assert output["total_connection_types"] == 1
        assert output["connection_types"][0]["connection_type"] == "aws"

    def test_list_connections_with_version(self, mocker):
        """Test --version flag on connections command."""
        mock_get = _mock_httpx_get(mocker, CONNECTIONS_RESPONSE)

        result = runner.invoke(
            app, ["registry", "connections", "amazon", "--version", "9.22.0", "--no-cache"]
        )

        assert result.exit_code == 0
        called_url = mock_get.call_args[0][0]
        assert "/providers/amazon/9.22.0/connections.json" in called_url


class TestErrorHandling:
    """Tests for error cases."""

    def test_404_shows_not_found(self, mocker):
        """Test 404 response produces a not-found error."""
        _mock_httpx_get(mocker, {}, status_code=404)

        result = runner.invoke(app, ["registry", "modules", "nonexistent", "--no-cache"])

        assert result.exit_code == 1
        error = json.loads(result.output)
        assert "Not found" in error["error"]

    def test_connection_error(self, mocker):
        """Test connection failure produces an error."""
        mocker.patch(
            "astro_airflow_mcp.cli.registry.httpx.get",
            side_effect=httpx.ConnectError("Connection refused"),
        )

        result = runner.invoke(app, ["registry", "providers", "--no-cache"])

        assert result.exit_code == 1
        error = json.loads(result.output)
        assert "Failed to connect" in error["error"]

    def test_invalid_json(self, mocker):
        """Test invalid JSON response produces an error."""
        mock_response = mocker.Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("No JSON")
        mocker.patch("astro_airflow_mcp.cli.registry.httpx.get", return_value=mock_response)

        result = runner.invoke(app, ["registry", "providers", "--no-cache"])

        assert result.exit_code == 1
        error = json.loads(result.output)
        assert "invalid JSON" in error["error"]

    def test_server_error(self, mocker):
        """Test 500 response produces an error."""
        _mock_httpx_get(mocker, {}, status_code=500)

        result = runner.invoke(app, ["registry", "providers", "--no-cache"])

        assert result.exit_code == 1
        error = json.loads(result.output)
        assert "500" in error["error"]


class TestCaching:
    """Tests for file-based caching."""

    def test_cache_write_and_read(self, tmp_path, mocker):
        """Test cache write then read returns same data."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)

        url = "https://example.com/api/providers.json"
        _write_cache(url, PROVIDERS_RESPONSE)
        result = _read_cache(url, CACHE_TTL_LATEST)

        assert result == PROVIDERS_RESPONSE

    def test_cache_expired_latest(self, tmp_path, mocker):
        """Test unversioned cache expires after CACHE_TTL_LATEST."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)

        url = "https://example.com/api/providers.json"
        _write_cache(url, PROVIDERS_RESPONSE)

        # Backdate the cached_at timestamp past the latest TTL
        import hashlib

        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cache_file = tmp_path / f"{cache_key}.json"
        data = json.loads(cache_file.read_text())
        data["_cached_at"] = time.time() - CACHE_TTL_LATEST - 1
        cache_file.write_text(json.dumps(data))

        result = _read_cache(url, CACHE_TTL_LATEST)
        assert result is None

    def test_versioned_cache_survives_latest_ttl(self, tmp_path, mocker):
        """Test versioned cache still valid after the latest TTL expires."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)

        url = "https://example.com/api/providers/ftp/3.14.1/modules.json"
        _write_cache(url, MODULES_RESPONSE)

        # Backdate past the latest TTL but within versioned TTL
        import hashlib

        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cache_file = tmp_path / f"{cache_key}.json"
        data = json.loads(cache_file.read_text())
        data["_cached_at"] = time.time() - CACHE_TTL_LATEST - 100
        cache_file.write_text(json.dumps(data))

        # With versioned TTL: still valid
        result = _read_cache(url, CACHE_TTL_VERSIONED)
        assert result == MODULES_RESPONSE

        # With latest TTL: expired
        result = _read_cache(url, CACHE_TTL_LATEST)
        assert result is None

    def test_cache_miss(self, tmp_path, mocker):
        """Test reading a non-existent cache entry returns None."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)

        result = _read_cache("https://example.com/api/nonexistent.json", CACHE_TTL_LATEST)
        assert result is None

    def test_no_cache_flag_bypasses_cache(self, tmp_path, mocker):
        """Test --no-cache flag fetches fresh data."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)
        mock_get = _mock_httpx_get(mocker, PROVIDERS_RESPONSE)

        # First call populates cache
        runner.invoke(app, ["registry", "providers"])
        # Second call with --no-cache should still hit the network
        runner.invoke(app, ["registry", "providers", "--no-cache"])

        assert mock_get.call_count == 2

    def test_cache_hit_skips_network(self, tmp_path, mocker):
        """Test cached data is served without a network call."""
        mocker.patch("astro_airflow_mcp.cli.registry._cache_dir", return_value=tmp_path)
        mock_get = _mock_httpx_get(mocker, PROVIDERS_RESPONSE)

        # First call: network + cache write
        result1 = runner.invoke(app, ["registry", "providers"])
        assert result1.exit_code == 0
        assert mock_get.call_count == 1

        # Second call: should hit cache, not network
        result2 = runner.invoke(app, ["registry", "providers"])
        assert result2.exit_code == 0
        assert mock_get.call_count == 1  # Still 1 — no new network call
