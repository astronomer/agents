"""MCP tool implementations for the Jupyter kernel server.

These tools are exposed via FastMCP and provide:
- Python code execution
- Package installation
- Kernel lifecycle management
"""

import logging
from typing import Any

from .kernel import KernelManager

logger = logging.getLogger(__name__)


async def execute_python(
    kernel_manager: KernelManager,
    code: str,
    timeout: float = 30.0,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Execute Python code in the Jupyter kernel.

    Args:
        kernel_manager: The kernel manager instance
        code: Python code to execute
        timeout: Maximum execution time in seconds (1-300)
        session_id: Optional session identifier for state isolation

    Returns:
        Dictionary with execution results
    """
    # Set session if provided
    if session_id:
        await kernel_manager.set_session(session_id)

    # Clamp timeout to valid range
    timeout = max(1.0, min(300.0, timeout))

    result = await kernel_manager.execute(code, timeout=timeout)

    response: dict[str, Any] = {
        "success": result.success,
        "output": result.output,
    }

    if result.error:
        response["error"] = result.error

    return response


async def install_packages(
    kernel_manager: KernelManager,
    packages: list[str],
) -> dict[str, Any]:
    """Install Python packages in the kernel environment.

    Args:
        kernel_manager: The kernel manager instance
        packages: List of package names/specs to install (e.g., ['plotly>=5.0', 'scipy'])

    Returns:
        Dictionary with installation results
    """
    if not packages:
        return {"success": False, "error": "No packages specified"}

    try:
        await kernel_manager.install_packages(packages)
        return {
            "success": True,
            "message": f"Successfully installed: {', '.join(packages)}",
            "packages": packages,
        }
    except Exception as e:
        logger.warning(f"Failed to install packages {packages}: {e}")
        return {"success": False, "error": str(e)}


async def start_kernel(kernel_manager: KernelManager) -> dict[str, Any]:
    """Start the Jupyter kernel.

    Args:
        kernel_manager: The kernel manager instance

    Returns:
        Dictionary with kernel status
    """
    try:
        await kernel_manager.start()
        return {
            "success": True,
            "message": "Kernel started successfully",
            "status": kernel_manager.get_status(),
        }
    except Exception as e:
        logger.error(f"Failed to start kernel: {e}")
        return {"success": False, "error": str(e)}


async def stop_kernel(kernel_manager: KernelManager) -> dict[str, Any]:
    """Stop the Jupyter kernel.

    Args:
        kernel_manager: The kernel manager instance

    Returns:
        Dictionary with kernel status
    """
    try:
        await kernel_manager.stop()
        return {
            "success": True,
            "message": "Kernel stopped successfully",
        }
    except Exception as e:
        logger.error(f"Failed to stop kernel: {e}")
        return {"success": False, "error": str(e)}


async def kernel_status(kernel_manager: KernelManager) -> dict[str, Any]:
    """Get the current kernel status.

    Args:
        kernel_manager: The kernel manager instance

    Returns:
        Dictionary with kernel status information
    """
    return kernel_manager.get_status()


async def restart_kernel(kernel_manager: KernelManager) -> dict[str, Any]:
    """Restart the Jupyter kernel, clearing all state.

    Args:
        kernel_manager: The kernel manager instance

    Returns:
        Dictionary with kernel status
    """
    try:
        await kernel_manager.restart()
        return {
            "success": True,
            "message": "Kernel restarted successfully",
            "status": kernel_manager.get_status(),
        }
    except Exception as e:
        logger.error(f"Failed to restart kernel: {e}")
        return {"success": False, "error": str(e)}
