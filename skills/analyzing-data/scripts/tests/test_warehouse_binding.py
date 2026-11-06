"""Tests for the kernel's warehouse binding.

The prelude runs once at start, so a kernel stays connected to whichever
warehouse it started with. `start -w <other>` used to return silently on a
running kernel, leaving later queries pointed at the original warehouse.
"""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

import cli
import kernel as kernel_module
from kernel import KernelManager


@pytest.fixture
def km(tmp_path):
    manager = KernelManager(venv_dir=tmp_path / "venv")
    manager.connection_file = tmp_path / "kernel.json"
    return manager


@pytest.fixture
def no_zmq():
    """Keep stop()/status() off the network: the connection file is a stub."""
    with patch.object(
        kernel_module, "BlockingKernelClient", autospec=True
    ) as mock_client:
        yield mock_client


class TestWarehouseSidecar:
    def test_unset_when_never_recorded(self, km):
        assert km.bound_warehouse is None

    def test_round_trips(self, km):
        km.record_warehouse("snowflake_prod")
        assert km.bound_warehouse == "snowflake_prod"

    def test_sits_beside_the_connection_file(self, km):
        km.record_warehouse("pg")
        assert km.warehouse_file == km.connection_file.with_suffix(".warehouse")

    @pytest.mark.parametrize(
        "contents,expected",
        [("pg\n", "pg"), ("  pg  ", "pg"), ("", None)],
        ids=["trailing-newline", "padded", "empty"],
    )
    def test_reads_trimmed(self, km, contents, expected):
        km.warehouse_file.write_text(contents)
        assert km.bound_warehouse == expected

    def test_cleared_on_stop(self, km, no_zmq):
        km.connection_file.write_text("{}")
        km.record_warehouse("pg")
        km.stop()
        assert km.bound_warehouse is None


class TestStartWarehouseGuard:
    """`start -w` must not silently no-op against a differently bound kernel."""

    @staticmethod
    def _run(args, running, bound):
        manager = KernelManager()
        with (
            patch.object(type(manager), "is_running", property(lambda self: running)),
            patch.object(
                type(manager), "bound_warehouse", property(lambda self: bound)
            ),
            patch.object(cli, "KernelManager", return_value=manager),
            patch.object(cli, "check_uv_installed"),
        ):
            return CliRunner().invoke(cli.start, args)

    def test_errors_when_bound_to_another_warehouse(self):
        result = self._run(["-w", "pg"], running=True, bound="snowflake")
        assert result.exit_code == 1
        assert "already connected to warehouse 'snowflake'" in result.output

    def test_error_names_the_command_that_switches(self):
        result = self._run(["-w", "pg"], running=True, bound="snowflake")
        assert "restart -w pg" in result.output

    def test_quiet_when_warehouse_matches(self):
        result = self._run(["-w", "pg"], running=True, bound="pg")
        assert result.exit_code == 0
        assert "already running" in result.output

    def test_quiet_when_no_warehouse_requested(self):
        result = self._run([], running=True, bound="snowflake")
        assert result.exit_code == 0

    def test_reports_binding_when_already_running(self):
        result = self._run([], running=True, bound="snowflake")
        assert "snowflake" in result.output

    def test_tolerates_kernel_started_before_binding_was_tracked(self):
        """No sidecar means an older kernel; refusing would strand the user."""
        result = self._run(["-w", "pg"], running=True, bound=None)
        assert result.exit_code == 0


class TestStatusReportsBinding:
    def test_status_includes_warehouse(self, km, no_zmq):
        km.connection_file.write_text("{}")
        km.record_warehouse("snowflake")
        assert km.status()["warehouse"] == "snowflake"

    def test_status_warehouse_none_when_unbound(self, km, no_zmq):
        km.connection_file.write_text("{}")
        assert km.status()["warehouse"] is None
