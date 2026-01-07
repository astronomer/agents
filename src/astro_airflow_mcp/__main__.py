"""Main entry point for running the Airflow MCP server."""

import argparse
import logging
import os

from astro_airflow_mcp.logging import configure_logging, get_logger
from astro_airflow_mcp.server import configure, mcp

logger = get_logger("main")


def main():
    """Main entry point for the Airflow MCP server."""
    # Parse command line arguments first to determine transport mode
    parser = argparse.ArgumentParser(description="Airflow MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default=os.getenv("MCP_TRANSPORT", "http"),
        choices=["stdio", "http"],
        help="Transport mode: http (default) or stdio",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("MCP_HOST", "localhost"),
        help="Host to bind to (only for http transport, default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="Port to bind to (only for http transport, default: 8000)",
    )
    parser.add_argument(
        "--airflow-url",
        type=str,
        default=os.getenv("AIRFLOW_API_URL", "http://localhost:8080"),
        help="Base URL of Airflow webserver (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--auth-token",
        type=str,
        default=os.getenv("AIRFLOW_AUTH_TOKEN"),
        help="Bearer token for Airflow API authentication (takes precedence over username/password)",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=os.getenv("AIRFLOW_USERNAME"),
        help="Username for Airflow API token authentication",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=os.getenv("AIRFLOW_PASSWORD"),
        help="Password for Airflow API token authentication",
    )

    args = parser.parse_args()

    # Configure logging - use stderr in stdio mode to avoid corrupting JSON-RPC
    stdio_mode = args.transport == "stdio"
    configure_logging(level=logging.INFO, stdio_mode=stdio_mode)

    # Configure Airflow connection settings
    configure(
        url=args.airflow_url,
        auth_token=args.auth_token,
        username=args.username,
        password=args.password,
    )

    # Log Airflow connection configuration
    logger.info(f"Airflow URL: {args.airflow_url}")
    if args.auth_token:
        logger.info("Authentication: Direct bearer token")
    elif args.username:
        logger.info(f"Authentication: Token manager (username: {args.username})")
    else:
        logger.info("Authentication: Token manager (credential-less mode)")

    # Run the server with specified transport
    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port, show_banner=False)
    else:
        mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
