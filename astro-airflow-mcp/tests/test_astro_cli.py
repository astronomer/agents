"""Tests for Astro CLI integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from astro_airflow_mcp.astro.astro_cli import (
    AstroCli,
    AstroCliError,
    AstroCliNotAuthenticatedError,
    AstroCliNotInstalledError,
    AstroDeployment,
)


class TestAstroDeployment:
    """Tests for AstroDeployment dataclass."""

    def test_from_inspect_yaml_basic(self):
        """Test creating deployment from inspect YAML output."""
        data = {
            "deployment": {
                "configuration": {
                    "name": "my-deployment",
                    "workspace_name": "my-workspace",
                },
                "metadata": {
                    "deployment_id": "dep-123",
                    "workspace_id": "ws-456",
                    "status": "HEALTHY",
                    "webserver_url": "xyz123.astronomer.run/abc456",
                    "airflow_version": "3.1.6",
                    "release_name": "my-deployment-7890",
                },
            }
        }
        deployment = AstroDeployment.from_inspect_yaml(data)

        assert deployment.id == "dep-123"
        assert deployment.name == "my-deployment"
        assert deployment.workspace_id == "ws-456"
        assert deployment.workspace_name == "my-workspace"
        assert deployment.status == "HEALTHY"
        assert deployment.airflow_api_url == "https://xyz123.astronomer.run/abc456"
        assert deployment.airflow_version == "3.1.6"
        assert deployment.release_name == "my-deployment-7890"

    def test_from_inspect_yaml_with_https(self):
        """Test that https:// is not duplicated if already present."""
        data = {
            "deployment": {
                "configuration": {"name": "test"},
                "metadata": {
                    "deployment_id": "dep-123",
                    "webserver_url": "https://already-https.com",
                },
            }
        }
        deployment = AstroDeployment.from_inspect_yaml(data)
        assert deployment.airflow_api_url == "https://already-https.com"

    def test_from_inspect_yaml_minimal(self):
        """Test with minimal data."""
        data = {
            "deployment": {
                "configuration": {},
                "metadata": {},
            }
        }
        deployment = AstroDeployment.from_inspect_yaml(data)

        assert deployment.id == ""
        assert deployment.name == ""
        assert deployment.status == "UNKNOWN"
        assert deployment.airflow_api_url == ""


class TestAstroCliInstallation:
    """Tests for CLI installation detection."""

    def test_is_installed_when_found(self):
        """Test is_installed returns True when CLI found."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            cli = AstroCli()
            assert cli.is_installed() is True

    def test_is_installed_when_not_found(self):
        """Test is_installed returns False when CLI not found."""
        with patch("shutil.which", return_value=None):
            cli = AstroCli()
            assert cli.is_installed() is False

    def test_run_command_raises_when_not_installed(self):
        """Test _run_command raises when CLI not installed."""
        with patch("shutil.which", return_value=None):
            cli = AstroCli()
            with pytest.raises(AstroCliNotInstalledError, match="not installed"):
                cli._run_command(["version"])


class TestAstroCliAuthentication:
    """Tests for authentication detection."""

    @pytest.fixture
    def mock_cli(self):
        """Create CLI with mocked astro path."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            yield AstroCli()

    @pytest.mark.parametrize(
        "error_message",
        [
            # Actual error from `astro` CLI when not logged in
            "no context set, have you authenticated to Astro? Run astro login and try again",
            # Partial matches
            "no context set",
            "Run astro login",
        ],
    )
    def test_run_command_detects_auth_errors(self, mock_cli, error_message):
        """Test _run_command detects auth error from astro CLI."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = error_message

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(AstroCliNotAuthenticatedError, match="Not authenticated"),
        ):
            mock_cli._run_command(["deployment", "list"])

    def test_run_command_success(self, mock_cli):
        """Test _run_command returns result on success."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "some output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = mock_cli._run_command(["context", "list"])
            assert result.returncode == 0
            assert result.stdout == "some output"


class TestTableParsing:
    """Tests for table output parsing."""

    @pytest.fixture
    def mock_cli(self):
        """Create CLI with mocked astro path."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            yield AstroCli()

    def test_parse_table_output_basic(self, mock_cli):
        """Test parsing basic table output."""
        output = """ NAME     NAMESPACE                    DEPLOYMENT ID
 test     physical-refraction-2416     cml0a458406f401jkva87iahu"""

        result = mock_cli._parse_table_output(output)
        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert result[0]["namespace"] == "physical-refraction-2416"
        assert result[0]["deployment_id"] == "cml0a458406f401jkva87iahu"

    def test_parse_table_output_multi_word_headers(self, mock_cli):
        """Test parsing table with multi-word headers."""
        output = """ NAME     CLOUD PROVIDER     DEPLOYMENT ID
 test     AZURE              abc123"""

        result = mock_cli._parse_table_output(output)
        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert result[0]["cloud_provider"] == "AZURE"
        assert result[0]["deployment_id"] == "abc123"

    def test_parse_table_output_multiple_rows(self, mock_cli):
        """Test parsing table with multiple rows."""
        output = """ NAME     DEPLOYMENT ID
 dep1     id1
 dep2     id2
 dep3     id3"""

        result = mock_cli._parse_table_output(output)
        assert len(result) == 3
        assert result[0]["name"] == "dep1"
        assert result[1]["name"] == "dep2"
        assert result[2]["name"] == "dep3"

    def test_parse_table_output_empty(self, mock_cli):
        """Test parsing empty table."""
        result = mock_cli._parse_table_output("")
        assert result == []

    def test_parse_table_output_header_only(self, mock_cli):
        """Test parsing table with only headers."""
        output = " NAME     DEPLOYMENT ID"
        result = mock_cli._parse_table_output(output)
        assert result == []


class TestAstroCliContext:
    """Tests for context management."""

    @pytest.fixture
    def mock_cli(self):
        """Create CLI with mocked astro path."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            yield AstroCli()

    def test_get_context_returns_current(self, mock_cli):
        """Test get_context returns the current context domain."""
        output = """   DOMAIN                    LAST USED WORKSPACE
 * cloud.astronomer.io       my-workspace
   dev.astronomer.io         other-workspace"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            assert mock_cli.get_context() == "cloud.astronomer.io"

    def test_get_context_returns_none_on_failure(self, mock_cli):
        """Test get_context returns None when command fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            assert mock_cli.get_context() is None


class TestAstroCliDeployments:
    """Tests for deployment listing and inspection."""

    @pytest.fixture
    def mock_cli(self):
        """Create CLI with mocked astro path."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            yield AstroCli()

    def test_list_deployments_success(self, mock_cli):
        """Test list_deployments returns deployment list."""
        output = """ NAME     NAMESPACE     DEPLOYMENT ID
 dep-1    ns-1          id-1
 dep-2    ns-2          id-2"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = mock_cli.list_deployments()
            assert len(result) == 2
            assert result[0]["name"] == "dep-1"
            assert result[0]["deployment_id"] == "id-1"

    def test_list_deployments_all_workspaces(self, mock_cli):
        """Test list_deployments passes --all flag."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = " NAME     DEPLOYMENT ID\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            mock_cli.list_deployments(all_workspaces=True)
            call_args = mock_run.call_args[0][0]
            assert "--all" in call_args

    def test_list_deployments_error(self, mock_cli):
        """Test list_deployments raises on error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(AstroCliError, match="Failed to list"),
        ):
            mock_cli.list_deployments()

    def test_list_deployments_auth_error(self, mock_cli):
        """Test list_deployments raises AstroCliNotAuthenticatedError for auth issues."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = (
            "Error: failed to find a valid workspace: failed to get current Workspace: "
            "no context set, have you authenticated to Astro or Astro Private Cloud? "
            "Run astro login and try again"
        )

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(AstroCliNotAuthenticatedError, match="Not authenticated"),
        ):
            mock_cli.list_deployments()

    def test_inspect_deployment_success(self, mock_cli):
        """Test inspect_deployment returns AstroDeployment."""
        yaml_output = """deployment:
    configuration:
        name: my-dep
        workspace_name: my-workspace
    metadata:
        deployment_id: dep-123
        workspace_id: ws-456
        status: HEALTHY
        webserver_url: example.astronomer.run/abc
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = yaml_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            deployment = mock_cli.inspect_deployment("dep-123")
            assert isinstance(deployment, AstroDeployment)
            assert deployment.id == "dep-123"
            assert deployment.name == "my-dep"
            assert deployment.airflow_api_url == "https://example.astronomer.run/abc"

    def test_inspect_deployment_with_workspace(self, mock_cli):
        """Test inspect_deployment passes workspace_id."""
        yaml_output = """deployment:
    configuration:
        name: test
    metadata:
        deployment_id: x
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = yaml_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            mock_cli.inspect_deployment("dep-123", workspace_id="ws-123")
            call_args = mock_run.call_args[0][0]
            assert "--workspace-id" in call_args
            assert "ws-123" in call_args


class TestAstroCliTokens:
    """Tests for token management."""

    @pytest.fixture
    def mock_cli(self):
        """Create CLI with mocked astro path."""
        with patch("shutil.which", return_value="/usr/local/bin/astro"):
            yield AstroCli()

    def test_list_deployment_tokens_success(self, mock_cli):
        """Test list_deployment_tokens returns token list."""
        output = """ NAME          ID        ROLE
 token-1       tok-1     DEPLOYMENT_ADMIN
 token-2       tok-2     DEPLOYMENT_VIEWER"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = mock_cli.list_deployment_tokens("dep-123")
            assert len(result) == 2
            assert result[0]["name"] == "token-1"
            assert result[1]["name"] == "token-2"

    def test_token_exists_true(self, mock_cli):
        """Test token_exists returns True when token found."""
        output = """ NAME               ID
 af-cli-discover    tok-1
 other-token        tok-2"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            assert mock_cli.token_exists("dep-123", "af-cli-discover") is True

    def test_token_exists_false(self, mock_cli):
        """Test token_exists returns False when token not found."""
        output = """ NAME           ID
 other-token    tok-1"""

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            assert mock_cli.token_exists("dep-123", "af-cli-discover") is False

    def test_create_deployment_token_jwt(self, mock_cli):
        """Test create_deployment_token extracts JWT token."""
        jwt_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"Token created successfully:\n{jwt_token}\n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            token = mock_cli.create_deployment_token("dep-123", "my-token")
            assert token == jwt_token

    def test_create_deployment_token_long_string(self, mock_cli):
        """Test create_deployment_token extracts long token string."""
        long_token = "a" * 150
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = f"Token: {long_token}"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            token = mock_cli.create_deployment_token("dep-123", "my-token")
            assert token == long_token

    def test_create_deployment_token_error(self, mock_cli):
        """Test create_deployment_token raises on error."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Failed to create token"

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(AstroCliError, match="Failed to create"),
        ):
            mock_cli.create_deployment_token("dep-123", "my-token")


class TestInstanceNameGeneration:
    """Tests for instance name generation from deployments."""

    def test_basic_name_generation(self):
        """Test basic name generation."""
        from astro_airflow_mcp.discovery.astro import _generate_instance_name

        dep = AstroDeployment(
            id="dep-1",
            name="my-deployment",
            workspace_id="ws-1",
            workspace_name="My Workspace",
            airflow_api_url="https://example.com/api/v2",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "my-workspace-my-deployment"

    def test_name_generation_normalizes_special_chars(self):
        """Test that special characters are normalized."""
        from astro_airflow_mcp.discovery.astro import _generate_instance_name

        dep = AstroDeployment(
            id="dep-1",
            name="My_Deployment (Test)",
            workspace_id="ws-1",
            workspace_name="Dev & Staging",
            airflow_api_url="https://example.com/api/v2",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "dev-staging-my-deployment-test"

    def test_name_generation_empty_workspace(self):
        """Test name generation when workspace name is empty."""
        from astro_airflow_mcp.discovery.astro import _generate_instance_name

        dep = AstroDeployment(
            id="dep-1",
            name="standalone",
            workspace_id="ws-1",
            workspace_name="",
            airflow_api_url="https://example.com/api/v2",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "standalone"

    def test_name_generation_strips_leading_trailing_hyphens(self):
        """Test that leading/trailing hyphens are stripped."""
        from astro_airflow_mcp.discovery.astro import _generate_instance_name

        dep = AstroDeployment(
            id="dep-1",
            name="---test---",
            workspace_id="ws-1",
            workspace_name="---workspace---",
            airflow_api_url="https://example.com/api/v2",
            status="HEALTHY",
        )
        assert _generate_instance_name(dep) == "workspace-test"
