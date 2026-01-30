"""CLI entry point for Astro Observe MCP Server.

Provides command-line interface for starting the MCP server with
configuration options for organization ID, authentication, and API URL.
"""

import argparse
import logging
import sys

from astro_observe_mcp.auth import get_api_url_from_config, get_org_id_from_config
from astro_observe_mcp.client import DEFAULT_API_URL
from astro_observe_mcp.server import configure, mcp


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: Enable debug logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Astro Observe MCP Server - Access Astro Cloud Observability API via MCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover org and token from 'astro login' (recommended)
  astro login
  astro-observe-mcp

  # With explicit org ID
  astro-observe-mcp --org-id clxxxxx

  # With environment variable
  export ASTRO_API_TOKEN="your-token"
  astro-observe-mcp --org-id clxxxxx

  # With explicit token
  astro-observe-mcp --org-id clxxxxx --token "your-token"

Configuration priority:
  1. --org-id / --token arguments
  2. ASTRO_API_TOKEN environment variable
  3. ~/.astro/config.yaml (created by 'astro login')
        """,
    )

    parser.add_argument(
        "--org-id",
        required=False,
        help="Astro organization ID (auto-discovered from 'astro login' if not provided)",
    )
    parser.add_argument(
        "--token",
        help="Astro API token (or set ASTRO_API_TOKEN env var, or use 'astro login')",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"Astro Cloud API URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    # Determine org ID (CLI arg > auto-discovery)
    org_id = args.org_id
    if not org_id:
        org_id = get_org_id_from_config()
        if org_id:
            logger.info("Auto-discovered org ID from ~/.astro/config.yaml")
        else:
            parser.error(
                "Organization ID required. Either:\n"
                "  1. Run 'astro login' to configure CLI, or\n"
                "  2. Provide --org-id argument"
            )

    # Determine API URL (CLI arg > auto-discovery > default)
    api_url = args.api_url
    if api_url == DEFAULT_API_URL:
        # Check if we should use a different URL based on context
        discovered_url = get_api_url_from_config()
        if discovered_url:
            api_url = discovered_url
            logger.info("Auto-discovered API URL from context: %s", api_url)

    # Configure the server
    logger.info("Starting Astro Observe MCP Server")
    logger.info("Organization ID: %s", org_id)
    logger.info("API URL: %s", api_url)
    logger.info("Transport: %s", args.transport)

    configure(
        organization_id=org_id,
        token=args.token,
        api_url=api_url,
    )

    # Run the server
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", sse_port=args.port)


if __name__ == "__main__":
    main()
