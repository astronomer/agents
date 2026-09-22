"""Jupyter kernel manager for executing Python code with persistent state."""

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from jupyter_client import KernelManager as JupyterKernelManager
from jupyter_client import BlockingKernelClient

from config import get_kernel_venv_dir, get_kernel_connection_file

DEFAULT_PACKAGES = [
    "ipykernel",
    "jupyter_client",
    "polars",
    "pandas",
    "numpy",
    "matplotlib",
    "seaborn",
    "pyyaml",
    "python-dotenv",
]


@dataclass
class ExecutionResult:
    """Result of code execution in the kernel."""

    success: bool
    output: str
    error: str | None = None
    # True when the client stopped waiting (and interrupted the cell) rather
    # than the query itself failing. Lets callers treat "I gave up" differently
    # from "the query errored".
    timed_out: bool = False


class KernelManager:
    """Manages a Jupyter kernel for Python code execution."""

    def __init__(
        self,
        venv_dir: Path | None = None,
        kernel_name: str = "astro-ai-kernel",
        packages: list[str] | None = None,
    ):
        self.venv_dir = venv_dir or get_kernel_venv_dir()
        self.kernel_name = kernel_name
        self.packages = packages or DEFAULT_PACKAGES.copy()
        self.connection_file = get_kernel_connection_file()
        self._km: JupyterKernelManager | None = None

    @property
    def python_path(self) -> Path:
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    @property
    def pid_file(self) -> Path:
        """Sidecar holding the running kernel's OS PID, used to interrupt it."""
        return self.connection_file.with_suffix(".pid")

    @property
    def _deps_marker(self) -> Path:
        """Records the package set the venv was last provisioned with."""
        return self.venv_dir / ".astro-deps-hash"

    def _deps_signature(self, packages: list[str]) -> str:
        """Stable hash of the desired packages + kernel name."""
        payload = "\n".join(sorted(packages) + [self.kernel_name])
        return hashlib.sha256(payload.encode()).hexdigest()

    def _kernel_registered(self) -> bool:
        """Whether this kernel's spec is still installed. Used to avoid skipping
        re-registration when the kernelspec was never written or got removed."""
        try:
            from jupyter_client.kernelspec import KernelSpecManager

            return self.kernel_name in KernelSpecManager().find_kernel_specs()
        except Exception:
            return False

    @property
    def is_running(self) -> bool:
        if not self.connection_file.exists():
            return False
        try:
            kc = BlockingKernelClient()
            kc.load_connection_file(str(self.connection_file))
            kc.start_channels()
            try:
                kc.wait_for_ready(timeout=2)
                return True
            except Exception:
                return False
            finally:
                kc.stop_channels()
        except Exception:
            return False

    def ensure_environment(self, extra_packages: list[str] | None = None) -> None:
        if not shutil.which("uv"):
            raise RuntimeError(
                "uv is not installed.\n"
                "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
            )

        packages = self.packages.copy()
        if extra_packages:
            packages.extend(extra_packages)

        # Skip the (slow) install + kernel registration when the existing venv
        # was already provisioned with this exact package set AND the kernelspec
        # is still registered. This makes restart/idle-kill recovery near-instant
        # instead of a full reinstall, without caching a broken environment.
        signature = self._deps_signature(packages)
        if self.venv_dir.exists() and self.python_path.exists():
            try:
                marker_ok = self._deps_marker.read_text().strip() == signature
            except OSError:
                marker_ok = False
            if marker_ok and self._kernel_registered():
                return

        if not self.venv_dir.exists():
            print(f"Creating environment at {self.venv_dir}")
            subprocess.run(
                ["uv", "venv", str(self.venv_dir), "--seed"],
                check=True,
                capture_output=True,
            )

        print("Installing packages...")
        subprocess.run(
            ["uv", "pip", "install", "--python", str(self.python_path)] + packages,
            check=True,
            capture_output=True,
        )

        # Register kernel
        registered = False
        try:
            result = subprocess.run(
                [
                    str(self.python_path),
                    "-m",
                    "ipykernel",
                    "install",
                    "--user",
                    "--name",
                    self.kernel_name,
                    "--display-name",
                    "Data Analysis Kernel",
                ],
                capture_output=True,
                timeout=30,
            )
            registered = result.returncode == 0
        except Exception:
            registered = False

        # Only record the marker once the environment is actually healthy, so a
        # failed/missing registration is never cached as "skip next time".
        if registered:
            try:
                self._deps_marker.write_text(signature)
            except OSError:
                pass

    def start(
        self,
        env_vars: dict[str, str] | None = None,
        extra_packages: list[str] | None = None,
    ) -> None:
        if self.is_running:
            print("Kernel already running")
            return

        self.ensure_environment(extra_packages=extra_packages)
        print("Starting kernel...")

        # Drop any stale PID sidecar before we start. If _write_pid can't
        # discover the new kernel's PID, the absence of a file makes _interrupt a
        # safe no-op rather than signaling a dead/reused PID.
        self.pid_file.unlink(missing_ok=True)

        self._km = JupyterKernelManager(kernel_name=self.kernel_name)

        if env_vars:
            for key, value in env_vars.items():
                os.environ[key] = value

        self._km.start_kernel(extra_arguments=["--IPKernelApp.parent_handle=0"])

        self.connection_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self._km.connection_file, self.connection_file)
        self._write_pid()

        kc = self._km.client()
        kc.start_channels()
        try:
            kc.wait_for_ready(timeout=10)
        except Exception as e:
            self.stop()
            raise RuntimeError(f"Kernel failed: {e}") from e
        finally:
            kc.stop_channels()

        # Inject idle-timeout watchdog into the kernel. The timeout is read from
        # ASTRO_KERNEL_IDLE_TIMEOUT (seconds); default 2h, 0 disables the
        # watchdog entirely. Interactive sessions have long think-gaps, so the
        # old 30-min default killed live kernels and lost their state.
        idle_timeout = self._idle_timeout_seconds()
        if idle_timeout > 0:
            self._km.client().execute(
                "import threading, time, os\n"
                f"_idle_timeout = {idle_timeout}\n"
                "_last_active = [time.time()]\n"
                "_busy = [False]\n"
                "_orig_execute = get_ipython().run_cell\n"
                "def _tracked_execute(*a, **kw):\n"
                "    _busy[0] = True\n"
                "    _last_active[0] = time.time()\n"
                "    try:\n"
                "        return _orig_execute(*a, **kw)\n"
                "    finally:\n"
                "        _busy[0] = False\n"
                "        _last_active[0] = time.time()\n"
                "get_ipython().run_cell = _tracked_execute\n"
                "def _idle_watchdog():\n"
                "    while True:\n"
                "        time.sleep(60)\n"
                # Never kill a kernel that's actively running a cell, and measure
                # idleness from when the last cell *finished*, not when it started.
                "        if _busy[0]:\n"
                "            continue\n"
                "        if time.time() - _last_active[0] > _idle_timeout:\n"
                "            _c = globals().get('_conn')\n"
                "            if _c is not None:\n"
                "                try:\n"
                "                    _c.close()\n"
                "                except Exception:\n"
                "                    pass\n"
                "            _e = globals().get('_engine')\n"
                "            if _e is not None:\n"
                "                try:\n"
                "                    _e.dispose()\n"
                "                except Exception:\n"
                "                    pass\n"
                "            os._exit(0)\n"
                "_t = threading.Thread(target=_idle_watchdog, daemon=True)\n"
                "_t.start()\n",
                silent=True,
            )

        self._km = None
        print(f"Kernel started ({self.connection_file})")

    def _idle_timeout_seconds(self) -> int:
        """Idle-watchdog timeout in seconds. Env-configurable, default 2h, 0=off."""
        raw = os.environ.get("ASTRO_KERNEL_IDLE_TIMEOUT", "7200")
        try:
            return max(0, int(raw))
        except ValueError:
            return 7200

    def _write_pid(self) -> None:
        """Persist the kernel's OS PID so a later execute() can interrupt it."""
        pid = None
        for attr in ("provisioner", "kernel"):
            pid = getattr(getattr(self._km, attr, None), "pid", None)
            if pid:
                break
        if not pid:
            return
        try:
            self.pid_file.write_text(str(pid))
        except OSError:
            pass

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text().strip())
        except (OSError, ValueError):
            return None

    def _interrupt(self) -> None:
        """Interrupt the running cell so the kernel stays responsive after a
        client-side timeout, rather than leaving a query running that blocks
        every subsequent execute(). SIGINT raises KeyboardInterrupt in the cell,
        which the DB drivers turn into a query cancel."""
        if sys.platform == "win32":
            return  # SIGINT-by-PID is unreliable on Windows; skip.
        pid = self._read_pid()
        if pid is None:
            return
        try:
            os.kill(pid, signal.SIGINT)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def stop(self) -> None:
        if not self.connection_file.exists():
            print("Kernel not running")
            return

        try:
            kc = BlockingKernelClient()
            kc.load_connection_file(str(self.connection_file))
            kc.start_channels()
            kc.shutdown()
            kc.stop_channels()
        except Exception:
            pass

        if self.connection_file.exists():
            self.connection_file.unlink()
        self.pid_file.unlink(missing_ok=True)
        print('{"message": "Kernel stopped"}')

    def execute(self, code: str, timeout: float = 120.0) -> ExecutionResult:
        if not self.connection_file.exists():
            return ExecutionResult(
                False, "", "Kernel not running. Start with: uv run scripts/cli.py start"
            )

        kc = BlockingKernelClient()
        kc.load_connection_file(str(self.connection_file))
        kc.start_channels()

        try:
            kc.wait_for_ready(timeout=5)
        except Exception as e:
            kc.stop_channels()
            return ExecutionResult(False, "", f"Kernel not responding: {e}")

        msg_id = kc.execute(code, silent=False, store_history=True)

        output_parts: list[str] = []
        error_msg: str | None = None
        status = "ok"
        deadline = time.time() + timeout
        done = False

        while time.time() < deadline and not done:
            try:
                msg = kc.get_iopub_msg(timeout=min(1.0, deadline - time.time()))
                if msg["parent_header"].get("msg_id") != msg_id:
                    continue

                msg_type = msg["msg_type"]
                content = msg["content"]

                if msg_type == "stream":
                    output_parts.append(content["text"])
                elif msg_type == "execute_result":
                    output_parts.append(content["data"].get("text/plain", ""))
                elif msg_type == "error":
                    error_msg = "\n".join(content["traceback"])
                    status = "error"
                elif msg_type == "status" and content["execution_state"] == "idle":
                    done = True
            except Exception:
                continue

        kc.stop_channels()

        if not done:
            # The client gave up waiting, but the cell is still running. Interrupt
            # it so the kernel stays responsive for the next call instead of
            # queueing behind a query we abandoned. This is "I gave up", not
            # "the query failed" -- flagged via timed_out so callers can tell.
            self._interrupt()
            return ExecutionResult(
                False,
                "".join(output_parts),
                f"Client stopped waiting after {timeout:.0f}s and interrupted the "
                f"query (it may have kept running server-side). Re-run with a "
                f"larger --timeout for known long-running queries.",
                timed_out=True,
            )

        return ExecutionResult(status == "ok", "".join(output_parts), error_msg)

    def status(self) -> dict:
        info = {
            "running": False,
            "connection_file": str(self.connection_file),
            "responsive": False,
        }
        if not self.connection_file.exists():
            return info
        info["running"] = True
        try:
            kc = BlockingKernelClient()
            kc.load_connection_file(str(self.connection_file))
            kc.start_channels()
            try:
                kc.wait_for_ready(timeout=2)
                info["responsive"] = True
            except Exception:
                pass
            finally:
                kc.stop_channels()
        except Exception:
            pass
        return info

    def install_packages(self, packages: list[str]) -> tuple[bool, str]:
        """Install additional packages into the kernel environment.

        Args:
            packages: List of package specs (e.g., ['plotly>=5.0', 'scipy'])

        Returns:
            Tuple of (success, message)
        """
        if not packages:
            return False, "No packages specified"

        if not shutil.which("uv"):
            return False, "uv is not installed"

        try:
            result = subprocess.run(
                ["uv", "pip", "install", "--python", str(self.python_path)] + packages,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return True, f"Installed: {', '.join(packages)}"
            else:
                return False, f"Failed: {result.stderr}"
        except Exception as e:
            return False, f"Error: {e}"
