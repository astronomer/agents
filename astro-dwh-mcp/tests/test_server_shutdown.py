"""Tests for MCP server shutdown behavior."""

import pytest
from unittest.mock import AsyncMock

from src import server


@pytest.fixture
def mock_kernel_manager():
    """Create a mock kernel manager."""
    manager = AsyncMock()
    manager.stop = AsyncMock()
    return manager


async def test_lifespan_stops_kernel_on_shutdown(mock_kernel_manager):
    """Test that server_lifespan stops the kernel during shutdown."""
    original = server._kernel_manager
    server._kernel_manager = mock_kernel_manager
    
    try:
        # Run the lifespan context manager
        async with server.server_lifespan(server.mcp):
            # Startup phase - kernel should not be stopped yet
            mock_kernel_manager.stop.assert_not_called()
        
        # After exiting context (shutdown), kernel should be stopped
        mock_kernel_manager.stop.assert_called_once()
    finally:
        server._kernel_manager = original


async def test_lifespan_handles_no_kernel():
    """Test that server_lifespan handles case when no kernel was started."""
    original = server._kernel_manager
    server._kernel_manager = None
    
    try:
        # Should not raise
        async with server.server_lifespan(server.mcp):
            pass
    finally:
        server._kernel_manager = original


async def test_lifespan_handles_stop_error(mock_kernel_manager):
    """Test that server_lifespan handles kernel stop errors gracefully."""
    mock_kernel_manager.stop.side_effect = Exception("Kernel already dead")
    
    original = server._kernel_manager
    server._kernel_manager = mock_kernel_manager
    
    try:
        # Should not raise, just log warning
        async with server.server_lifespan(server.mcp):
            pass
        
        mock_kernel_manager.stop.assert_called_once()
    finally:
        server._kernel_manager = original
