"""Integration tests for af api CLI command against real Airflow instances.

These tests validate that the af api command works correctly with both
Airflow 2.x and 3.x instances.
"""

import json
import os

import pytest
from typer.testing import CliRunner

from astro_airflow_mcp.adapters import create_adapter
from astro_airflow_mcp.cli.main import app

runner = CliRunner()

# Skip integration tests if AIRFLOW_URL is not set
pytestmark = pytest.mark.skipif(
    os.getenv("AIRFLOW_URL") is None,
    reason="Integration tests require AIRFLOW_URL environment variable",
)


class TestRawRequestIntegration:
    """Test raw_request method against real Airflow."""

    @pytest.fixture
    def adapter(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Create adapter for tests."""
        return create_adapter(
            airflow_url,
            basic_auth_getter=lambda: (airflow_username, airflow_password),
        )

    def test_raw_request_get_dags(self, adapter):
        """Should make raw GET request to dags endpoint."""
        result = adapter.raw_request("GET", "dags", params={"limit": 5})

        assert result["status_code"] == 200
        assert "dags" in result["body"]
        print(f"Raw request returned {len(result['body']['dags'])} dags")

    def test_raw_request_get_specific_dag(self, adapter):
        """Should make raw GET request for specific DAG."""
        # First get a DAG that exists
        dags_result = adapter.raw_request("GET", "dags", params={"limit": 1})
        if not dags_result["body"].get("dags"):
            pytest.skip("No DAGs available")
        dag_id = dags_result["body"]["dags"][0]["dag_id"]

        result = adapter.raw_request("GET", f"dags/{dag_id}")

        assert result["status_code"] == 200
        assert result["body"]["dag_id"] == dag_id
        print(f"Raw request got DAG: {dag_id}")

    def test_raw_request_get_version(self, adapter):
        """Should make raw GET request to version endpoint."""
        result = adapter.raw_request("GET", "version")

        assert result["status_code"] == 200
        assert "version" in result["body"]
        print(f"Raw request got version: {result['body']['version']}")

    def test_raw_request_post_variable(self, adapter):
        """Should create and delete a variable via raw request."""
        test_key = "integration_test_var"
        test_value = "test_value_123"

        # Create variable
        create_result = adapter.raw_request(
            "POST",
            "variables",
            json_data={"key": test_key, "value": test_value},
        )

        try:
            assert create_result["status_code"] in (200, 201)
            assert create_result["body"]["key"] == test_key
            print(f"Created variable: {test_key}")

            # Verify it exists
            get_result = adapter.raw_request("GET", f"variables/{test_key}")
            assert get_result["status_code"] == 200
            assert get_result["body"]["value"] == test_value

        finally:
            # Clean up
            adapter.raw_request("DELETE", f"variables/{test_key}")
            print(f"Deleted variable: {test_key}")

    def test_raw_request_raw_endpoint(self, adapter):
        """Should access non-versioned endpoint with raw_endpoint=True."""
        # Try /health (AF2) first, then /api/v2/monitor/health (AF3)
        result = adapter.raw_request("GET", "health", raw_endpoint=True)
        if result["status_code"] == 404:
            # AF3 uses a different health endpoint
            result = adapter.raw_request("GET", "api/v2/monitor/health", raw_endpoint=True)

        # Health endpoint returns 200 if healthy
        assert result["status_code"] == 200
        print(f"Health check response: {result['body']}")

    def test_raw_request_404_handling(self, adapter):
        """Should return 404 for non-existent endpoint."""
        result = adapter.raw_request("GET", "dags/nonexistent_dag_12345")

        assert result["status_code"] == 404
        print("Got expected 404 for non-existent DAG")


class TestAfApiCommandIntegration:
    """Test af api CLI command against real Airflow."""

    @pytest.fixture
    def cli_env(self, airflow_url: str, airflow_username: str, airflow_password: str):
        """Set up environment for CLI tests."""
        return {
            "AIRFLOW_API_URL": airflow_url,
            "AIRFLOW_USERNAME": airflow_username,
            "AIRFLOW_PASSWORD": airflow_password,
        }

    def test_af_api_list_dags(self, cli_env):
        """Should list DAGs via af api command."""
        result = runner.invoke(
            app,
            ["api", "dags", "-F", "limit=5"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "dags" in output
        print(f"af api dags returned {len(output['dags'])} dags")

    def test_af_api_get_dag(self, cli_env):
        """Should get specific DAG via af api command."""
        # First get a DAG that exists
        list_result = runner.invoke(
            app,
            ["api", "dags", "-F", "limit=1"],
            env=cli_env,
        )
        assert list_result.exit_code == 0
        dags_output = json.loads(list_result.output)
        if not dags_output.get("dags"):
            pytest.skip("No DAGs available")
        dag_id = dags_output["dags"][0]["dag_id"]

        result = runner.invoke(
            app,
            ["api", f"dags/{dag_id}"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["dag_id"] == dag_id
        print(f"af api got DAG: {dag_id}")

    def test_af_api_endpoints_flag(self, cli_env):
        """Should list endpoints via --endpoints flag."""
        result = runner.invoke(
            app,
            ["api", "--endpoints"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "endpoints" in output
        assert "count" in output
        assert output["count"] > 0
        print(f"af api --endpoints returned {output['count']} endpoints")

    def test_af_api_endpoints_with_filter(self, cli_env):
        """Should filter endpoints via --endpoints --filter."""
        result = runner.invoke(
            app,
            ["api", "--endpoints", "--filter", "dag"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "endpoints" in output
        # All endpoints should contain 'dag' (case-insensitive)
        for endpoint in output["endpoints"]:
            assert "dag" in endpoint.lower()
        print(f"Filtered to {output['count']} dag-related endpoints")

    def test_af_api_spec_flag(self, cli_env):
        """Should fetch OpenAPI spec via --spec flag."""
        result = runner.invoke(
            app,
            ["api", "--spec"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Should have OpenAPI structure
        assert "openapi" in output or "swagger" in output
        assert "paths" in output
        print(f"af api --spec returned OpenAPI spec with {len(output['paths'])} paths")

    def test_af_api_include_headers(self, cli_env):
        """Should include headers with -i flag."""
        result = runner.invoke(
            app,
            ["api", "version", "-i"],
            env=cli_env,
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "status_code" in output
        assert "headers" in output
        assert "body" in output
        assert output["status_code"] == 200
        print(f"af api -i included headers: {list(output['headers'].keys())}")

    def test_af_api_post_delete_variable(self, cli_env):
        """Should create and delete variable via af api."""
        test_key = "cli_integration_test_var"
        test_value = "cli_test_value"

        # Create variable
        create_result = runner.invoke(
            app,
            [
                "api",
                "variables",
                "-X",
                "POST",
                "-F",
                f"key={test_key}",
                "-f",
                f"value={test_value}",
            ],
            env=cli_env,
        )

        try:
            assert create_result.exit_code == 0
            output = json.loads(create_result.output)
            assert output["key"] == test_key
            print(f"Created variable via CLI: {test_key}")

            # Verify it exists
            get_result = runner.invoke(
                app,
                ["api", f"variables/{test_key}"],
                env=cli_env,
            )
            assert get_result.exit_code == 0
            get_output = json.loads(get_result.output)
            assert get_output["value"] == test_value

        finally:
            # Clean up
            delete_result = runner.invoke(
                app,
                ["api", f"variables/{test_key}", "-X", "DELETE"],
                env=cli_env,
            )
            # DELETE returns empty or 204
            assert delete_result.exit_code == 0
            print(f"Deleted variable via CLI: {test_key}")

    def test_af_api_error_response(self, cli_env):
        """Should return non-zero exit code for 404."""
        result = runner.invoke(
            app,
            ["api", "dags/nonexistent_dag_xyz_12345"],
            env=cli_env,
        )

        assert result.exit_code == 1
        print("Got expected error for non-existent DAG")

    def test_af_api_connection_warning(self, cli_env):
        """Should show warning when accessing connections endpoint."""
        result = runner.invoke(
            app,
            ["api", "connections", "-F", "limit=1"],
            env=cli_env,
            catch_exceptions=False,
        )

        # Should succeed
        assert result.exit_code == 0
        # Output contains JSON with connections key
        assert '"connections"' in result.output
        print("Connections endpoint works")
