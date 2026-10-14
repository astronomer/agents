"""Tests for the SessionEnd fast path (hooks/stop-kernel.py).

The hook has to finish inside Claude Code's 1.5s SessionEnd budget, so it must
reach the kernel through the PID sidecar rather than importing jupyter_client.
"""

import importlib.util
import signal
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HOOK_PATH = Path(__file__).parent.parent.parent / "hooks" / "stop-kernel.py"


@pytest.fixture
def hook():
    """Load stop-kernel.py, which isn't importable by name (hyphen, no package)."""
    spec = importlib.util.spec_from_file_location("stop_kernel", HOOK_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        pytest.fail(f"could not load {HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def kernel_files(tmp_path, hook):
    """Connection + sidecar files, with the hook pointed at them."""
    connection = tmp_path / "kernel.json"
    files = {
        "connection": connection,
        "pid": connection.with_suffix(".pid"),
        "warehouse": connection.with_suffix(".warehouse"),
    }
    with patch.object(hook, "get_kernel_connection_file", return_value=connection):
        yield files


class TestNoKernelRunning:
    def test_exits_clean_when_no_connection_file(self, hook, kernel_files):
        assert hook.main() == 0

    def test_signals_nothing_when_no_connection_file(self, hook, kernel_files):
        with patch.object(hook.os, "kill", autospec=True) as mock_kill:
            hook.main()
        mock_kill.assert_not_called()

    def test_does_not_spawn_subprocess_when_no_connection_file(
        self, hook, kernel_files
    ):
        with patch.object(hook.subprocess, "Popen", autospec=True) as mock_popen:
            hook.main()
        mock_popen.assert_not_called()


class TestKernelRunning:
    @pytest.fixture
    def running(self, kernel_files):
        kernel_files["connection"].write_text("{}")
        kernel_files["pid"].write_text("4242")
        kernel_files["warehouse"].write_text("snowflake")
        return kernel_files

    def test_sends_sigterm_to_recorded_pid(self, hook, running):
        with patch.object(hook, "_terminate", autospec=True) as mock_terminate:
            hook.main()
        mock_terminate.assert_called_once_with(4242)

    @pytest.mark.parametrize("sidecar", ["connection", "pid", "warehouse"])
    def test_removes_sidecar(self, hook, running, sidecar):
        with patch.object(hook, "_terminate", autospec=True):
            hook.main()
        assert not running[sidecar].exists()

    def test_does_not_fall_back_to_subprocess(self, hook, running):
        with (
            patch.object(hook, "_terminate", autospec=True),
            patch.object(hook.subprocess, "Popen", autospec=True) as mock_popen,
        ):
            hook.main()
        mock_popen.assert_not_called()

    @pytest.mark.parametrize(
        "pid_contents", ["", "   ", "not-a-pid"], ids=["empty", "blank", "garbage"]
    )
    def test_unreadable_pid_falls_back(self, hook, running, pid_contents):
        running["pid"].write_text(pid_contents)
        with patch.object(hook, "_spawn_detached_stop", autospec=True) as mock_spawn:
            hook.main()
        mock_spawn.assert_called_once()

    def test_missing_pid_file_falls_back(self, hook, running):
        running["pid"].unlink()
        with patch.object(hook, "_spawn_detached_stop", autospec=True) as mock_spawn:
            hook.main()
        mock_spawn.assert_called_once()

    def test_fallback_leaves_sidecars_for_the_detached_process(self, hook, running):
        """Removing them here would make `cli.py stop` find no kernel to stop."""
        running["pid"].unlink()
        with patch.object(hook, "_spawn_detached_stop", autospec=True):
            hook.main()
        assert running["connection"].exists()


class TestTerminate:
    def test_escalates_to_sigkill_when_process_survives(self, hook, monkeypatch):
        monkeypatch.setattr(hook, "GRACE_SECONDS", 0.01)
        monkeypatch.setattr(sys, "platform", "linux")
        sent = []
        with patch.object(
            hook.os, "kill", autospec=True, side_effect=lambda p, s: sent.append(s)
        ):
            hook._terminate(4242)
        assert sent[0] == signal.SIGTERM
        assert sent[-1] == signal.SIGKILL

    def test_stops_at_sigterm_when_process_exits(self, hook, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")

        def kill(pid, sig):
            if sig == 0:
                raise ProcessLookupError  # already gone

        with patch.object(
            hook.os, "kill", autospec=True, side_effect=kill
        ) as mock_kill:
            hook._terminate(4242)
        assert signal.SIGKILL not in [call.args[1] for call in mock_kill.call_args_list]

    def test_dead_pid_is_not_an_error(self, hook):
        with patch.object(
            hook.os, "kill", autospec=True, side_effect=ProcessLookupError
        ):
            hook._terminate(4242)  # must not raise

    def test_windows_does_not_poll_liveness(self, hook, monkeypatch):
        """os.kill(pid, 0) terminates on Windows, so polling it would be wrong."""
        monkeypatch.setattr(sys, "platform", "win32")
        with patch.object(hook.os, "kill", autospec=True) as mock_kill:
            hook._terminate(4242)
        assert [call.args[1] for call in mock_kill.call_args_list] == [signal.SIGTERM]
