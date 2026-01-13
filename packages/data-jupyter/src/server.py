"""FastMCP server for Jupyter kernel code execution.

This server exposes tools for Python code execution, package installation,
and kernel lifecycle management via the Model Context Protocol (MCP).

Usage:
    python -m data_jupyter.server

Or via the installed script:
    data-jupyter
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .kernel import KernelManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global kernel manager instance
_kernel_manager: KernelManager | None = None


def get_kernel_manager() -> KernelManager:
    """Get or create the global kernel manager instance."""
    global _kernel_manager
    if _kernel_manager is None:
        _kernel_manager = KernelManager()
    return _kernel_manager


# Create the FastMCP server
mcp = FastMCP("data-jupyter")


@mcp.tool()
async def execute_python(
    code: str,
    timeout: float = 30.0,
    session_id: str | None = None,
) -> str:
    """Execute Python code in the Jupyter kernel.

    The kernel maintains state across executions - variables and imports persist.
    Use this for data analysis, visualization, and computation tasks.

    Pre-installed packages: polars, pandas, numpy, matplotlib, seaborn

    Args:
        code: Python code to execute. Keep code blocks small (10-15 lines)
              for better error handling and user experience.
        timeout: Optional execution timeout in seconds (default: 30, max: 300)
        session_id: Optional session identifier for state isolation

    Returns:
        Execution output or error message
    """
    kernel_manager = get_kernel_manager()

    # Set session if provided
    if session_id:
        await kernel_manager.set_session(session_id)

    # Clamp timeout
    timeout = max(1.0, min(300.0, timeout))

    result = await kernel_manager.execute(code, timeout=timeout)

    if result.success:
        return result.output if result.output else "(no output)"
    else:
        error_msg = result.error or "Execution failed"
        if result.output:
            return f"Output:\n{result.output}\n\nError:\n{error_msg}"
        return f"Error:\n{error_msg}"


@mcp.tool()
async def install_packages(packages: list[str]) -> str:
    """Install additional Python packages in the kernel environment.

    Supports version specs like 'plotly>=5.0' or 'numpy==1.24.0'.
    Packages are installed immediately and available for import in subsequent code.

    Args:
        packages: List of package names to install.
                  Can include version specs (e.g., ['plotly>=5.0', 'scipy==1.11.0'])

    Returns:
        Success message or error details
    """
    if not packages:
        return "Error: No packages specified"

    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.install_packages(packages)
        return f"Successfully installed: {', '.join(packages)}"
    except Exception as e:
        return f"Failed to install packages: {e}"


@mcp.tool()
async def start_kernel() -> str:
    """Start the Jupyter kernel.

    The kernel is started automatically on first execution, but this tool
    allows explicit control over kernel lifecycle.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.start()
        status = kernel_manager.get_status()
        return f"Kernel started successfully. Status: {status}"
    except Exception as e:
        return f"Failed to start kernel: {e}"


@mcp.tool()
async def stop_kernel() -> str:
    """Stop the Jupyter kernel.

    This clears all kernel state (variables, imports, etc.).
    A new kernel will be started on next execution.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.stop()
        return "Kernel stopped successfully"
    except Exception as e:
        return f"Failed to stop kernel: {e}"


@mcp.tool()
async def restart_kernel() -> str:
    """Restart the Jupyter kernel, clearing all state.

    This stops the current kernel and starts a fresh one.
    All variables and imports will be lost.

    Returns:
        Status message
    """
    kernel_manager = get_kernel_manager()

    try:
        await kernel_manager.restart()
        status = kernel_manager.get_status()
        return f"Kernel restarted successfully. Status: {status}"
    except Exception as e:
        return f"Failed to restart kernel: {e}"


@mcp.tool()
async def kernel_status() -> dict[str, Any]:
    """Get the current kernel status.

    Returns information about the kernel state including:
    - Whether the kernel is started
    - Whether it's currently alive
    - Current session ID and directory
    - Whether the session prelude has been executed

    Returns:
        Dictionary with kernel status information
    """
    kernel_manager = get_kernel_manager()
    return kernel_manager.get_status()


def main() -> None:
    """Entry point for the Jupyter kernel MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

