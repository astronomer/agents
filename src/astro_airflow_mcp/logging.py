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


def configure_logging(level: str | int = logging.INFO) -> None:
    """Configure logging for the airflow_mcp package.

    Sets up a simple console handler with a standard format.

    Args:
        level: Logging level (e.g., logging.INFO, logging.DEBUG, or "INFO", "DEBUG")
              Defaults to INFO.

    Example:
        >>> configure_logging(level=logging.DEBUG)
    """
    # Convert string level to int if needed
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Get the root airflow_mcp logger
    logger = get_logger()
    logger.setLevel(level)

    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Create simple formatter
    formatter = logging.Formatter(fmt="%(levelname)s: %(message)s")
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
