"""Logging utilities for Airflow MCP."""

import logging
import sys


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger instance nested under the airflow_mcp namespace.

    Args:
        name: Optional name for the logger. If not provided, returns root airflow_mcp logger.
              Will be nested under 'airflow_mcp' (e.g., 'airflow_mcp.server')

    Returns:
        A logger instance

    Example:
        >>> logger = get_logger("server")
        >>> logger.info("Starting server")
    """
    if name:
        return logging.getLogger(f"airflow_mcp.{name}")
    return logging.getLogger("airflow_mcp")


def configure_logging(level: str | int = logging.INFO, stdio_mode: bool = False) -> None:
    """Configure logging for the airflow_mcp package.

    Sets up a console handler with a standard format. When running in stdio mode,
    logs are sent to stderr to avoid corrupting JSON-RPC messages on stdout.

    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG, or "INFO", "DEBUG")
              Defaults to INFO.
        stdio_mode: If True, logs to stderr instead of stdout to avoid corrupting
                   JSON-RPC protocol messages. Defaults to False.

    Example:
        >>> configure_logging(level=logging.DEBUG)
        >>> configure_logging(level=logging.INFO, stdio_mode=True)  # For MCP stdio transport
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Get the root airflow_mcp logger
    logger = get_logger()
    logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler - use stderr in stdio mode to avoid corrupting JSON-RPC
    stream = sys.stderr if stdio_mode else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)

    # Create simple formatter
    formatter = logging.Formatter(fmt="%(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
