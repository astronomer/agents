"""Tests for af api CLI command."""

import json

import pytest
from typer.testing import CliRunner

from astro_airflow_mcp.adapters import AirflowV2Adapter, AirflowV3Adapter
from astro_airflow_mcp.cli.api import parse_field, parse_field_value
from astro_airflow_mcp.cli.main import app

runner = CliRunner()


class TestParseFieldValue:
    """Tests for parse_field_value function."""

    def test_null_conversion(self):
        """Test null string converts to None."""
        assert parse_field_value("null") is None

    def test_true_conversion(self):
        """Test true string converts to True."""
        assert parse_field_value("true") is True

    def test_false_conversion(self):
        """Test false string converts to False."""
        assert parse_field_value("false") is False

    def test_integer_conversion(self):
        """Test integer string converts to int."""
        assert parse_field_value("42") == 42
        assert parse_field_value("-10") == -10
        assert parse_field_value("0") == 0

    def test_float_conversion(self):
        """Test float string converts to float."""
        assert parse_field_value("3.14") == 3.14
        assert parse_field_value("-2.5") == -2.5

    def test_string_passthrough(self):
        """Test non-convertible strings are kept as-is."""
        assert parse_field_value("hello") == "hello"
        assert parse_field_value("foo bar") == "foo bar"

    def test_file_read(self, tmp_path):
        """Test @filename reads file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("file content")
        assert parse_field_value(f"@{test_file}") == "file content"


class TestParseField:
    """Tests for parse_field function."""

    def test_basic_parsing(self):
        """Test basic key=value parsing."""
        key, value = parse_field("name=test")
        assert key == "name"
        assert value == "test"

    def test_typed_conversion(self):
        """Test typed field conversion."""
        key, value = parse_field("count=10")
        assert key == "count"
        assert value == 10

    def test_raw_mode(self):
        """Test raw mode keeps strings."""
        key, value = parse_field("count=10", raw=True)
        assert key == "count"
        assert value == "10"

    def test_value_with_equals(self):
        """Test values containing equals sign."""
        key, value = parse_field("expr=a=b=c", raw=True)
        assert key == "expr"
        assert value == "a=b=c"

    def test_missing_equals_raises(self):
        """Test missing equals raises error."""
        import typer

        with pytest.raises(typer.BadParameter):
            parse_field("no_equals")


class TestRawRequest:
    """Tests for raw_request method on adapters."""

    def test_raw_request_get(self, mocker):
        """Test raw_request with GET method."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": [], "total_entries": 0}
        mock_response.text = '{"dags": [], "total_entries": 0}'
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.raw_request("GET", "dags")

        assert result["status_code"] == 200
        assert result["body"] == {"dags": [], "total_entries": 0}
        mock_client.request.assert_called_once()
        call_args = mock_client.request.call_args
        assert call_args[1]["method"] == "GET"
        assert "http://localhost:8080/api/v1/dags" in call_args[1]["url"]

    def test_raw_request_post_with_json(self, mocker):
        """Test raw_request with POST method and JSON body."""
        adapter = AirflowV3Adapter(
            "http://localhost:8080",
            "3.1.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"key": "test", "value": "value"}
        mock_response.text = '{"key": "test", "value": "value"}'
        mock_response.status_code = 201
        mock_response.headers = {"content-type": "application/json"}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.raw_request(
            "POST", "variables", json_data={"key": "test", "value": "value"}
        )

        assert result["status_code"] == 201
        call_args = mock_client.request.call_args
        assert call_args[1]["method"] == "POST"
        assert call_args[1]["json"] == {"key": "test", "value": "value"}
        # V3 uses /api/v2
        assert "/api/v2/variables" in call_args[1]["url"]

    def test_raw_request_with_params(self, mocker):
        """Test raw_request with query parameters."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"dags": [], "total_entries": 0}
        mock_response.text = '{"dags": [], "total_entries": 0}'
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        adapter.raw_request("GET", "dags", params={"limit": 10, "offset": 0})

        call_args = mock_client.request.call_args
        assert call_args[1]["params"] == {"limit": 10, "offset": 0}

    def test_raw_request_raw_endpoint(self, mocker):
        """Test raw_request with raw_endpoint=True bypasses version prefix."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.text = '{"status": "healthy"}'
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        adapter.raw_request("GET", "health", raw_endpoint=True)

        call_args = mock_client.request.call_args
        # Should NOT have /api/v1 prefix
        assert call_args[1]["url"] == "http://localhost:8080/health"

    def test_raw_request_strips_leading_slash(self, mocker):
        """Test raw_request strips leading slash from endpoint."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {}
        mock_response.text = "{}"
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        # Both should result in same URL
        adapter.raw_request("GET", "/dags")
        call_args = mock_client.request.call_args
        assert call_args[1]["url"] == "http://localhost:8080/api/v1/dags"

    def test_raw_request_with_custom_headers(self, mocker):
        """Test raw_request includes custom headers."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
            token_getter=lambda: "test_token",
        )

        mock_response = mocker.Mock()
        mock_response.json.return_value = {}
        mock_response.text = "{}"
        mock_response.status_code = 200
        mock_response.headers = {}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        adapter.raw_request("GET", "dags", headers={"X-Custom": "value"})

        call_args = mock_client.request.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["X-Custom"] == "value"

    def test_raw_request_empty_response(self, mocker):
        """Test raw_request handles empty response body."""
        adapter = AirflowV2Adapter(
            "http://localhost:8080",
            "2.9.0",
        )

        mock_response = mocker.Mock()
        mock_response.text = ""
        mock_response.status_code = 204
        mock_response.headers = {}

        mock_client = mocker.Mock()
        mock_client.request.return_value = mock_response
        mock_client.__enter__ = mocker.Mock(return_value=mock_client)
        mock_client.__exit__ = mocker.Mock(return_value=False)

        mocker.patch("httpx.Client", return_value=mock_client)

        result = adapter.raw_request("DELETE", "variables/test")

        assert result["status_code"] == 204
        assert result["body"] is None


class TestApiCommand:
    """Tests for af api CLI command."""

    def test_api_no_endpoint_shows_error(self, mocker):
        """Test api command requires endpoint or --spec."""
        result = runner.invoke(app, ["api"])
        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_api_spec_flag(self, mocker):
        """Test api --spec fetches OpenAPI spec."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {"openapi": "3.0.0", "paths": {}},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "--spec"])

        assert result.exit_code == 0
        # OpenAPI spec is at root /openapi.json, not under API version path
        mock_adapter.raw_request.assert_called_once_with("GET", "openapi.json", raw_endpoint=True)
        output = json.loads(result.output)
        assert output["openapi"] == "3.0.0"

    def test_api_endpoints_flag(self, mocker):
        """Test api --endpoints lists available endpoints."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {
                "openapi": "3.0.0",
                "paths": {
                    "/api/v2/dags": {},
                    "/api/v2/variables": {},
                    "/api/v2/connections": {},
                },
            },
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "--endpoints"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "endpoints" in output
        assert len(output["endpoints"]) == 3
        assert output["count"] == 3
        assert "/api/v2/dags" in output["endpoints"]

    def test_api_endpoints_with_filter(self, mocker):
        """Test api --endpoints --filter filters endpoints."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {
                "openapi": "3.0.0",
                "paths": {
                    "/api/v2/dags": {},
                    "/api/v2/variables": {},
                    "/api/v2/variables/{key}": {},
                    "/api/v2/connections": {},
                },
            },
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "--endpoints", "--filter", "variable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["count"] == 2
        assert all("variable" in ep.lower() for ep in output["endpoints"])

    def test_api_get_dags(self, mocker):
        """Test basic GET request to dags endpoint."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {"dags": [], "total_entries": 0},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "dags"])

        assert result.exit_code == 0
        mock_adapter.raw_request.assert_called_once_with(
            method="GET",
            endpoint="dags",
            params=None,
            json_data=None,
            headers=None,
            raw_endpoint=False,
        )

    def test_api_get_with_query_params(self, mocker):
        """Test GET request with query parameters via -F."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {"dags": []},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "dags", "-F", "limit=10", "-F", "only_active=true"])

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["params"] == {"limit": 10, "only_active": True}

    def test_api_post_with_fields(self, mocker):
        """Test POST request with fields converted to JSON body."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 201,
            "headers": {},
            "body": {"key": "test", "value": "hello"},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(
            app, ["api", "variables", "-X", "POST", "-F", "key=test", "-f", "value=hello"]
        )

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"] == {"key": "test", "value": "hello"}
        assert call_kwargs["params"] is None

    def test_api_post_with_body(self, mocker):
        """Test POST request with explicit JSON body."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 201,
            "headers": {},
            "body": {"key": "test"},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(
            app, ["api", "variables", "-X", "POST", "--body", '{"key": "test", "value": "v"}']
        )

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["json_data"] == {"key": "test", "value": "v"}

    def test_api_delete(self, mocker):
        """Test DELETE request."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 204,
            "headers": {},
            "body": None,
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "variables/test", "-X", "DELETE"])

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["method"] == "DELETE"

    def test_api_raw_endpoint(self, mocker):
        """Test --raw flag bypasses API version prefix."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {"status": "healthy"},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "health", "--raw"])

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["raw_endpoint"] is True

    def test_api_include_headers(self, mocker):
        """Test -i flag includes status and headers in output."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body": {"dags": []},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "dags", "-i"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "status_code" in output
        assert output["status_code"] == 200
        assert "headers" in output
        assert "body" in output

    def test_api_custom_header(self, mocker):
        """Test custom header via -H."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 200,
            "headers": {},
            "body": {},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "dags", "-H", "X-Custom: my-value"])

        assert result.exit_code == 0
        call_kwargs = mock_adapter.raw_request.call_args[1]
        assert call_kwargs["headers"] == {"X-Custom": "my-value"}

    def test_api_error_response(self, mocker):
        """Test error response returns non-zero exit code."""
        mock_adapter = mocker.Mock()
        mock_adapter.raw_request.return_value = {
            "status_code": 404,
            "headers": {},
            "body": {"detail": "Not Found"},
        }
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mock_adapter)

        result = runner.invoke(app, ["api", "nonexistent"])

        assert result.exit_code == 1

    def test_api_invalid_method(self, mocker):
        """Test invalid HTTP method shows error."""
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mocker.Mock())

        result = runner.invoke(app, ["api", "dags", "-X", "INVALID"])

        assert result.exit_code == 1
        assert "Invalid method" in result.output

    def test_api_invalid_json_body(self, mocker):
        """Test invalid JSON body shows error."""
        mocker.patch("astro_airflow_mcp.cli.api.get_adapter", return_value=mocker.Mock())

        result = runner.invoke(app, ["api", "dags", "-X", "POST", "--body", "not json"])

        assert result.exit_code == 1
        assert "Invalid JSON" in result.output
