"""Tests for the discovery module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from astro_airflow_mcp.discovery import (
    DiscoveredInstance,
    DiscoveryError,
    DiscoveryRegistry,
    get_default_registry,
)
from astro_airflow_mcp.discovery.astro import (
    AstroDiscoveryBackend,
    AstroDiscoveryError,
    AstroNotAuthenticatedError,
    _generate_instance_name,
)
from astro_airflow_mcp.discovery.astro_cli import AstroCliError, AstroDeployment
from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend


class TestDiscoveredInstance:
    """Tests for DiscoveredInstance dataclass."""

    def test_basic_creation(self):
        """Test creating a basic instance."""
        instance = DiscoveredInstance(
            name="test-instance",
            url="http://localhost:8080",
            source="local",
        )
        assert instance.name == "test-instance"
        assert instance.url == "http://localhost:8080"
        assert instance.source == "local"
        assert instance.auth_token is None
        assert instance.metadata == {}

    def test_with_token_and_metadata(self):
        """Test creating instance with token and metadata."""
        instance = DiscoveredInstance(
            name="astro-prod",
            url="https://example.astronomer.run",
            source="astro",
            auth_token="test-token",
            metadata={"deployment_id": "dep-123", "status": "HEALTHY"},
        )
        assert instance.auth_token == "test-token"
        assert instance.metadata["deployment_id"] == "dep-123"
        assert instance.metadata["status"] == "HEALTHY"


class TestDiscoveryRegistry:
    """Tests for DiscoveryRegistry."""

    def test_register_and_get_backend(self):
        """Test registering and retrieving a backend."""
        registry = DiscoveryRegistry()
        mock_backend = MagicMock()
        mock_backend.name = "test"
        mock_backend.is_available.return_value = True

        registry.register(mock_backend)

        assert registry.get_backend("test") is mock_backend
        assert registry.get_backend("nonexistent") is None

    def test_unregister(self):
        """Test unregistering a backend."""
        registry = DiscoveryRegistry()
        mock_backend = MagicMock()
        mock_backend.name = "test"

        registry.register(mock_backend)
        assert registry.get_backend("test") is not None

        registry.unregister("test")
        assert registry.get_backend("test") is None

    def test_get_all_backends(self):
        """Test getting all registered backends."""
        registry = DiscoveryRegistry()
        backend1 = MagicMock()
        backend1.name = "backend1"
        backend2 = MagicMock()
        backend2.name = "backend2"

        registry.register(backend1)
        registry.register(backend2)

        all_backends = registry.get_all_backends()
        assert len(all_backends) == 2

    def test_get_available_backends(self):
        """Test getting only available backends."""
        registry = DiscoveryRegistry()

        available = MagicMock()
        available.name = "available"
        available.is_available.return_value = True

        unavailable = MagicMock()
        unavailable.name = "unavailable"
        unavailable.is_available.return_value = False

        registry.register(available)
        registry.register(unavailable)

        available_backends = registry.get_available_backends()
        assert len(available_backends) == 1
        assert available_backends[0].name == "available"

    def test_discover_all_uses_available_backends(self):
        """Test discover_all runs on all available backends."""
        registry = DiscoveryRegistry()

        backend1 = MagicMock()
        backend1.name = "backend1"
        backend1.is_available.return_value = True
        backend1.discover.return_value = [
            DiscoveredInstance(name="inst1", url="http://a", source="backend1")
        ]

        backend2 = MagicMock()
        backend2.name = "backend2"
        backend2.is_available.return_value = True
        backend2.discover.return_value = [
            DiscoveredInstance(name="inst2", url="http://b", source="backend2")
        ]

        registry.register(backend1)
        registry.register(backend2)

        results = registry.discover_all()

        assert "backend1" in results
        assert "backend2" in results
        assert len(results["backend1"]) == 1
        assert len(results["backend2"]) == 1

    def test_discover_all_with_specific_backends(self):
        """Test discover_all with specific backend selection."""
        registry = DiscoveryRegistry()

        backend1 = MagicMock()
        backend1.name = "backend1"
        backend1.is_available.return_value = True
        backend1.discover.return_value = []

        backend2 = MagicMock()
        backend2.name = "backend2"
        backend2.is_available.return_value = True
        backend2.discover.return_value = []

        registry.register(backend1)
        registry.register(backend2)

        results = registry.discover_all(backends=["backend1"])

        assert "backend1" in results
        assert "backend2" not in results
        backend1.discover.assert_called_once()
        backend2.discover.assert_not_called()

    def test_discover_all_raises_for_unknown_backend(self):
        """Test discover_all raises for unknown backend."""
        registry = DiscoveryRegistry()

        with pytest.raises(DiscoveryError, match="not found"):
            registry.discover_all(backends=["nonexistent"])

    def test_discover_all_raises_for_unavailable_backend(self):
        """Test discover_all raises when specified backend is unavailable."""
        registry = DiscoveryRegistry()

        backend = MagicMock()
        backend.name = "unavailable"
        backend.is_available.return_value = False

        registry.register(backend)

        with pytest.raises(DiscoveryError, match="not available"):
            registry.discover_all(backends=["unavailable"])


class TestDefaultRegistry:
    """Tests for get_default_registry."""

    def test_creates_registry_with_backends(self):
        """Test default registry has expected backends."""
        registry = get_default_registry()

        assert registry.get_backend("astro") is not None
        assert registry.get_backend("local") is not None


class TestAstroDiscoveryBackend:
    """Tests for AstroDiscoveryBackend."""

    @pytest.fixture
    def mock_cli(self):
        """Create a mock AstroCli."""
        return MagicMock()

    def test_name(self, mock_cli):
        """Test backend name."""
        backend = AstroDiscoveryBackend(cli=mock_cli)
        assert backend.name == "astro"

    def test_is_available_when_cli_installed(self, mock_cli):
        """Test is_available returns True when CLI is installed."""
        mock_cli.is_installed.return_value = True
        backend = AstroDiscoveryBackend(cli=mock_cli)
        assert backend.is_available() is True

    def test_is_available_when_cli_not_installed(self, mock_cli):
        """Test is_available returns False when CLI not installed."""
        mock_cli.is_installed.return_value = False
        backend = AstroDiscoveryBackend(cli=mock_cli)
        assert backend.is_available() is False

    def test_discover_returns_instances(self, mock_cli):
        """Test discover returns list of instances."""
        mock_cli.list_deployments.return_value = [{"name": "dep1", "deployment_id": "id1"}]
        mock_cli.inspect_deployment.return_value = AstroDeployment(
            id="id1",
            name="dep1",
            workspace_id="ws1",
            workspace_name="workspace1",
            airflow_api_url="https://example.com",
            status="HEALTHY",
        )
        mock_cli.token_exists.return_value = False
        mock_cli.create_deployment_token.return_value = "test-token"

        backend = AstroDiscoveryBackend(cli=mock_cli)
        instances = backend.discover(create_tokens=True)

        assert len(instances) == 1
        assert instances[0].name == "workspace1-dep1"
        assert instances[0].url == "https://example.com"
        assert instances[0].source == "astro"
        assert instances[0].auth_token == "test-token"

    def test_discover_without_tokens(self, mock_cli):
        """Test discover without creating tokens."""
        mock_cli.list_deployments.return_value = [{"name": "dep1", "deployment_id": "id1"}]
        mock_cli.inspect_deployment.return_value = AstroDeployment(
            id="id1",
            name="dep1",
            workspace_id="ws1",
            workspace_name="workspace1",
            airflow_api_url="https://example.com",
            status="HEALTHY",
        )

        backend = AstroDiscoveryBackend(cli=mock_cli)
        instances = backend.discover(create_tokens=False)

        assert len(instances) == 1
        assert instances[0].auth_token is None
        mock_cli.token_exists.assert_not_called()
        mock_cli.create_deployment_token.assert_not_called()

    def test_discover_handles_auth_error(self, mock_cli):
        """Test discover raises on auth error."""
        from astro_airflow_mcp.discovery.astro_cli import AstroCliNotAuthenticatedError

        mock_cli.list_deployments.side_effect = AstroCliNotAuthenticatedError("Not authenticated")

        backend = AstroDiscoveryBackend(cli=mock_cli)

        with pytest.raises(AstroNotAuthenticatedError):
            backend.discover()

    def test_discover_handles_cli_error(self, mock_cli):
        """Test discover raises on CLI error."""
        mock_cli.list_deployments.side_effect = AstroCliError("Failed")

        backend = AstroDiscoveryBackend(cli=mock_cli)

        with pytest.raises(AstroDiscoveryError, match="Failed to list"):
            backend.discover()

    def test_discover_skips_deployments_without_id(self, mock_cli):
        """Test discover skips deployments without ID."""
        mock_cli.list_deployments.return_value = [
            {"name": "dep1"},  # No deployment_id
        ]

        backend = AstroDiscoveryBackend(cli=mock_cli)
        instances = backend.discover()

        assert len(instances) == 0
        mock_cli.inspect_deployment.assert_not_called()


class TestGenerateInstanceName:
    """Tests for _generate_instance_name helper."""

    def test_basic_name_generation(self):
        """Test basic name generation."""
        dep = AstroDeployment(
            id="dep-1",
            name="my-deployment",
            workspace_id="ws-1",
            workspace_name="My Workspace",
            airflow_api_url="https://example.com",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "my-workspace-my-deployment"

    def test_name_generation_normalizes_special_chars(self):
        """Test that special characters are normalized."""
        dep = AstroDeployment(
            id="dep-1",
            name="My_Deployment (Test)",
            workspace_id="ws-1",
            workspace_name="Dev & Staging",
            airflow_api_url="https://example.com",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "dev-staging-my-deployment-test"

    def test_name_generation_empty_workspace(self):
        """Test name generation when workspace name is empty."""
        dep = AstroDeployment(
            id="dep-1",
            name="standalone",
            workspace_id="ws-1",
            workspace_name="",
            airflow_api_url="https://example.com",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "standalone"


class TestLocalDiscoveryBackend:
    """Tests for LocalDiscoveryBackend."""

    def test_name(self):
        """Test backend name."""
        backend = LocalDiscoveryBackend()
        assert backend.name == "local"

    def test_is_available_always_true(self):
        """Test is_available always returns True."""
        backend = LocalDiscoveryBackend()
        assert backend.is_available() is True

    def test_default_ports(self):
        """Test default ports are set."""
        assert LocalDiscoveryBackend.DEFAULT_PORTS == [
            8080,
            8081,
            8082,
            8083,
            8084,
            8085,
            8086,
            8087,
            8088,
            8089,
            8090,
        ]

    def test_discover_with_no_open_ports(self):
        """Test discover returns empty when no ports open."""
        backend = LocalDiscoveryBackend()

        with patch.object(backend, "_is_port_open", return_value=False):
            instances = backend.discover(ports=[8080])

        assert instances == []

    def test_discover_finds_airflow_instance(self):
        """Test discover finds an Airflow instance."""
        backend = LocalDiscoveryBackend()

        with (
            patch.object(backend, "_is_port_open", return_value=True),
            patch.object(
                backend,
                "_detect_airflow",
                return_value={"detected_from": "/api/v1/health", "api_version": "v1"},
            ),
        ):
            instances = backend.discover(ports=[8080], hosts=["localhost"])

        assert len(instances) == 1
        assert instances[0].name == "localhost:8080"
        assert instances[0].url == "http://localhost:8080"
        assert instances[0].source == "local"
        assert instances[0].auth_token is None

    def test_discover_deduplicates_localhost_and_127(self):
        """Test discover doesn't return duplicates for localhost and 127.0.0.1."""
        backend = LocalDiscoveryBackend()

        with (
            patch.object(backend, "_is_port_open", return_value=True),
            patch.object(
                backend,
                "_detect_airflow",
                return_value={"detected_from": "/api/v1/health"},
            ),
        ):
            instances = backend.discover(ports=[8080], hosts=["localhost", "127.0.0.1"])

        # Should only return one instance (deduplicated)
        assert len(instances) == 1

    def test_is_port_open_returns_true_for_open_port(self):
        """Test _is_port_open returns True for open port."""
        backend = LocalDiscoveryBackend()

        with patch("socket.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 0
            mock_socket.return_value.__enter__.return_value = mock_sock

            result = backend._is_port_open("localhost", 8080, 1.0)

        assert result is True

    def test_is_port_open_returns_false_for_closed_port(self):
        """Test _is_port_open returns False for closed port."""
        backend = LocalDiscoveryBackend()

        with patch("socket.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_sock.connect_ex.return_value = 1
            mock_socket.return_value.__enter__.return_value = mock_sock

            result = backend._is_port_open("localhost", 8080, 1.0)

        assert result is False

    def test_detect_airflow_v1_health(self):
        """Test _detect_airflow detects v1 API when v2 is not available."""
        backend = LocalDiscoveryBackend()

        # v2 fails, v1 succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 404

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
        }

        def get_side_effect(url):
            if "/api/v2/" in url:
                return mock_response_fail
            return mock_response_success

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = get_side_effect
            result = backend._detect_airflow("http://localhost:8080", 1.0)

        assert result is not None
        assert result["api_version"] == "v1"

    def test_detect_airflow_v2_health(self):
        """Test _detect_airflow detects v2 API (checked first)."""
        backend = LocalDiscoveryBackend()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
        }

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = backend._detect_airflow("http://localhost:8080", 1.0)

        assert result is not None
        assert result["api_version"] == "v2"

    def test_detect_airflow_returns_none_for_non_airflow(self):
        """Test _detect_airflow returns None for non-Airflow services."""
        backend = LocalDiscoveryBackend()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}  # Not Airflow
        mock_response.text = "Some other service"

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response
            result = backend._detect_airflow("http://localhost:8080", 1.0)

        assert result is None

    def test_detect_airflow_handles_connection_errors(self):
        """Test _detect_airflow handles connection errors gracefully."""
        backend = LocalDiscoveryBackend()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = httpx.RequestError(
                "Connection refused"
            )
            result = backend._detect_airflow("http://localhost:8080", 1.0)

        assert result is None

    def test_parse_health_response_extracts_info(self):
        """Test _parse_health_response extracts Airflow info."""
        backend = LocalDiscoveryBackend()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "metadatabase": {"status": "healthy"},
            "scheduler": {"status": "healthy"},
        }

        result = backend._parse_health_response(mock_response, "/api/v1/health")

        assert result is not None
        assert result["api_version"] == "v1"
        assert "health" in result

    def test_parse_health_response_returns_none_for_non_airflow_json(self):
        """Test _parse_health_response returns None for non-Airflow JSON."""
        backend = LocalDiscoveryBackend()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}  # Not Airflow-specific

        result = backend._parse_health_response(mock_response, "/health")

        assert result is None

    def test_parse_health_response_none_for_non_json(self):
        """Test _parse_health_response returns None for non-JSON responses."""
        backend = LocalDiscoveryBackend()

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Not JSON")

        result = backend._parse_health_response(mock_response, "/health")

        assert result is None

    def test_get_astro_project_port_webserver(self, tmp_path):
        """Test _get_astro_project_port reads webserver.port (Airflow 2)."""
        astro_dir = tmp_path / ".astro"
        astro_dir.mkdir()
        config_file = astro_dir / "config.yaml"
        config_file.write_text("webserver:\n  port: 8081\n")

        backend = LocalDiscoveryBackend()
        port = backend._get_astro_project_port(tmp_path)

        assert port == 8081

    def test_get_astro_project_port_api_server(self, tmp_path):
        """Test _get_astro_project_port reads api-server.port (Airflow 3)."""
        astro_dir = tmp_path / ".astro"
        astro_dir.mkdir()
        config_file = astro_dir / "config.yaml"
        config_file.write_text("api-server:\n  port: 8082\n")

        backend = LocalDiscoveryBackend()
        port = backend._get_astro_project_port(tmp_path)

        assert port == 8082

    def test_get_astro_project_port_prefers_api_server(self, tmp_path):
        """Test _get_astro_project_port prefers api-server over webserver."""
        astro_dir = tmp_path / ".astro"
        astro_dir.mkdir()
        config_file = astro_dir / "config.yaml"
        config_file.write_text("api-server:\n  port: 8082\nwebserver:\n  port: 8081\n")

        backend = LocalDiscoveryBackend()
        port = backend._get_astro_project_port(tmp_path)

        assert port == 8082

    def test_get_astro_project_port_no_config(self, tmp_path):
        """Test _get_astro_project_port returns None when no config."""
        backend = LocalDiscoveryBackend()
        port = backend._get_astro_project_port(tmp_path)

        assert port is None

    def test_get_astro_project_port_no_port_in_config(self, tmp_path):
        """Test _get_astro_project_port returns None when no port in config."""
        astro_dir = tmp_path / ".astro"
        astro_dir.mkdir()
        config_file = astro_dir / "config.yaml"
        config_file.write_text("project:\n  name: test\n")

        backend = LocalDiscoveryBackend()
        port = backend._get_astro_project_port(tmp_path)

        assert port is None
