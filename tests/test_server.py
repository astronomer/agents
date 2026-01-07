"""Tests for server API client wrapper."""

import json
import time

import pytest
import requests

from astro_airflow_mcp.server import (
    DEFAULT_AIRFLOW_URL,
    TOKEN_REFRESH_BUFFER_SECONDS,
    AirflowTokenManager,
    _call_airflow_api,
    _config,
    _get_auth_token,
    _get_dag_details_impl,
    _list_dags_impl,
    _post_airflow_api,
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


class TestCallAirflowAPI:
    """Tests for the _call_airflow_api function."""

    def test_basic_api_call(self, mocker):
        """Test basic API call without authentication."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": []}
        mock_response.raise_for_status = mocker.Mock()
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        result = _call_airflow_api("dags")

        assert result == {"dags": []}
        mock_get.assert_called_once_with(
            f"{DEFAULT_AIRFLOW_URL}/api/v2/dags",
            params=None,
            headers={},
            timeout=30,
        )

    def test_api_call_with_auth_token(self, mocker):
        """Test API call with Bearer token authentication."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"version": "3.0.0"}
        mock_response.raise_for_status = mocker.Mock()
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        result = _call_airflow_api("version", auth_token="test_token_123")

        assert result == {"version": "3.0.0"}
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_token_123"

    def test_api_call_with_params(self, mocker):
        """Test API call with query parameters."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": [], "total_entries": 0}
        mock_response.raise_for_status = mocker.Mock()
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        params = {"limit": 50, "offset": 10}
        result = _call_airflow_api("dags", params=params)

        assert result == {"dags": [], "total_entries": 0}
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"] == params

    def test_api_call_with_custom_url(self, mocker):
        """Test API call with custom Airflow URL."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = mocker.Mock()
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        custom_url = "https://custom.airflow.com"
        result = _call_airflow_api("health", airflow_url=custom_url)

        assert result == {"status": "ok"}
        mock_get.assert_called_once()
        call_args = mock_get.call_args[0]
        assert call_args[0] == f"{custom_url}/api/v2/health"

    def test_api_call_request_exception(self, mocker):
        """Test API call handles request exceptions."""
        mocker.patch(
            "requests.get",
            side_effect=requests.exceptions.ConnectionError("Connection failed"),
        )

        with pytest.raises(Exception) as exc_info:
            _call_airflow_api("dags")

        assert "Error connecting to Airflow API" in str(exc_info.value)
        assert "Connection failed" in str(exc_info.value)

    def test_api_call_http_error(self, mocker):
        """Test API call handles HTTP errors."""
        mock_response = mocker.Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mocker.patch("requests.get", return_value=mock_response)

        with pytest.raises(Exception) as exc_info:
            _call_airflow_api("dags/nonexistent")

        assert "Error connecting to Airflow API" in str(exc_info.value)


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
        mock_response.json.return_value = {
            "access_token": "test_jwt_token",
            "token_type": "bearer",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = mocker.Mock()
        mock_post = mocker.patch("requests.post", return_value=mock_response)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="secret",
        )
        manager._fetch_token()

        assert manager._token == "test_jwt_token"
        assert manager._token_fetched_at is not None
        assert manager._token_lifetime_seconds == 3600
        mock_post.assert_called_once_with(
            "http://localhost:8080/auth/token",
            json={"username": "admin", "password": "secret"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    def test_fetch_token_credential_less(self, mocker):
        """Test credential-less token fetch (all_admins mode)."""
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "access_token": "admin_token",
            "token_type": "bearer",
        }
        mock_response.raise_for_status = mocker.Mock()
        mock_get = mocker.patch("requests.get", return_value=mock_response)

        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        manager._fetch_token()

        assert manager._token == "admin_token"
        mock_get.assert_called_once_with(
            "http://localhost:8080/auth/token",
            timeout=30,
        )

    def test_fetch_token_failure(self, mocker):
        """Test token fetch handles request failures."""
        mocker.patch(
            "requests.post",
            side_effect=requests.exceptions.ConnectionError("Connection failed"),
        )

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
        mock_response.json.return_value = {"access_token": "new_token"}
        mock_response.raise_for_status = mocker.Mock()
        mocker.patch("requests.post", return_value=mock_response)

        manager = AirflowTokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        token = manager.get_token()

        assert token == "new_token"

    def test_get_token_returns_cached(self, mocker):
        """Test get_token returns cached token when valid."""
        mock_post = mocker.patch("requests.post")

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
        mock_post.assert_not_called()

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
        mocker.patch("requests.get", return_value=mock_response)

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
        mocker.patch("requests.post", return_value=mock_response)

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
        mock_get = mocker.patch("requests.get")

        manager = AirflowTokenManager(airflow_url="http://localhost:8080")
        manager._token_endpoint_available = False

        token = manager.get_token()

        assert token is None
        mock_get.assert_not_called()

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


class TestAPIRetryOnAuthError:
    """Tests for API retry behavior on 401/403 errors."""

    def test_call_api_retry_on_401(self, mocker, reset_config):
        """Test _call_airflow_api retries on 401 with fresh token."""
        # Setup token manager
        mock_manager = mocker.Mock()
        mock_manager.get_token.side_effect = ["old_token", "new_token"]
        _config.token_manager = mock_manager
        _config.auth_token = None

        # First call returns 401, second succeeds
        mock_response_401 = mocker.Mock()
        mock_response_401.status_code = 401

        mock_response_ok = mocker.Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"data": "success"}
        mock_response_ok.raise_for_status = mocker.Mock()

        mock_get = mocker.patch("requests.get", side_effect=[mock_response_401, mock_response_ok])

        result = _call_airflow_api("dags")

        assert result == {"data": "success"}
        assert mock_get.call_count == 2
        mock_manager.invalidate.assert_called_once()

    def test_call_api_no_retry_with_explicit_token(self, mocker):
        """Test _call_airflow_api does not retry when explicit token provided."""
        mock_response = mocker.Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401")
        mocker.patch("requests.get", return_value=mock_response)

        with pytest.raises(Exception) as exc_info:
            _call_airflow_api("dags", auth_token="explicit_token")

        assert "Error connecting to Airflow API" in str(exc_info.value)

    def test_post_api_retry_on_403(self, mocker, reset_config):
        """Test _post_airflow_api retries on 403 with fresh token."""
        # Setup token manager
        mock_manager = mocker.Mock()
        mock_manager.get_token.side_effect = ["old_token", "new_token"]
        _config.token_manager = mock_manager
        _config.auth_token = None

        # First call returns 403, second succeeds
        mock_response_403 = mocker.Mock()
        mock_response_403.status_code = 403

        mock_response_ok = mocker.Mock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"dag_run_id": "test_run"}
        mock_response_ok.raise_for_status = mocker.Mock()

        mock_post = mocker.patch("requests.post", side_effect=[mock_response_403, mock_response_ok])

        result = _post_airflow_api("dags/test/dagRuns", json_data={})

        assert result == {"dag_run_id": "test_run"}
        assert mock_post.call_count == 2
        mock_manager.invalidate.assert_called_once()


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
