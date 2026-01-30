"""Tests for server API client wrapper."""

import json
import time

import httpx
import pytest

from astro_airflow_mcp.auth import TOKEN_REFRESH_BUFFER_SECONDS, TokenManager
from astro_airflow_mcp.server import (
    _manager,
    configure,
)
from astro_airflow_mcp.tools.asset import (
    _get_upstream_asset_events_impl,
    _list_asset_events_impl,
)
from astro_airflow_mcp.tools.dag import (
    _get_dag_details_impl,
    _list_dags_impl,
)
from astro_airflow_mcp.tools.task import (
    _clear_task_instances_impl,
)


@pytest.fixture
def reset_config():
    """Fixture that saves and restores global config after each test."""
    original_url = _manager._airflow_url
    original_token = _manager._auth_token
    original_token_manager = _manager._token_manager
    yield
    _manager._airflow_url = original_url
    _manager._auth_token = original_token
    _manager._token_manager = original_token_manager
    _manager._adapter = None


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
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

        result = _get_dag_details_impl("example_dag")
        result_data = json.loads(result)

        assert result_data["dag_id"] == "example_dag"
        assert result_data["is_paused"] is False
        assert result_data["description"] == "Test DAG"

    def test_get_dag_details_impl_error(self, mocker):
        """Test _get_dag_details_impl with adapter error."""
        mock_adapter = mocker.Mock()
        mock_adapter.get_dag.side_effect = Exception("DAG not found")
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

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
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

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
        mocker.patch("astro_airflow_mcp.tools.dag._get_adapter", return_value=mock_adapter)

        result = _list_dags_impl()
        result_data = json.loads(result)

        assert result_data["total_dags"] == 0
        assert result_data["returned_count"] == 0
        assert result_data["dags"] == []

    def test_list_asset_events_impl_success(self, mocker):
        """Test _list_asset_events_impl with successful response."""
        mock_response = {
            "asset_events": [
                {
                    "asset_uri": "s3://bucket/path",
                    "source_dag_id": "producer_dag",
                    "source_run_id": "run_123",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ],
            "total_entries": 1,
        }
        mock_adapter = mocker.Mock()
        mock_adapter.list_asset_events.return_value = mock_response
        mocker.patch("astro_airflow_mcp.tools.asset._get_adapter", return_value=mock_adapter)

        result = _list_asset_events_impl(source_dag_id="producer_dag")
        result_data = json.loads(result)

        assert result_data["total_asset_events"] == 1
        assert result_data["returned_count"] == 1
        assert result_data["asset_events"][0]["source_dag_id"] == "producer_dag"
        mock_adapter.list_asset_events.assert_called_once_with(
            limit=100,
            offset=0,
            source_dag_id="producer_dag",
            source_run_id=None,
            source_task_id=None,
        )

    def test_list_asset_events_impl_empty(self, mocker):
        """Test _list_asset_events_impl with no events."""
        mock_response = {"asset_events": [], "total_entries": 0}
        mock_adapter = mocker.Mock()
        mock_adapter.list_asset_events.return_value = mock_response
        mocker.patch("astro_airflow_mcp.tools.asset._get_adapter", return_value=mock_adapter)

        result = _list_asset_events_impl()
        result_data = json.loads(result)

        assert result_data["total_asset_events"] == 0
        assert result_data["returned_count"] == 0
        assert result_data["asset_events"] == []

    def test_get_upstream_asset_events_impl_success(self, mocker):
        """Test _get_upstream_asset_events_impl with successful response."""
        mock_response = {
            "asset_events": [
                {
                    "asset_uri": "s3://bucket/input",
                    "source_dag_id": "upstream_dag",
                    "source_run_id": "upstream_run",
                    "timestamp": "2024-01-01T00:00:00Z",
                },
            ],
        }
        mock_adapter = mocker.Mock()
        mock_adapter.get_dag_run_upstream_asset_events.return_value = mock_response
        mocker.patch("astro_airflow_mcp.tools.asset._get_adapter", return_value=mock_adapter)

        result = _get_upstream_asset_events_impl("consumer_dag", "run_123")
        result_data = json.loads(result)

        assert result_data["dag_id"] == "consumer_dag"
        assert result_data["dag_run_id"] == "run_123"
        assert result_data["event_count"] == 1
        assert result_data["triggered_by_events"][0]["source_dag_id"] == "upstream_dag"
        mock_adapter.get_dag_run_upstream_asset_events.assert_called_once_with(
            "consumer_dag", "run_123"
        )

    def test_get_upstream_asset_events_impl_empty(self, mocker):
        """Test _get_upstream_asset_events_impl with no triggering events."""
        mock_response = {"asset_events": []}
        mock_adapter = mocker.Mock()
        mock_adapter.get_dag_run_upstream_asset_events.return_value = mock_response
        mocker.patch("astro_airflow_mcp.tools.asset._get_adapter", return_value=mock_adapter)

        result = _get_upstream_asset_events_impl("dag", "run")
        result_data = json.loads(result)

        assert result_data["event_count"] == 0
        assert result_data["triggered_by_events"] == []

    def test_clear_task_instances_impl_success(self, mocker):
        """Test _clear_task_instances_impl with successful response."""
        mock_response = {
            "task_instances": [
                {
                    "dag_id": "example_dag",
                    "dag_run_id": "manual__2024-01-01",
                    "task_id": "my_task",
                    "state": "cleared",
                },
            ],
        }
        mock_adapter = mocker.Mock()
        mock_adapter.clear_task_instances.return_value = mock_response
        mocker.patch("astro_airflow_mcp.tools.task._get_adapter", return_value=mock_adapter)

        result = _clear_task_instances_impl(
            dag_id="example_dag",
            dag_run_id="manual__2024-01-01",
            task_ids=["my_task"],
            dry_run=False,
        )
        result_data = json.loads(result)

        assert len(result_data["task_instances"]) == 1
        assert result_data["task_instances"][0]["task_id"] == "my_task"
        assert result_data["task_instances"][0]["state"] == "cleared"
        mock_adapter.clear_task_instances.assert_called_once_with(
            dag_id="example_dag",
            dag_run_id="manual__2024-01-01",
            task_ids=["my_task"],
            dry_run=False,
            only_failed=False,
            include_downstream=False,
        )

    def test_clear_task_instances_impl_error(self, mocker):
        """Test _clear_task_instances_impl with adapter error."""
        mock_adapter = mocker.Mock()
        mock_adapter.clear_task_instances.side_effect = Exception("DAG not found")
        mocker.patch("astro_airflow_mcp.tools.task._get_adapter", return_value=mock_adapter)

        result = _clear_task_instances_impl(
            dag_id="nonexistent_dag",
            dag_run_id="run_123",
            task_ids=["task1"],
        )

        assert "DAG not found" in result


class TestConfiguration:
    """Tests for global configuration."""

    def test_configure_url(self, reset_config):
        """Test configure() updates global URL."""
        configure(url="https://test.airflow.com")
        assert _manager._airflow_url == "https://test.airflow.com"

    def test_configure_auth_token(self, reset_config):
        """Test configure() updates global auth token."""
        configure(auth_token="new_token_456")
        assert _manager._auth_token == "new_token_456"

    def test_configure_both(self, reset_config):
        """Test configure() updates both URL and token."""
        configure(url="https://prod.airflow.com", auth_token="prod_token")
        assert _manager._airflow_url == "https://prod.airflow.com"
        assert _manager._auth_token == "prod_token"

    def test_configure_with_username_password(self, reset_config):
        """Test configure() creates token manager with username/password."""
        configure(
            url="https://test.airflow.com",
            username="testuser",
            password="testpass",
        )
        assert _manager._airflow_url == "https://test.airflow.com"
        assert _manager._auth_token is None  # Direct token should be None
        assert _manager._token_manager is not None
        assert _manager._token_manager.username == "testuser"
        assert _manager._token_manager.password == "testpass"

    def test_configure_auth_token_takes_precedence(self, reset_config):
        """Test that auth_token takes precedence over username/password."""
        configure(
            auth_token="direct_token",
            username="testuser",
            password="testpass",
        )
        assert _manager._auth_token == "direct_token"
        assert _manager._token_manager is None  # Token manager not created


class TestTokenManager:
    """Tests for the TokenManager class."""

    def test_init(self):
        """Test token manager initialization."""
        manager = TokenManager(
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
        manager = TokenManager("http://localhost:8080")
        assert manager._should_refresh() is True

    def test_should_refresh_with_valid_token(self):
        """Test _should_refresh returns False for valid token."""
        manager = TokenManager("http://localhost:8080")
        manager._token = "valid_token"
        manager._token_fetched_at = time.time()
        manager._token_lifetime_seconds = 3600  # 1 hour
        assert manager._should_refresh() is False

    def test_should_refresh_expired_token(self):
        """Test _should_refresh returns True for expired token."""
        manager = TokenManager("http://localhost:8080")
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

        manager = TokenManager(
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

        manager = TokenManager(airflow_url="http://localhost:8080")
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

        manager = TokenManager(
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

        manager = TokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="admin",
        )
        token = manager.get_token()

        assert token == "new_token"

    def test_get_token_returns_cached(self, mocker):
        """Test get_token returns cached token when valid."""
        mock_client = mocker.patch("httpx.Client")

        manager = TokenManager(
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
        manager = TokenManager("http://localhost:8080")
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

        manager = TokenManager(airflow_url="http://localhost:8080")
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

        manager = TokenManager(
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

        manager = TokenManager(airflow_url="http://localhost:8080")
        manager._token_endpoint_available = False

        token = manager.get_token()

        assert token is None
        mock_client.assert_not_called()

    def test_get_basic_auth(self):
        """Test get_basic_auth returns credentials."""
        manager = TokenManager(
            airflow_url="http://localhost:8080",
            username="admin",
            password="secret",
        )
        auth = manager.get_basic_auth()

        assert auth == ("admin", "secret")

    def test_get_basic_auth_none_without_credentials(self):
        """Test get_basic_auth returns None without credentials."""
        manager = TokenManager(airflow_url="http://localhost:8080")
        auth = manager.get_basic_auth()

        assert auth is None


class TestGetAuthToken:
    """Tests for the _get_auth_token helper function."""

    def test_returns_direct_token(self, reset_config):
        """Test _get_auth_token returns direct auth_token when set."""
        _manager._auth_token = "direct_token"
        _manager._token_manager = None

        token = _manager._get_auth_token()
        assert token == "direct_token"

    def test_returns_token_from_manager(self, mocker, reset_config):
        """Test _get_auth_token returns token from manager."""
        _manager._auth_token = None
        mock_manager = mocker.Mock()
        mock_manager.get_token.return_value = "manager_token"
        _manager._token_manager = mock_manager

        token = _manager._get_auth_token()
        assert token == "manager_token"
        mock_manager.get_token.assert_called_once()

    def test_direct_token_takes_precedence(self, mocker, reset_config):
        """Test direct auth_token takes precedence over token manager."""
        _manager._auth_token = "direct_token"
        mock_manager = mocker.Mock()
        mock_manager.get_token.return_value = "manager_token"
        _manager._token_manager = mock_manager

        token = _manager._get_auth_token()
        assert token == "direct_token"
        mock_manager.get_token.assert_not_called()
