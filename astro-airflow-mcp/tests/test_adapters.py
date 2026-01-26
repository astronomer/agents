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

    def test_get_dag_stats_call_with_dag_ids(self, mocker):
        """Test V2 adapter calls dagStats endpoint correctly with specific dag_ids."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dags": [
                {
                    "dag_id": "example_dag",
                    "stats": [{"state": "success", "count": 5}],
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

        result = adapter.get_dag_stats(dag_ids=["example_dag"])

        assert result["total_entries"] == 1
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/api/v1/dagStats" in call_args[0][0]
        assert call_args[1]["params"]["dag_ids"] == "example_dag"

    def test_get_dag_stats_call_without_dag_ids(self, mocker):
        """Test V2 adapter fetches all DAGs first when dag_ids not provided."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        # Mock list_dags response
        dags_response = mocker.Mock()
        dags_response.json.return_value = {
            "dags": [
                {"dag_id": "dag1"},
                {"dag_id": "dag2"},
            ],
            "total_entries": 2,
        }
        dags_response.status_code = 200
        dags_response.raise_for_status = mocker.Mock()

        # Mock dagStats response
        stats_response = mocker.Mock()
        stats_response.json.return_value = {
            "dags": [
                {"dag_id": "dag1", "stats": [{"state": "success", "count": 3}]},
                {"dag_id": "dag2", "stats": [{"state": "failed", "count": 1}]},
            ],
            "total_entries": 2,
        }
        stats_response.status_code = 200
        stats_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        # First call returns dags, second call returns stats
        mock_client.get.side_effect = [dags_response, stats_response]
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.get_dag_stats(dag_ids=None)

        assert result["total_entries"] == 2
        assert mock_client.get.call_count == 2

        # First call should be to list_dags
        first_call = mock_client.get.call_args_list[0]
        assert "/api/v1/dags" in first_call[0][0]

        # Second call should be to dagStats with all dag_ids
        second_call = mock_client.get.call_args_list[1]
        assert "/api/v1/dagStats" in second_call[0][0]
        assert second_call[1]["params"]["dag_ids"] == "dag1,dag2"

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

    def test_list_asset_events_normalizes_field_names(self, mocker):
        """Test V2 adapter normalizes dataset_events to asset_events."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dataset_events": [
                {
                    "dataset_uri": "s3://bucket/path",
                    "source_dag_id": "producer_dag",
                    "source_run_id": "run_123",
                    "timestamp": "2024-01-01T00:00:00Z",
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

        result = adapter.list_asset_events(source_dag_id="producer_dag")

        # Check normalization
        assert "asset_events" in result
        assert "dataset_events" not in result
        assert "uri" in result["asset_events"][0]
        assert "dataset_uri" not in result["asset_events"][0]
        assert result["asset_events"][0]["source_dag_id"] == "producer_dag"

        # Verify endpoint and params
        call_args = mock_client.get.call_args
        assert "/api/v1/datasets/events" in call_args[0][0]
        assert call_args[1]["params"]["source_dag_id"] == "producer_dag"

    def test_get_dag_run_upstream_asset_events_normalizes_field_names(self, mocker):
        """Test V2 adapter normalizes dataset_events to asset_events for upstream events."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dataset_events": [
                {
                    "dataset_uri": "s3://bucket/input",
                    "source_dag_id": "upstream_dag",
                    "source_run_id": "upstream_run",
                }
            ],
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.get_dag_run_upstream_asset_events("consumer_dag", "run_123")

        # Check normalization
        assert "asset_events" in result
        assert "dataset_events" not in result
        assert "uri" in result["asset_events"][0]
        assert "dataset_uri" not in result["asset_events"][0]
        assert result["asset_events"][0]["source_dag_id"] == "upstream_dag"

        # Verify endpoint
        call_args = mock_client.get.call_args
        assert "/api/v1/dags/consumer_dag/dagRuns/run_123/upstreamDatasetEvents" in call_args[0][0]


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

    def test_list_asset_events_normalizes_field_names(self, mocker):
        """Test V3 adapter normalizes asset_uri to uri."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "asset_events": [
                {
                    "asset_uri": "s3://bucket/path",
                    "source_dag_id": "producer_dag",
                    "source_run_id": "run_123",
                    "timestamp": "2024-01-01T00:00:00Z",
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

        result = adapter.list_asset_events(
            source_dag_id="producer_dag",
            source_run_id="run_123",
        )

        # Check normalization
        assert "asset_events" in result
        assert "uri" in result["asset_events"][0]
        assert "asset_uri" not in result["asset_events"][0]
        assert result["asset_events"][0]["source_dag_id"] == "producer_dag"

        # Verify endpoint and params
        call_args = mock_client.get.call_args
        assert "/api/v2/assets/events" in call_args[0][0]
        assert call_args[1]["params"]["source_dag_id"] == "producer_dag"
        assert call_args[1]["params"]["source_run_id"] == "run_123"

    def test_get_dag_run_upstream_asset_events_normalizes_field_names(self, mocker):
        """Test V3 adapter normalizes asset_uri to uri for upstream events."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "asset_events": [
                {
                    "asset_uri": "s3://bucket/input",
                    "source_dag_id": "upstream_dag",
                    "source_run_id": "upstream_run",
                }
            ],
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.get_dag_run_upstream_asset_events("consumer_dag", "run_123")

        # Check normalization
        assert "asset_events" in result
        assert "uri" in result["asset_events"][0]
        assert "asset_uri" not in result["asset_events"][0]
        assert result["asset_events"][0]["source_dag_id"] == "upstream_dag"

        # Verify endpoint
        call_args = mock_client.get.call_args
        assert "/api/v2/dags/consumer_dag/dagRuns/run_123/upstreamAssetEvents" in call_args[0][0]


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


class TestPatchMethod:
    """Tests for _patch HTTP method."""

    def test_patch_method_v2(self, mocker):
        """Test V2 adapter _patch makes correct API call."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
            token_getter=lambda: "test_token",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dag_id": "test_dag", "is_paused": True}
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter._patch("dags/test_dag", json_data={"is_paused": True})

        assert result["is_paused"] is True
        mock_client.patch.assert_called_once()
        call_args = mock_client.patch.call_args
        assert "/api/v1/dags/test_dag" in call_args[0][0]
        assert call_args[1]["json"] == {"is_paused": True}

    def test_patch_method_v3(self, mocker):
        """Test V3 adapter _patch makes correct API call."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
            token_getter=lambda: "test_token",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dag_id": "test_dag", "is_paused": False}
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter._patch("dags/test_dag", json_data={"is_paused": False})

        assert result["is_paused"] is False
        mock_client.patch.assert_called_once()
        call_args = mock_client.patch.call_args
        assert "/api/v2/dags/test_dag" in call_args[0][0]

    def test_patch_method_handles_404(self, mocker):
        """Test _patch raises NotFoundError on 404."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        with pytest.raises(NotFoundError) as exc_info:
            adapter._patch("dags/nonexistent_dag", json_data={"is_paused": True})

        assert "nonexistent_dag" in str(exc_info.value)


class TestPauseDag:
    """Tests for pause_dag and unpause_dag methods."""

    def test_pause_dag_v2(self, mocker):
        """Test V2 adapter pause_dag calls correct endpoint."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dag_id": "example_dag",
            "is_paused": True,
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.pause_dag("example_dag")

        assert result["is_paused"] is True
        call_args = mock_client.patch.call_args
        assert "/api/v1/dags/example_dag" in call_args[0][0]
        assert call_args[1]["json"] == {"is_paused": True}

    def test_unpause_dag_v2(self, mocker):
        """Test V2 adapter unpause_dag calls correct endpoint."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dag_id": "example_dag",
            "is_paused": False,
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.unpause_dag("example_dag")

        assert result["is_paused"] is False
        call_args = mock_client.patch.call_args
        assert "/api/v1/dags/example_dag" in call_args[0][0]
        assert call_args[1]["json"] == {"is_paused": False}

    def test_pause_dag_v3(self, mocker):
        """Test V3 adapter pause_dag calls correct endpoint."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dag_id": "example_dag",
            "is_paused": True,
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.pause_dag("example_dag")

        assert result["is_paused"] is True
        call_args = mock_client.patch.call_args
        assert "/api/v2/dags/example_dag" in call_args[0][0]

    def test_unpause_dag_v3(self, mocker):
        """Test V3 adapter unpause_dag calls correct endpoint."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "dag_id": "example_dag",
            "is_paused": False,
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.patch.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.unpause_dag("example_dag")

        assert result["is_paused"] is False
        call_args = mock_client.patch.call_args
        assert "/api/v2/dags/example_dag" in call_args[0][0]


class TestClearTaskInstances:
    """Tests for clear_task_instances method."""

    def test_clear_task_instances_v2(self, mocker):
        """Test V2 adapter clear_task_instances calls correct endpoint."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "task_instances": [
                {
                    "dag_id": "example_dag",
                    "dag_run_id": "manual__2024-01-01",
                    "task_id": "my_task",
                    "state": "cleared",
                }
            ]
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.clear_task_instances(
            dag_id="example_dag",
            dag_run_id="manual__2024-01-01",
            task_ids=["my_task"],
            dry_run=False,
        )

        assert "task_instances" in result
        assert result["task_instances"][0]["task_id"] == "my_task"
        call_args = mock_client.post.call_args
        assert "/api/v1/dags/example_dag/clearTaskInstances" in call_args[0][0]
        assert call_args[1]["json"]["task_ids"] == ["my_task"]
        assert call_args[1]["json"]["dag_run_id"] == "manual__2024-01-01"
        assert call_args[1]["json"]["dry_run"] is False

    def test_clear_task_instances_v2_dry_run(self, mocker):
        """Test V2 adapter clear_task_instances dry_run mode."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "task_instances": [
                {"task_id": "task1", "state": "failed"},
                {"task_id": "task2", "state": "success"},
            ]
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.clear_task_instances(
            dag_id="example_dag",
            dag_run_id="run_123",
            task_ids=["task1", "task2"],
            dry_run=True,
            only_failed=True,
        )

        assert len(result["task_instances"]) == 2
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["dry_run"] is True
        assert call_args[1]["json"]["only_failed"] is True

    def test_clear_task_instances_v2_handles_404(self, mocker):
        """Test V2 adapter handles 404 for clear_task_instances gracefully."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.0.0",  # Old version without clearTaskInstances
        )

        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.clear_task_instances(
            dag_id="example_dag",
            dag_run_id="run_123",
            task_ids=["task1"],
        )

        assert result["available"] is False
        assert "alternative" in result
        assert "2.1" in result["alternative"]

    def test_clear_task_instances_v3(self, mocker):
        """Test V3 adapter clear_task_instances calls correct endpoint."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "task_instances": [
                {
                    "dag_id": "example_dag",
                    "dag_run_id": "manual__2024-01-01",
                    "task_id": "extract",
                    "state": "cleared",
                }
            ]
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = mocker.Mock()

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.clear_task_instances(
            dag_id="example_dag",
            dag_run_id="manual__2024-01-01",
            task_ids=["extract"],
            include_downstream=True,
        )

        assert "task_instances" in result
        call_args = mock_client.post.call_args
        assert "/api/v2/dags/example_dag/clearTaskInstances" in call_args[0][0]
        assert call_args[1]["json"]["include_downstream"] is True

    def test_clear_task_instances_v3_handles_404(self, mocker):
        """Test V3 adapter handles 404 for clear_task_instances gracefully."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.0.0",
        )

        mock_response = mocker.Mock()
        mock_response.status_code = 404

        mock_client = mocker.Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.clear_task_instances(
            dag_id="nonexistent_dag",
            dag_run_id="run_123",
            task_ids=["task1"],
        )

        assert result["available"] is False
        assert "alternative" in result
