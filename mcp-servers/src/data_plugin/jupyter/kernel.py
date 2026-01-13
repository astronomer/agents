"""Jupyter kernel manager for Python code execution.

This module manages a Jupyter kernel for executing Python code with persistent state.
It mirrors the architecture from ai-cli's kernel management, but implemented directly
in Python without the Go->Python IPC layer.
"""

import asyncio
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jupyter_client import KernelManager as JupyterKernelManager

from data_plugin.config import ensure_session_dir, get_kernel_venv_dir

logger = logging.getLogger(__name__)


# Default packages to install in the kernel environment
DEFAULT_PACKAGES = [
    "ipykernel",
    "jupyter_client",
    "polars",
    "pandas",
    "numpy",
    "matplotlib",
    "seaborn",
]


@dataclass
class ExecutionResult:
    """Result of code execution in the kernel."""

    success: bool
    output: str
    error: str | None = None
    execution_count: int | None = None


@dataclass
class KernelState:
    """Internal state of the kernel manager."""

    started: bool = False
    current_session_id: str | None = None
    current_session_dir: Path | None = None
    prelude_executed: bool = False


class KernelManager:
    """Manages a Jupyter kernel for Python code execution.

    This class provides:
    - Automatic environment setup using uv
    - Kernel lifecycle management (start, stop, restart)
    - Code execution with timeout handling
    - Session isolation with automatic restart on session change
    - Prelude execution for session setup
    """

    def __init__(
        self,
        venv_dir: Path | None = None,
        kernel_name: str = "astro-ai-kernel",
        packages: list[str] | None = None,
    ):
        """Initialize the kernel manager.

        Args:
            venv_dir: Path to the virtual environment. Defaults to ~/.astro/ai/kernel_venv
            kernel_name: Name for the Jupyter kernel spec
            packages: List of packages to install. Defaults to DEFAULT_PACKAGES
        """
        self.venv_dir = venv_dir or get_kernel_venv_dir()
        self.kernel_name = kernel_name
        self.packages = packages or DEFAULT_PACKAGES.copy()

        # Kernel management
        self._km: JupyterKernelManager | None = None
        self._kc: Any = None  # KernelClient
        self._state = KernelState()
        self._lock = asyncio.Lock()
        self._execution_lock = asyncio.Lock()

    @property
    def python_path(self) -> Path:
        """Get the path to the Python executable in the venv."""
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    @property
    def is_started(self) -> bool:
        """Check if the kernel is started."""
        return self._state.started and self._km is not None and self._km.is_alive()

    async def ensure_environment(self) -> None:
        """Ensure the Python environment is set up with required packages.

        This creates a virtual environment using uv and installs required packages.

        Raises:
            RuntimeError: If uv is not installed or environment setup fails
        """
        # Check if uv is available
        if not shutil.which("uv"):
            raise RuntimeError(
                "uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
            )

        # Create venv if it doesn't exist
        if not self.venv_dir.exists():
            logger.info("Creating Python environment at %s", self.venv_dir)
            proc = await asyncio.create_subprocess_exec(
                "uv",
                "venv",
                str(self.venv_dir),
                "--seed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Failed to create venv: {stderr.decode()}")

        # Check if packages are already installed
        python_exe = str(self.python_path)
        import_check = ", ".join(
            pkg.split(">")[0].split("=")[0].split("<")[0].strip() for pkg in self.packages
        )
        check_proc = await asyncio.create_subprocess_exec(
            python_exe,
            "-c",
            f"import {import_check}; print('ok')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await check_proc.communicate()

        if check_proc.returncode == 0:
            logger.debug("All required packages already installed")
            return

        # Install packages
        logger.info("Installing Python packages (may take a few minutes on first run)")
        args = ["pip", "install", "--python", python_exe] + self.packages

        proc = await asyncio.create_subprocess_exec(
            "uv",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to install packages: {stderr.decode()}")

        logger.info("Python packages installed successfully")

        # Register the kernel
        await self._register_kernel()

    async def _register_kernel(self) -> None:
        """Register the Jupyter kernel spec."""
        python_exe = str(self.python_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                python_exe,
                "-m",
                "ipykernel",
                "install",
                "--user",
                "--name",
                self.kernel_name,
                "--display-name",
                "Data Plugin Kernel",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Kernel registration timed out")
        except Exception as e:
            logger.warning("Failed to register kernel: %s", e)

    async def start(self) -> None:
        """Start the Jupyter kernel.

        Raises:
            RuntimeError: If kernel fails to start
        """
        async with self._lock:
            if self._state.started and self._km is not None and self._km.is_alive():
                logger.debug("Kernel already running")
                return

            # Ensure environment is ready
            await self.ensure_environment()

            logger.info("Starting Jupyter kernel")

            # Create kernel manager
            self._km = JupyterKernelManager(kernel_name=self.kernel_name)

            # Start kernel in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._km.start_kernel(extra_arguments=["--IPKernelApp.parent_handle=-1"]),
            )

            # Get client and start channels
            self._kc = self._km.client()
            self._kc.start_channels()

            # Wait for kernel to be ready
            try:
                await loop.run_in_executor(None, lambda: self._kc.wait_for_ready(timeout=10))
            except Exception as e:
                await self.stop()
                raise RuntimeError(f"Kernel failed to become ready: {e}") from e

            self._state.started = True
            logger.info("Jupyter kernel started successfully")

    async def stop(self) -> None:
        """Stop the Jupyter kernel."""
        async with self._lock:
            if not self._state.started:
                logger.debug("Kernel not started, nothing to stop")
                return

            logger.info("Stopping Jupyter kernel")

            if self._kc is not None:
                try:
                    self._kc.stop_channels()
                except Exception as e:
                    logger.debug("Error stopping channels: %s", e)

            if self._km is not None:
                try:
                    loop = asyncio.get_event_loop()
                    # Try graceful shutdown first
                    await loop.run_in_executor(
                        None, lambda: self._km.shutdown_kernel(now=False, restart=False)
                    )

                    # Wait a bit for graceful shutdown
                    deadline = time.time() + 2.0
                    while self._km.is_alive() and time.time() < deadline:
                        await asyncio.sleep(0.1)

                    # Force kill if still running
                    if self._km.is_alive():
                        await loop.run_in_executor(
                            None, lambda: self._km.shutdown_kernel(now=True, restart=False)
                        )
                except Exception as e:
                    logger.debug("Error during kernel shutdown: %s", e)

            self._km = None
            self._kc = None
            self._state.started = False
            self._state.prelude_executed = False
            logger.info("Jupyter kernel stopped")

    async def restart(self) -> None:
        """Restart the Jupyter kernel."""
        logger.info("Restarting Jupyter kernel")
        await self.stop()
        await asyncio.sleep(0.1)
        await self.start()

        # Re-execute prelude if we have a session
        self._state.prelude_executed = False
        if self._state.current_session_id:
            await self._execute_prelude()

        logger.info("Jupyter kernel restarted successfully")

    async def execute(self, code: str, timeout: float = 30.0) -> ExecutionResult:
        """Execute Python code in the kernel.

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds

        Returns:
            ExecutionResult with output and any errors

        Raises:
            RuntimeError: If kernel is not available
        """
        # Ensure kernel is started
        if not self.is_started:
            await self.start()

        async with self._execution_lock:
            if self._kc is None:
                raise RuntimeError("Kernel client not available")

            loop = asyncio.get_event_loop()

            # Execute code
            msg_id = await loop.run_in_executor(
                None, lambda: self._kc.execute(code, silent=False, store_history=True)
            )

            output_parts: list[str] = []
            error_msg: str | None = None
            status = "ok"
            deadline = time.time() + timeout
            execution_complete = False

            while time.time() < deadline and not execution_complete:
                remaining_time = deadline - time.time()
                if remaining_time <= 0:
                    break

                try:
                    # Get message with timeout
                    msg = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, lambda: self._kc.get_iopub_msg(timeout=min(1.0, remaining_time))
                        ),
                        timeout=min(1.0, remaining_time) + 0.5,
                    )

                    # Skip messages from other executions
                    if msg["parent_header"].get("msg_id") != msg_id:
                        continue

                    msg_type = msg["msg_type"]
                    content = msg["content"]

                    if msg_type == "stream":
                        output_parts.append(content["text"])
                    elif msg_type == "execute_result":
                        result_text = content["data"].get("text/plain", "")
                        output_parts.append(result_text)
                    elif msg_type == "error":
                        error_msg = "\n".join(content["traceback"])
                        status = "error"
                    elif msg_type == "status" and content["execution_state"] == "idle":
                        execution_complete = True

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.debug("Error getting message: %s", e)
                    continue

            if not execution_complete and time.time() >= deadline:
                return ExecutionResult(
                    success=False,
                    output="".join(output_parts),
                    error=f"Execution timed out after {timeout} seconds",
                )

            return ExecutionResult(
                success=(status == "ok"),
                output="".join(output_parts),
                error=error_msg,
            )

    async def install_packages(self, packages: list[str]) -> None:
        """Install additional Python packages.

        Args:
            packages: List of package names/specs to install

        Raises:
            RuntimeError: If installation fails
        """
        if not packages:
            return

        python_exe = str(self.python_path)
        args = ["pip", "install", "--python", python_exe] + packages

        logger.info("Installing packages: %s", ", ".join(packages))

        proc = await asyncio.create_subprocess_exec(
            "uv",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to install packages: {stderr.decode()}")

        logger.info("Packages installed successfully")

    async def set_session(self, session_id: str) -> None:
        """Set the current session, restarting kernel if session changes.

        Args:
            session_id: The session identifier
        """
        if self._state.current_session_id == session_id:
            return

        # Session changed, restart kernel for clean state
        if self._state.current_session_id is not None:
            logger.info(
                "Session changed from %s to %s, restarting kernel",
                self._state.current_session_id,
                session_id,
            )
            await self.restart()

        self._state.current_session_id = session_id
        self._state.current_session_dir = ensure_session_dir(session_id)
        self._state.prelude_executed = False

        # Execute prelude
        await self._execute_prelude()

    async def _execute_prelude(self) -> None:
        """Execute the session prelude to set up the Python environment."""
        if self._state.prelude_executed or self._state.current_session_dir is None:
            return

        from data_plugin.jupyter.prelude import render_session_prelude

        prelude_code = render_session_prelude(self._state.current_session_dir)

        try:
            result = await self.execute(prelude_code, timeout=10.0)
            if result.success:
                self._state.prelude_executed = True
                logger.debug("Session prelude executed successfully")
            else:
                logger.warning("Session prelude failed: %s", result.error)
        except Exception as e:
            logger.warning("Failed to execute session prelude: %s", e)

    def get_status(self) -> dict[str, Any]:
        """Get the current kernel status.

        Returns:
            Dictionary with kernel status information
        """
        return {
            "started": self._state.started,
            "alive": self._km.is_alive() if self._km else False,
            "session_id": self._state.current_session_id,
            "session_dir": str(self._state.current_session_dir)
            if self._state.current_session_dir
            else None,
            "prelude_executed": self._state.prelude_executed,
        }

