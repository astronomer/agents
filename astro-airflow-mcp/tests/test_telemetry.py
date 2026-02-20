"""Tests for af CLI telemetry."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from astro_airflow_mcp import telemetry as shared_telemetry
from astro_airflow_mcp.cli import telemetry


class TestGetAnonymousId:
    """Tests for _get_anonymous_id."""

    def test_creates_new_id(self, tmp_path):
        """Test generates a new UUID when no file exists."""
        id_file = tmp_path / ".anonymous_id"
        with patch.object(shared_telemetry, "ANONYMOUS_ID_FILE", id_file):
            result = telemetry._get_anonymous_id()

        assert len(result) == 36
        assert id_file.read_text() == result

    def test_reads_existing_id(self, tmp_path):
        """Test returns existing UUID from file."""
        id_file = tmp_path / ".anonymous_id"
        existing_id = "12345678-1234-1234-1234-123456789abc"
        id_file.write_text(existing_id)

        with patch.object(shared_telemetry, "ANONYMOUS_ID_FILE", id_file):
            result = telemetry._get_anonymous_id()

        assert result == existing_id

    def test_regenerates_invalid_id(self, tmp_path):
        """Test regenerates UUID when file contains invalid data."""
        id_file = tmp_path / ".anonymous_id"
        id_file.write_text("not-a-uuid")

        with patch.object(shared_telemetry, "ANONYMOUS_ID_FILE", id_file):
            result = telemetry._get_anonymous_id()

        assert len(result) == 36
        assert result != "not-a-uuid"


class TestIsTelemetryDisabled:
    """Tests for _is_telemetry_disabled."""

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_disabled_by_env_var(self, monkeypatch, value):
        """Test telemetry disabled via environment variable."""
        monkeypatch.setenv("AF_TELEMETRY_DISABLED", value)
        assert telemetry._is_telemetry_disabled() is True

    def test_enabled_by_default(self, monkeypatch):
        """Test telemetry enabled when env var is not set."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        with patch("astro_airflow_mcp.config.loader.ConfigManager") as mock_cm:
            mock_cm.return_value.load.return_value.telemetry_disabled = False
            assert telemetry._is_telemetry_disabled() is False

    def test_disabled_by_config(self, monkeypatch):
        """Test telemetry disabled via config file."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        with patch("astro_airflow_mcp.config.loader.ConfigManager") as mock_cm:
            mock_cm.return_value.load.return_value.telemetry_disabled = True
            assert telemetry._is_telemetry_disabled() is True


class TestDetectInvocationContext:
    """Tests for _detect_invocation_context."""

    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch):
        """Clear all agent/CI env vars so tests control the environment."""
        for var in (
            "CLAUDECODE",
            "CLAUDE_CODE_ENTRYPOINT",
            "CURSOR_TRACE_ID",
            "AIDER_MODEL",
            "CONTINUE_GLOBAL_DIR",
            "GITHUB_ACTIONS",
            "GITLAB_CI",
            "JENKINS_URL",
            "CIRCLECI",
            "CI",
        ):
            monkeypatch.delenv(var, raising=False)

    def test_detects_claude_code(self, monkeypatch):
        """Test detects Claude Code agent."""
        monkeypatch.setenv("CLAUDECODE", "1")
        assert telemetry._detect_invocation_context() == ("agent", "claude-code")

    def test_detects_cursor(self, monkeypatch):
        """Test detects Cursor agent."""
        monkeypatch.setenv("CURSOR_TRACE_ID", "abc")
        assert telemetry._detect_invocation_context() == ("agent", "cursor")

    def test_detects_github_actions(self, monkeypatch):
        """Test detects GitHub Actions CI."""
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        assert telemetry._detect_invocation_context() == ("ci", "github-actions")

    def test_interactive_tty(self):
        """Test detects interactive terminal."""
        with (
            patch.object(sys.stdin, "isatty", return_value=True),
            patch.object(sys.stdout, "isatty", return_value=True),
        ):
            assert telemetry._detect_invocation_context() == ("interactive", None)

    def test_non_interactive(self):
        """Test detects non-interactive context."""
        with patch.object(sys.stdin, "isatty", return_value=False):
            assert telemetry._detect_invocation_context() == ("non-interactive", None)


class TestGetCommandFromArgv:
    """Tests for _get_command_from_argv."""

    def test_simple_command(self):
        """Test extracts simple subcommand."""
        with patch.object(sys, "argv", ["af", "dags", "list"]):
            assert telemetry._get_command_from_argv() == "dags list"

    def test_filters_flags(self):
        """Test filters out flag-style arguments."""
        with patch.object(sys, "argv", ["af", "dags", "list", "--verbose"]):
            assert telemetry._get_command_from_argv() == "dags list"

    def test_filters_config_option(self):
        """Test filters --config and its value."""
        with patch.object(sys, "argv", ["af", "--config", "/path", "dags", "list"]):
            assert telemetry._get_command_from_argv() == "dags list"

    def test_no_args_returns_root(self):
        """Test returns 'root' when no subcommand given."""
        with patch.object(sys, "argv", ["af"]):
            assert telemetry._get_command_from_argv() == "root"

    def test_option_with_equals(self):
        """Test handles --option=value format."""
        with patch.object(sys, "argv", ["af", "--config=/path", "dags", "list"]):
            assert telemetry._get_command_from_argv() == "dags list"


class TestSend:
    """Tests for _send subprocess dispatch."""

    def test_spawns_detached_subprocess(self, mocker):
        """Test spawns a fire-and-forget subprocess in normal mode."""
        mock_stdin = MagicMock()
        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_popen = mocker.patch("subprocess.Popen", return_value=mock_proc)

        telemetry._send("https://example.com/telemetry", {"event": "test"})

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["start_new_session"] is True
        assert call_kwargs["stderr"] == subprocess.DEVNULL
        mock_stdin.write.assert_called_once()
        mock_stdin.close.assert_called_once()
        mock_proc.wait.assert_not_called()

    def test_passes_payload_as_json(self, mocker):
        """Test sends correct JSON payload to subprocess stdin."""
        mock_stdin = MagicMock()
        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        body = {"source": "test", "event": "CLI Command"}
        telemetry._send("https://example.com/telemetry", body)

        written = mock_stdin.write.call_args[0][0]
        payload = json.loads(written.decode())
        assert payload["api_url"] == "https://example.com/telemetry"
        assert payload["body"] == body
        assert payload["debug"] is False

    def test_debug_mode_waits_and_inherits_stderr(self, mocker):
        """Test debug mode waits for subprocess and inherits stderr."""
        mock_stdin = MagicMock()
        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mock_popen = mocker.patch("subprocess.Popen", return_value=mock_proc)

        telemetry._send("https://example.com/telemetry", {"event": "test"}, debug=True)

        call_kwargs = mock_popen.call_args[1]
        assert call_kwargs["start_new_session"] is False
        assert call_kwargs["stderr"] is None  # inherits parent stderr
        mock_proc.wait.assert_called_once()

    def test_debug_mode_logs_request_to_stderr(self, mocker, capsys):
        """Test debug mode prints request details to stderr."""
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        body = {"source": "af-cli", "event": "CLI Command"}
        telemetry._send("https://example.com/telemetry", body, debug=True)

        captured = capsys.readouterr()
        assert "[telemetry] POST https://example.com/telemetry" in captured.err
        assert '"source": "af-cli"' in captured.err

    def test_debug_payload_includes_debug_flag(self, mocker):
        """Test debug flag is passed through in the payload."""
        mock_stdin = MagicMock()
        mock_proc = MagicMock()
        mock_proc.stdin = mock_stdin
        mocker.patch("subprocess.Popen", return_value=mock_proc)

        telemetry._send("https://example.com/telemetry", {"event": "test"}, debug=True)

        written = mock_stdin.write.call_args[0][0]
        payload = json.loads(written.decode())
        assert payload["debug"] is True

    def test_suppresses_exceptions(self, mocker):
        """Test silently handles subprocess errors."""
        mocker.patch("subprocess.Popen", side_effect=OSError("spawn failed"))
        # Should not raise
        telemetry._send("https://example.com/telemetry", {"event": "test"})


class TestSendScript:
    """Tests for _SEND_SCRIPT executed as a subprocess."""

    def test_script_posts_to_api(self):
        """Test the subprocess script sends correct HTTP request."""
        script = shared_telemetry._SEND_SCRIPT.replace(
            "__TIMEOUT__", str(shared_telemetry.TELEMETRY_TIMEOUT_SECONDS)
        )
        payload = json.dumps(
            {
                "api_url": "http://localhost:9999/telemetry",
                "body": {"source": "test", "event": "Test Event", "anonymousId": "abc"},
                "debug": True,
            }
        )

        # Run the actual script in a subprocess with a fake server that will refuse
        # the connection - we verify the script runs and reports the error in debug mode.
        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=payload.encode(),
            capture_output=True,
            timeout=10,
        )

        stderr = proc.stderr.decode()
        # Should get a connection refused or similar error in debug output
        assert "[telemetry] error:" in stderr

    def test_script_is_valid_python(self):
        """Test the subprocess script compiles without syntax errors."""
        script = shared_telemetry._SEND_SCRIPT.replace("__TIMEOUT__", "3")
        compile(script, "<send_script>", "exec")

    def test_script_silent_without_debug(self):
        """Test the subprocess script produces no output when debug is off."""
        script = shared_telemetry._SEND_SCRIPT.replace(
            "__TIMEOUT__", str(shared_telemetry.TELEMETRY_TIMEOUT_SECONDS)
        )
        payload = json.dumps(
            {
                "api_url": "http://localhost:9999/telemetry",
                "body": {"source": "test", "event": "Test Event", "anonymousId": "abc"},
                "debug": False,
            }
        )

        proc = subprocess.run(
            [sys.executable, "-c", script],
            input=payload.encode(),
            capture_output=True,
            timeout=10,
        )

        assert proc.stderr.decode() == ""


class TestTrackCommand:
    """Tests for track_command integration."""

    @pytest.fixture(autouse=True)
    def reset_tracked(self):
        """Reset the global _tracked flag between tests."""
        telemetry._tracked = False
        yield
        telemetry._tracked = False

    def test_idempotent(self, mocker, monkeypatch):
        """Test only tracks once per invocation."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.cli.telemetry._send")
        mocker.patch("astro_airflow_mcp.cli.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.cli.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._get_command_from_argv", return_value="dags list"
        )
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._detect_invocation_context",
            return_value=("interactive", None),
        )

        telemetry.track_command()
        telemetry.track_command()

        mock_send.assert_called_once()

    def test_skips_when_disabled(self, mocker, monkeypatch):
        """Test does not send when telemetry is disabled."""
        mock_send = mocker.patch("astro_airflow_mcp.cli.telemetry._send")
        mocker.patch("astro_airflow_mcp.cli.telemetry._is_telemetry_disabled", return_value=True)

        telemetry.track_command()

        mock_send.assert_not_called()

    def test_sends_correct_payload(self, mocker, monkeypatch):
        """Test sends expected event body."""
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_API_URL", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.cli.telemetry._send")
        mocker.patch("astro_airflow_mcp.cli.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.cli.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._get_command_from_argv", return_value="dags list"
        )
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._detect_invocation_context",
            return_value=("agent", "claude-code"),
        )

        telemetry.track_command()

        mock_send.assert_called_once()
        api_url, body = mock_send.call_args[0]
        assert api_url == telemetry.TELEMETRY_API_URL
        assert body["event"] == "CLI Command"
        assert body["anonymousId"] == "test-id"
        assert body["properties"]["command"] == "dags list"
        assert body["properties"]["agent"] == "claude-code"
        assert body["properties"]["context"] == "agent"

    def test_api_url_override(self, mocker, monkeypatch):
        """Test API URL can be overridden via env var."""
        monkeypatch.setenv("AF_TELEMETRY_API_URL", "https://custom.example.com/telemetry")
        monkeypatch.delenv("AF_TELEMETRY_DISABLED", raising=False)
        monkeypatch.delenv("AF_TELEMETRY_DEBUG", raising=False)
        mock_send = mocker.patch("astro_airflow_mcp.cli.telemetry._send")
        mocker.patch("astro_airflow_mcp.cli.telemetry._is_telemetry_disabled", return_value=False)
        mocker.patch("astro_airflow_mcp.cli.telemetry._get_anonymous_id", return_value="test-id")
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._get_command_from_argv", return_value="health"
        )
        mocker.patch(
            "astro_airflow_mcp.cli.telemetry._detect_invocation_context",
            return_value=("interactive", None),
        )

        telemetry.track_command()

        api_url = mock_send.call_args[0][0]
        assert api_url == "https://custom.example.com/telemetry"
