"""Tests for server API client wrapper."""

import json
import time

import httpx
import pytest

from astro_airflow_mcp.server import (
    TOKEN_REFRESH_BUFFER_SECONDS,
    AirflowTokenManager,
    _config,
    _get_auth_token,
    _get_dag_details_impl,
    _list_dags_impl,
    configure,
)


@pytest.fixture
def reset_config():
    """Fixture that saves and restores global config after each test."""
    original_url = _config.url
    original_token = _config.auth_token
    original_manager = _config.token_manager
    yield
    _config.url = original_url
    _config.auth_token = original_token
    _config.token_manager = original_manager


class TestImplFunctions:
    """Tests for _impl functions using mocked adapters."""

    def test_get_dag_details_impl_success(self, mocker):
        """Test _get_dag_details_impl with successful response."""
        mock_dag_data = {
            "dag_id": "example_dag",
            "is_paused": False,
            "description": "Test DAG",
        }
        mock_adapter = mocker.Mock()
        mock_adapter.get_dag.return_value = mock_dag_data
        mocker.patch("astro_airflow_mcp.server._get_adapter", return_value=mock_adapter)

        result = _get_dag_details_impl("example_dag")
        result_data = json.loads(result)

        assert result_data["dag_id"] == "example_dag"
        assert result_data["is_paused"] is False
        assert result_data["description"] == "Test DAG"

    def test_get_dag_details_impl_error(self, mocker):
        """Test _get_dag_details_impl with adapter error."""
        mock_adapter = mocker.Mock()
        mock_adapter.get_dag.side_effect = Exception("DAG not found")
        mocker.patch("astro_airflow_mcp.server._get_adapter", return_value=mock_adapter)

        result = _get_dag_details_impl("nonexistent_dag")

        assert "DAG not found" in result

    def test_list_dags_impl_success(self, mocker):
        """Test _list_dags_impl with successful response."""
        mock_response = {
            "dags": [
                {"dag_id": "dag1", "is_paused": False},
                {"dag_id": "dag2", "is_paused": True},
            ],
            "total_entries": 2,
        }
        mock_adapter = mocker.Mock()
        mock_adapter.list_dags.return_value = mock_response
        mocker.patch("astro_airflow_mcp.server._get_adapter", return_value=mock_adapter)

        result = _list_dags_impl(limit=10, offset=0)
        result_data = json.loads(result)

        assert result_data["total_dags"] == 2
        assert result_data["returned_count"] == 2
        assert len(result_data["dags"]) == 2
        assert result_data["dags"][0]["dag_id"] == "dag1"

    def test_list_dags_impl_empty(self, mocker):
        """Test _list_dags_impl with no DAGs."""
        mock_response = {"dags": [], "total_entries": 0}
        mock_adapter = mocker.Mock()
        mock_adapter.list_dags.return_value = mock_response
        mocker.patch("astro_airflow_mcp.server._get_adapter", return_value=mock_adapter)

        result = _list_dags_impl()
        result_data = json.loads(result)

        assert result_data["total_dags"] == 0
        assert result_data["returned_count"] == 0
        assert result_data["dags"] == []


class TestConfiguration:
    """Tests for global configuration."""

    def test_configure_url(self, reset_config):
        """Test configure() updates global URL."""
        configure(url="https://test.airflow.com")
        assert _config.url == "https://test.airflow.com"

    def test_configure_auth_token(self, reset_config):
        """Test configure() updates global auth token."""
        configure(auth_token="new_token_456")
        assert _config.auth_token == "new_token_456"

    def test_configure_both(self, reset_config):
        """Test configure() updates both URL and token."""
        configure(url="https://prod.airflow.com", auth_token="prod_token")
        assert _config.url == "https://prod.airflow.com"
        assert _config.auth_token == "prod_token"

    def test_configure_with_username_password(self, reset_config):
        """Test configure() creates token manager with username/password."""
        configure(
            url="https://test.airflow.com",
            username="testuser",
            password="testpass",
        )
        assert _config.url == "https://test.airflow.com"
        assert _config.auth_token is None  # Direct token should be None
        assert _config.token_manager is not None
        assert _config.token_manager.username == "testuser"
        assert _config.token_manager.password == "testpass"

    def test_configure_auth_token_takes_precedence(self, reset_config):
        """Test that auth_token takes precedence over username/password."""
        configure(
            auth_token="direct_token",
            username="testuser",
            password="testpass",
        )
        assert _config.auth_token == "direct_token"
        assert _config.token_manager is None  # Token manager not created


class TestAirflowTokenManager:
    """Tests for the AirflowTokenManager class."""

    def test_init(self):
        """Test token manager initialization."""
        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        assert manager.airflow_url == "http://localhost:8080"
        assert manager.username == "admin"
        assert manager.password == "admin"
        assert manager._token is None
        assert manager._token_fetched_at is None

    def test_should_refresh_no_token(self):
        """Test _should_refresh returns True when no token exists."""
        manager = AirflowTokenManager("http://localhost:8080")
        assert manager._should_refresh() is True

    def test_should_refresh_with_valid_token(self):
        """Test _should_refresh returns False for valid token."""
        manager = AirflowTokenManager("http://localhost:8080")
        manager._token = "valid_token"
        manager._token_fetched_at = time.time()
        manager._token_lifetime_seconds = 3600  # 1 hour
        assert manager._should_refresh() is False

    def test_should_refresh_expired_token(self):
        """Test _should_refresh returns True for expired token."""
        manager = AirflowTokenManager("http://localhost:8080")
        manager._token = "expired_token"
        # Set fetched_at to be past the lifetime minus buffer
        manager._token_lifetime_seconds = 1800
        manager._token_fetched_at = (
            time.time() - manager._token_lifetime_seconds + TOKEN_REFRESH_BUFFER_SECONDS - 10
        )
        assert manager._should_refresh() is True

    def test_fetch_token_with_credentials(self, mocker):
        """Test token fetch with username/password credentials."""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_jwt_token",
            "token_type": "bearer",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="secret",
        )
        manager._fetch_token()

        assert manager._token == "test_jwt_token"
        assert manager._token_fetched_at is not None
        assert manager._token_lifetime_seconds == 3600
        mock_client.post.assert_called_once_with(
            "http://localhost:8080/auth/token",
            json={"username": "admin", "password": "secret"},
            headers={"Content-Type": "application/json"},
        )

    def test_fetch_token_credential_less(self, mocker):
        """Test credential-less token fetch (all_admins mode)."""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "admin_token",
            "token_type": "bearer",
        }
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        manager._fetch_token()

        assert manager._token == "admin_token"
        mock_client.get.assert_called_once_with("http://localhost:8080/auth/token")

    def test_fetch_token_failure(self, mocker):
        """Test token fetch handles request failures."""
        mock_client = mocker.Mock()
        mock_client.post.side_effect = httpx.RequestError("Connection failed")
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        manager._fetch_token()

        assert manager._token is None

    def test_get_token_fetches_when_needed(self, mocker):
        """Test get_token fetches token when refresh needed."""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new_token"}
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        token = manager.get_token()

        assert token == "new_token"

    def test_get_token_returns_cached(self, mocker):
        """Test get_token returns cached token when valid."""
        mock_client = mocker.patch("httpx.Client")

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        manager._token = "cached_token"
        manager._token_fetched_at = time.time()
        manager._token_lifetime_seconds = 3600

        token = manager.get_token()

        assert token == "cached_token"
        mock_client.assert_not_called()

    def test_invalidate(self):
        """Test token invalidation."""
        manager = AirflowTokenManager("http://localhost:8080")
        manager._token = "some_token"
        manager._token_fetched_at = time.time()

        manager.invalidate()

        assert manager._token is None
        assert manager._token_fetched_at is None

    def test_fetch_token_404_marks_unavailable(self, mocker):
        """Test that 404 response marks token endpoint as unavailable (Airflow 2.x)."""
        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        manager._fetch_token()

        assert manager._token is None
        assert manager._token_endpoint_available is False
        # Should default to admin:admin for Airflow 2.x
        assert manager.username == "admin"
        assert manager.password == "admin"

    def test_fetch_token_404_keeps_provided_credentials(self, mocker):
        """Test that 404 keeps user-provided credentials instead of defaulting."""
        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)
        mocker.patch("httpx.Client", return_value=mock_client)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="custom_user",
            password="custom_pass",
        )
        manager._fetch_token()

        assert manager._token is None
        assert manager._token_endpoint_available is False
        # Should keep provided credentials
        assert manager.username == "custom_user"
        assert manager.password == "custom_pass"

    def test_get_token_skips_unavailable_endpoint(self, mocker):
        """Test that get_token doesn't retry when endpoint is marked unavailable."""
        mock_client = mocker.patch("httpx.Client")

        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        manager._token_endpoint_available = False

        token = manager.get_token()

        assert token is None
        mock_client.assert_not_called()

    def test_get_basic_auth(self):
        """Test get_basic_auth returns credentials."""
        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="secret",
        )
        auth = manager.get_basic_auth()

        assert auth == ("admin", "secret")

    def test_get_basic_auth_none_without_credentials(self):
        """Test get_basic_auth returns None without credentials."""
        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        auth = manager.get_basic_auth()

        assert auth is None


class TestGetAuthToken:
    """Tests for the _get_auth_token helper function."""

    def test_returns_direct_token(self, reset_config):
        """Test _get_auth_token returns direct auth_token when set."""
        _config.auth_token = "direct_token"
        _config.token_manager = None

        token = _get_auth_token()
        assert token == "direct_token"

    def test_returns_token_from_manager(self, mocker, reset_config):
        """Test _get_auth_token returns token from manager."""
        _config.auth_token = None
        mock_manager = mocker.Mock()
        mock_manager.get_token.return_value = "manager_token"
        _config.token_manager = mock_manager

        token = _get_auth_token()
        assert token == "manager_token"
        mock_manager.get_token.assert_called_once()

    def test_direct_token_takes_precedence(self, mocker, reset_config):
        """Test direct auth_token takes precedence over token manager."""
        _config.auth_token = "direct_token"
        mock_manager = mocker.Mock()
        mock_manager.get_token.return_value = "manager_token"
        _config.token_manager = mock_manager

        token = _get_auth_token()
        assert token == "direct_token"
        mock_manager.get_token.assert_not_called()
