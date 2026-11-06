#!/usr/bin/env python3
"""SessionEnd hook: shut the analysis kernel down inside the hook budget.

Claude Code gives SessionEnd hooks a shared 1.5-second budget, and a `timeout`
set on a plugin-provided hook does not raise it. Running `cli.py stop` here
would spend that whole budget on uv dependency resolution and the
`jupyter_client` import before reaching any cleanup, so this script is
stdlib-only and signals the kernel directly through the PID sidecar that
KernelManager writes at start.

Marking the hook `async` instead is not an option: under `claude -p` and the
Agent SDK, Claude Code kills async hooks still running at teardown, which is
precisely when a headless run needs its kernel reclaimed. A surviving kernel is
not merely a stray process -- the next headless run attaches to it and inherits
the previous run's variables and warehouse connection.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from config import get_kernel_connection_file  # noqa: E402  (needs sys.path above)

# Long enough for ipykernel to run its own shutdown, short enough to leave most
# of the 1.5s budget unspent.
GRACE_SECONDS = 0.4


def _terminate(pid: int) -> None:
    """Signal the kernel, escalating if it ignores SIGTERM."""
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return

    if sys.platform == "win32":
        # os.kill already maps to TerminateProcess here, and probing liveness
        # with signal 0 would terminate the process rather than report on it,
        # so there is nothing useful to poll.
        return

    deadline = time.monotonic() + GRACE_SECONDS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.02)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _spawn_detached_stop() -> None:
    """Hand off to the full shutdown path when there is no PID to signal.

    KernelManager writes no sidecar when it cannot discover the kernel's PID.
    This costs more than the budget allows, so it has to outlive the hook, and
    only a fully detached process survives a `claude -p` teardown.
    """
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(["uv", "run", str(SCRIPTS_DIR / "cli.py"), "stop"], **kwargs)
    except OSError:
        pass


def main() -> int:
    connection_file = get_kernel_connection_file()
    if not connection_file.exists():
        return 0  # No kernel. The common case, and it costs milliseconds.

    pid_file = connection_file.with_suffix(".pid")
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        # The detached fallback clears the sidecars itself; removing them here
        # would make it find no kernel and exit without doing anything.
        _spawn_detached_stop()
        return 0

    _terminate(pid)
    for path in (connection_file, pid_file, connection_file.with_suffix(".warehouse")):
        try:
            path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
