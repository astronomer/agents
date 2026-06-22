"""Tests for KernelManager lifecycle helpers (timeout, idle, deps marker, PID).

These cover the pure logic added for the kernel-wrapper fixes without needing a
live Jupyter kernel.
"""

from unittest.mock import patch

import pytest

from kernel import ExecutionResult, KernelManager


@pytest.fixture
def km(tmp_path):
    """KernelManager pointed at throwaway venv/connection paths."""
    manager = KernelManager(venv_dir=tmp_path / "venv")
    manager.connection_file = tmp_path / "kernel.json"
    return manager


class TestExecutionResult:
    def test_timed_out_defaults_false(self):
        result = ExecutionResult(success=True, output="ok")
        assert result.timed_out is False

    def test_timed_out_can_be_set(self):
        result = ExecutionResult(
            success=False, output="", error="gave up", timed_out=True
        )
        assert result.timed_out is True


class TestIdleTimeoutSeconds:
    @pytest.mark.parametrize(
        "env_value,expected",
        [
            (None, 7200),  # unset -> 2h default
            ("0", 0),  # explicit disable
            ("3600", 3600),
            ("-5", 0),  # negatives clamp to 0
            ("garbage", 7200),  # invalid -> default
        ],
        ids=["unset", "disabled", "custom", "negative", "invalid"],
    )
    def test_idle_timeout_seconds(self, km, monkeypatch, env_value, expected):
        if env_value is None:
            monkeypatch.delenv("ASTRO_KERNEL_IDLE_TIMEOUT", raising=False)
        else:
            monkeypatch.setenv("ASTRO_KERNEL_IDLE_TIMEOUT", env_value)
        assert km._idle_timeout_seconds() == expected


class TestDepsSignature:
    def test_order_insensitive(self, km):
        assert km._deps_signature(["b", "a"]) == km._deps_signature(["a", "b"])

    def test_content_sensitive(self, km):
        assert km._deps_signature(["a", "b"]) != km._deps_signature(["a", "b", "c"])

    def test_kernel_name_sensitive(self, tmp_path):
        a = KernelManager(venv_dir=tmp_path / "v", kernel_name="one")
        b = KernelManager(venv_dir=tmp_path / "v", kernel_name="two")
        assert a._deps_signature(["x"]) != b._deps_signature(["x"])


class TestDerivedPaths:
    def test_pid_file_next_to_connection_file(self, km):
        assert km.pid_file == km.connection_file.with_suffix(".pid")

    def test_deps_marker_inside_venv(self, km):
        assert km._deps_marker.parent == km.venv_dir


class TestEnsureEnvironmentSkip:
    """#4: a provisioned venv with a matching signature AND a registered
    kernelspec must not reinstall; anything less must repair."""

    def _provision(self, km, packages):
        km.python_path.parent.mkdir(parents=True, exist_ok=True)
        km.python_path.write_text("")  # pretend interpreter exists
        km._deps_marker.write_text(km._deps_signature(packages))

    def test_skips_install_when_signature_matches_and_registered(self, km):
        self._provision(km, km.packages.copy())
        with (
            patch("kernel.shutil.which", return_value="/usr/bin/uv"),
            patch.object(KernelManager, "_kernel_registered", return_value=True),
            patch("kernel.subprocess.run") as run,
        ):
            km.ensure_environment()
        run.assert_not_called()

    def test_reinstalls_when_kernelspec_missing(self, km):
        """Marker matches but the kernelspec is gone -> must re-register, not skip."""
        self._provision(km, km.packages.copy())
        with (
            patch("kernel.shutil.which", return_value="/usr/bin/uv"),
            patch.object(KernelManager, "_kernel_registered", return_value=False),
            patch("kernel.subprocess.run") as run,
        ):
            km.ensure_environment()
        assert run.called

    def test_reinstalls_when_extra_packages_change(self, km):
        self._provision(km, km.packages.copy())  # marker has no extras
        with (
            patch("kernel.shutil.which", return_value="/usr/bin/uv"),
            patch.object(KernelManager, "_kernel_registered", return_value=True),
            patch("kernel.subprocess.run") as run,
        ):
            km.ensure_environment(extra_packages=["snowflake-connector-python"])
        assert run.called

    def test_writes_marker_after_successful_registration(self, km):
        with (
            patch("kernel.shutil.which", return_value="/usr/bin/uv"),
            patch("kernel.subprocess.run") as run,
        ):
            run.return_value.returncode = 0  # registration succeeds
            km.venv_dir.mkdir(parents=True, exist_ok=True)
            km.ensure_environment()
        assert km._deps_marker.read_text() == km._deps_signature(km.packages.copy())

    def test_marker_not_written_when_registration_fails(self, km):
        with (
            patch("kernel.shutil.which", return_value="/usr/bin/uv"),
            patch("kernel.subprocess.run") as run,
        ):
            run.return_value.returncode = 1  # ipykernel install failed
            km.venv_dir.mkdir(parents=True, exist_ok=True)
            km.ensure_environment()
        assert not km._deps_marker.exists()

    def test_missing_uv_raises(self, km):
        with patch("kernel.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="uv is not installed"):
                km.ensure_environment()


class TestInterruptGuards:
    def test_read_pid_missing_file_returns_none(self, km):
        assert km._read_pid() is None

    def test_read_pid_roundtrip(self, km):
        km.pid_file.parent.mkdir(parents=True, exist_ok=True)
        km.pid_file.write_text("4242")
        assert km._read_pid() == 4242

    def test_read_pid_garbage_returns_none(self, km):
        km.pid_file.parent.mkdir(parents=True, exist_ok=True)
        km.pid_file.write_text("not-a-pid")
        assert km._read_pid() is None

    def test_interrupt_noop_without_pid(self, km):
        # No pid file -> must not raise and must not signal anything.
        with patch("kernel.os.kill") as kill:
            km._interrupt()
        kill.assert_not_called()

    def test_interrupt_signals_pid(self, km):
        km.pid_file.parent.mkdir(parents=True, exist_ok=True)
        km.pid_file.write_text("4242")
        with patch("kernel.sys.platform", "darwin"), patch("kernel.os.kill") as kill:
            km._interrupt()
        kill.assert_called_once()
        assert kill.call_args.args[0] == 4242

    def test_interrupt_skipped_on_windows(self, km):
        km.pid_file.parent.mkdir(parents=True, exist_ok=True)
        km.pid_file.write_text("4242")
        with patch("kernel.sys.platform", "win32"), patch("kernel.os.kill") as kill:
            km._interrupt()
        kill.assert_not_called()

    def test_interrupt_swallows_dead_pid(self, km):
        km.pid_file.parent.mkdir(parents=True, exist_ok=True)
        km.pid_file.write_text("4242")
        with (
            patch("kernel.sys.platform", "darwin"),
            patch("kernel.os.kill", side_effect=ProcessLookupError),
        ):
            km._interrupt()  # must not propagate
