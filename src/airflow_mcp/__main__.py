"""Main entry point for running the Airflow MCP server."""

import argparse
import os

from airflow_mcp.server import configure, mcp

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Airflow MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        choices=["stdio", "http"],
        help="Transport mode: stdio (default) or http (HTTP transport for Claude Code)",
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
        help="Bearer token for Airflow API authentication",
    )
    parser.add_argument(
        "--auth-username",
        type=str,
        default=os.getenv("AIRFLOW_USERNAME"),
        help="Username for Basic authentication",
    )
    parser.add_argument(
        "--auth-password",
        type=str,
        default=os.getenv("AIRFLOW_PASSWORD"),
        help="Password for Basic authentication",
    )

    args = parser.parse_args()

    # Configure Airflow connection settings
    configure(
        url=args.airflow_url,
        auth_token=args.auth_token,
        auth_username=args.auth_username,
        auth_password=args.auth_password,
    )

    # Run the server with specified transport
    if args.transport == "http":
        print(f"Starting Airflow MCP Server in HTTP mode on {args.host}:{args.port}")
        print(f"Airflow URL: {args.airflow_url}")
        if args.auth_token:
            print("Authentication: Bearer token")
        elif args.auth_username:
            print("Authentication: Basic auth")
        else:
            print("Authentication: None")
        print(f"Connect using: http://{args.host}:{args.port}")
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        print("Starting Airflow MCP Server in stdio mode")
        print(f"Airflow URL: {args.airflow_url}")
        mcp.run()
