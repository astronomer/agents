"""Tests for Airflow API adapters."""

import pytest

from astro_airflow_mcp.adapters import (
    AirflowV2Adapter,
    AirflowV3Adapter,
    NotFoundError,
    create_adapter,
    detect_version,
)


class TestNotFoundError:
    """Tests for NotFoundError exception."""

    def test_notfounderror_message(self):
        """Test NotFoundError includes endpoint in message."""
        error = NotFoundError("dagStats")
        assert error.endpoint == "dagStats"
        assert "dagStats" in str(error)


class TestAirflowV2Adapter:
    """Tests for AirflowV2Adapter."""

    def test_api_base_path(self):
        """Test V2 adapter uses /api/v1 path."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )
        assert adapter.api_base_path == "/api/v1"

    def test_setup_auth_with_token_getter(self):
        """Test auth setup with token getter."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
            token_getter=lambda: "test_token",
        )
        headers, auth = adapter._setup_auth()
        assert headers["Authorization"] == "Bearer test_token"
        assert auth is None

    def test_setup_auth_none(self):
        """Test auth setup with no token getter."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )
        headers, auth = adapter._setup_auth()
        assert headers == {}
        assert auth is None

    def test_setup_auth_token_getter_returns_none(self):
        """Test auth setup when token getter returns None."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
            token_getter=lambda: None,
        )
        headers, auth = adapter._setup_auth()
        assert headers == {}
        assert auth is None

    def test_get_dag_stats_returns_not_available(self):
        """Test V2 adapter returns not available for dagStats."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )
        result = adapter.get_dag_stats()
        assert result["available"] is False
        assert "alternative" in result

    def test_list_dags_call(self, mocker):
        """Test list_dags makes correct API call."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
            token_getter=lambda: "test_token",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": [], "total_entries": 0}
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.list_dags(limit=50, offset=0)

        assert result == {"dags": [], "total_entries": 0}
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/api/v1/dags" in call_args[0][0]

    def test_list_assets_normalizes_field_names(self, mocker):
        """Test V2 adapter normalizes datasets to assets."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "datasets": [
                {
                    "id": 1,
                    "uri": "s3://bucket/path",
                    "consuming_dags": [{"dag_id": "consumer"}],
                }
            ],
            "total_entries": 1,
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.list_assets()

        # Check normalization
        assert "assets" in result
        assert "datasets" not in result
        assert result["assets"][0]["scheduled_dags"] == [{"dag_id": "consumer"}]
        assert "consuming_dags" not in result["assets"][0]


class TestAirflowV3Adapter:
    """Tests for AirflowV3Adapter."""

    def test_api_base_path(self):
        """Test V3 adapter uses /api/v2 path."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )
        assert adapter.api_base_path == "/api/v2"

    def test_get_dag_stats_call(self, mocker):
        """Test V3 adapter calls dagStats endpoint."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": []}
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.get_dag_stats()

        assert result == {"dags": []}
        call_args = mock_client.get.call_args
        assert "/api/v2/dagStats" in call_args[0][0]

    def test_passthrough_params(self, mocker):
        """Test kwargs are passed through to API call."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": []}
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        # Pass additional filter params
        adapter.list_dags(limit=10, offset=0, tags=["production"], only_active=True)

        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["params"]["tags"] == ["production"]
        assert call_kwargs["params"]["only_active"] is True


class TestVersionDetection:
    """Tests for version detection logic."""

    def test_detect_version_v3(self, mocker):
        """Test version detection for Airflow 3.x."""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "3.0.0"}

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        major, full = detect_version("http://localhost:8080")

        assert major == 3
        assert full == "3.0.0"

    def test_detect_version_v2(self, mocker):
        """Test version detection for Airflow 2.x."""
        # First call to /api/v2/version fails (not Airflow 3)
        fail_response = mocker.Mock()
        fail_response.status_code = 404

        # Second call to /api/v1/version succeeds
        success_response = mocker.Mock()
        success_response.status_code = 200
        success_response.json.return_value = {"version": "2.9.0"}

        mock_client = mocker.Mock()
        mock_client.get.side_effect = [fail_response, success_response]
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        major, full = detect_version("http://localhost:8080")

        assert major == 2
        assert full == "2.9.0"

    def test_detect_version_with_token_getter(self, mocker):
        """Test version detection uses token getter for auth."""
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "3.0.0"}

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        major, full = detect_version(
            "http://localhost:8080",
            token_getter=lambda: "test_token",
        )

        assert major == 3
        assert full == "3.0.0"
        # Verify token was used in the request
        call_kwargs = mock_client.get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer test_token"


class TestAdapterFactory:
    """Tests for adapter factory."""

    def test_create_adapter_v3(self, mocker):
        """Test factory creates V3 adapter for Airflow 3.x."""
        mocker.patch(
            "astro_airflow_mcp.adapters.detect_version",
            return_value=(3, "3.0.0"),
        )

        adapter = create_adapter("http://localhost:8080")

        assert isinstance(adapter, AirflowV3Adapter)
        assert adapter.version == "3.0.0"

    def test_create_adapter_v2(self, mocker):
        """Test factory creates V2 adapter for Airflow 2.x."""
        mocker.patch(
            "astro_airflow_mcp.adapters.detect_version",
            return_value=(2, "2.9.0"),
        )

        adapter = create_adapter("http://localhost:8080")

        assert isinstance(adapter, AirflowV2Adapter)
        assert adapter.version == "2.9.0"

    def test_create_adapter_with_token_getter(self, mocker):
        """Test factory passes token getter to adapter."""
        mocker.patch(
            "astro_airflow_mcp.adapters.detect_version",
            return_value=(3, "3.0.0"),
        )

        token_getter = lambda: "test_token"  # noqa: E731
        adapter = create_adapter("http://localhost:8080", token_getter=token_getter)

        assert isinstance(adapter, AirflowV3Adapter)
        assert adapter._token_getter is token_getter

    def test_create_adapter_unsupported_version(self, mocker):
        """Test factory raises error for unsupported version."""
        mocker.patch(
            "astro_airflow_mcp.adapters.detect_version",
            return_value=(1, "1.10.0"),
        )

        with pytest.raises(RuntimeError) as exc_info:
            create_adapter("http://localhost:8080")

        assert "Unsupported Airflow version" in str(exc_info.value)


class TestFeatureDetection:
    """Tests for runtime feature detection."""

    def test_v2_adapter_notfound_handling(self, mocker):
        """Test V2 adapter handles 404 gracefully for missing endpoints."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.6.0",
        )

        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        # list_assets should handle 404 gracefully for old Airflow versions
        result = adapter.list_assets()

        assert result["available"] is False
        assert "alternative" in result

    def test_handle_not_found_method(self):
        """Test _handle_not_found returns structured response."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        result = adapter._handle_not_found("testEndpoint", alternative="Use alternative")

        assert result["available"] is False
        assert "testEndpoint" in result["note"]
        assert result["alternative"] == "Use alternative"
