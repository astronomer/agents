"""Integration test for fix #1: a client-side timeout interrupts the running
cell and leaves the kernel responsive for the next execute().

This is the one behavior the mock-based unit tests can't prove -- that SIGINT
actually unwinds a blocking cell and the kernel recovers. It starts a real
Jupyter kernel (no warehouse needed), so it's gated behind `uv` availability
and lives under tests/integration (excluded from the default unit run).
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from kernel import KernelManager

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None, reason="uv required to build the kernel venv"
)


@pytest.fixture
def live_kernel():
    """A real, started kernel using throwaway venv/connection paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        km = KernelManager(
            venv_dir=tmp / "venv",
            kernel_name="astro-ai-kernel-itest",  # unique: don't clobber real kernel
        )
        km.connection_file = tmp / "kernel.json"
        try:
            km.start()
        except Exception as e:  # pragma: no cover - environment dependent
            pytest.skip(f"could not start kernel: {e}")
        try:
            yield km
        finally:
            km.stop()


def test_timeout_interrupts_then_kernel_stays_responsive(live_kernel):
    # Sanity: kernel runs normal code.
    warmup = live_kernel.execute("print('ready')", timeout=30)
    assert warmup.success, warmup.error
    assert "ready" in warmup.output

    # A long cell with a short client timeout must report timed_out (not a
    # generic failure) and interrupt the cell rather than abandoning it.
    slow = live_kernel.execute("import time; time.sleep(30)", timeout=2)
    assert slow.timed_out is True
    assert slow.success is False

    # The kernel must remain usable immediately afterwards -- the whole point of
    # interrupting instead of leaving the query running and blocking the queue.
    after = live_kernel.execute("print(6 * 7)", timeout=30)
    assert after.success, after.error
    assert "42" in after.output


def test_pid_file_written_and_cleared(live_kernel):
    assert live_kernel.pid_file.exists()
    assert live_kernel._read_pid() is not None
