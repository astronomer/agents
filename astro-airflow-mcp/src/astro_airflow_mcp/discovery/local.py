"""Local discovery backend for scanning ports for Airflow instances."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path
from typing import Any

import httpx
import yaml

from astro_airflow_mcp.constants import (
    DEFAULT_PROXY_PORT,
    get_astro_global_config_path,
    get_proxy_routes_path,
)
from astro_airflow_mcp.discovery.base import DiscoveredInstance, DiscoveryError


class LocalDiscoveryError(DiscoveryError):
    """Error during local discovery."""


class LocalDiscoveryBackend:
    """Discovery backend for local Airflow instances.

    Scans common ports for running Airflow instances by checking
    the health endpoint.
    """

    DEFAULT_PORTS = [8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089, 8090]
    DEFAULT_HOSTS = ["localhost", "127.0.0.1"]

    # Health endpoints to check (in order of preference)
    HEALTH_ENDPOINTS = [
        "/api/v2/monitor/health",  # Airflow 3.x REST API
        "/api/v1/health",  # Airflow 2.x REST API
    ]

    # Keys in health JSON response that indicate Airflow
    AIRFLOW_HEALTH_KEYS = [
        "metadatabase",
        "scheduler",
        "triggerer",
        "dag_processor",
    ]

    # Timeout and concurrency defaults
    DEFAULT_HTTP_TIMEOUT = 2.0
    DEFAULT_PORT_SCAN_CONCURRENCY = 200

    def __init__(self) -> None:
        """Initialize the local discovery backend."""

    @property
    def name(self) -> str:
        """The backend name."""
        return "local"

    def is_available(self) -> bool:
        """Local discovery is always available."""
        return True

    def get_astro_project_port(self, project_dir: Path | None = None) -> int | None:
        """Check for .astro/config.yaml and extract the configured port.

        Looks for:
        - webserver.port (Airflow 2.x via Astro CLI)
        - api-server.port (Airflow 3.x via Astro CLI)

        Args:
            project_dir: Directory to check (default: current working directory)

        Returns:
            Port number if found, None otherwise
        """
        if project_dir is None:
            project_dir = Path.cwd()

        config_path = project_dir / ".astro" / "config.yaml"
        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            if not config:
                return None

            # Check for Airflow 3.x api-server.port
            if "api-server" in config and "port" in config["api-server"]:
                return int(config["api-server"]["port"])

            # Check for Airflow 2.x webserver.port
            if "webserver" in config and "port" in config["webserver"]:
                return int(config["webserver"]["port"])

            return None
        except (OSError, yaml.YAMLError, ValueError, TypeError):
            return None

    def _get_proxy_port(self, global_config_path: Path | None = None) -> int:
        """Read the proxy port from the global Astro CLI config.

        Args:
            global_config_path: Path to ~/.astro/config.yaml (for testing)

        Returns:
            Proxy port number (default: DEFAULT_PROXY_PORT)
        """
        if global_config_path is None:
            global_config_path = get_astro_global_config_path()

        try:
            with open(global_config_path) as f:
                config = yaml.safe_load(f)
            if (
                config
                and "proxy" in config
                and isinstance(config["proxy"], dict)
                and (port := config["proxy"].get("port")) is not None
            ):
                return int(port)
        except (OSError, yaml.YAMLError, ValueError, TypeError):
            pass

        return DEFAULT_PROXY_PORT

    def _read_proxy_routes(self, routes_path: Path | None = None) -> list[dict]:
        """Read proxy routes from ~/.astro/proxy/routes.json.

        Args:
            routes_path: Path to routes.json (for testing)

        Returns:
            List of route dicts, or empty list if unavailable
        """
        if routes_path is None:
            routes_path = get_proxy_routes_path()

        try:
            with open(routes_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        return []

    def find_proxy_url_for_project(
        self,
        project_dir: str,
        routes_path: Path | None = None,
        global_config_path: Path | None = None,
    ) -> str | None:
        """Find the proxy URL for a specific project directory.

        Args:
            project_dir: The project directory to match
            routes_path: Path to routes.json (for testing)
            global_config_path: Path to global astro config (for testing)

        Returns:
            Proxy URL if a matching route is found, None otherwise
        """
        routes = self._read_proxy_routes(routes_path=routes_path)
        if not routes:
            return None

        project_path = str(Path(project_dir).resolve())
        for route in routes:
            if not (route_dir := route.get("projectDir")):
                continue
            if str(Path(route_dir).resolve()) != project_path:
                continue
            if not (hostname := route.get("hostname")):
                continue
            proxy_port = self._get_proxy_port(global_config_path=global_config_path)
            return f"http://{hostname}:{proxy_port}"

        return None

    def discover(
        self,
        ports: list[int] | None = None,
        hosts: list[str] | None = None,
        timeout: float | None = None,
        proxy_routes_path: Path | None = None,
        proxy_global_config_path: Path | None = None,
        **kwargs: Any,
    ) -> list[DiscoveredInstance]:
        """Discover local Airflow instances.

        Checks proxy routes first (for Astro CLI reverse proxy), then falls
        back to scanning ports for running Airflow instances.

        Args:
            ports: Ports to scan (default: check .astro/config.yaml, then common ports)
            hosts: Hosts to scan (default: localhost, 127.0.0.1)
            timeout: Connection timeout in seconds
            proxy_routes_path: Path to proxy routes.json (for testing)
            proxy_global_config_path: Path to global astro config (for testing)
            **kwargs: Additional options (ignored)

        Returns:
            List of discovered instances (proxy routes first, then port-scanned)
        """
        if timeout is None:
            timeout = self.DEFAULT_HTTP_TIMEOUT

        instances: list[DiscoveredInstance] = []

        # Step 1: Check proxy routes (Astro CLI reverse proxy)
        if proxy_routes := self._read_proxy_routes(routes_path=proxy_routes_path):
            proxy_port = self._get_proxy_port(global_config_path=proxy_global_config_path)
            for route in proxy_routes:
                if not (hostname := route.get("hostname")):
                    continue
                proxy_url = f"http://{hostname}:{proxy_port}"
                instance_name = f"{hostname}:{proxy_port}"
                instances.append(
                    DiscoveredInstance(
                        name=instance_name,
                        url=proxy_url,
                        source=self.name,
                        auth_token=None,
                        metadata={
                            "proxy": True,
                            "project_dir": route.get("projectDir", ""),
                            "mode": route.get("mode", ""),
                            "backend_port": route.get("port", ""),
                        },
                    )
                )

        # Step 2: Port scanning
        # Build port list: check .astro/config.yaml first, then fallback to defaults
        if ports:
            scan_ports = ports
        else:
            astro_port = self.get_astro_project_port()
            if astro_port:
                # Prioritize Astro project port, then check other common ports
                scan_ports = [astro_port] + [p for p in self.DEFAULT_PORTS if p != astro_port]
            else:
                scan_ports = self.DEFAULT_PORTS

        scan_hosts = hosts if hosts else self.DEFAULT_HOSTS

        seen_urls: set[str] = set()

        for host in scan_hosts:
            for port in scan_ports:
                # Check if port is open first (fast check)
                if not self._is_port_open(host, port, timeout):
                    continue

                # Try to detect Airflow
                url = f"http://{host}:{port}"

                # Avoid duplicates (localhost and 127.0.0.1 are the same)
                normalized_url = url.replace("localhost", "127.0.0.1")
                if normalized_url in seen_urls:
                    continue
                seen_urls.add(normalized_url)

                airflow_info = self._detect_airflow(url, timeout)
                if airflow_info:
                    instance_name = f"localhost:{port}"
                    instances.append(
                        DiscoveredInstance(
                            name=instance_name,
                            url=url,
                            source=self.name,
                            auth_token=None,
                            metadata=airflow_info,
                        )
                    )

        return instances

    def _is_port_open(self, host: str, port: int, timeout: float) -> bool:
        """Check if a port is open.

        Args:
            host: Host to check
            port: Port to check
            timeout: Timeout in seconds

        Returns:
            True if port is open
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                return result == 0
        except OSError:
            return False

    def _detect_airflow(
        self,
        url: str,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> dict[str, Any] | None:
        """Try to detect if a URL is an Airflow instance.

        Checks various health endpoints and looks for Airflow indicators.

        Args:
            url: Base URL to check
            timeout: Request timeout in seconds (default: DEFAULT_HTTP_TIMEOUT)
            client: Optional httpx client to reuse (creates one if not provided)

        Returns:
            Dict with Airflow info if detected, None otherwise
        """
        if timeout is None:
            timeout = self.DEFAULT_HTTP_TIMEOUT

        # Use strict timeout that applies to entire request, not per-phase
        strict_timeout = httpx.Timeout(timeout, connect=timeout, read=timeout, write=timeout)

        def _check_with_client(http_client: httpx.Client) -> dict[str, Any] | None:
            for endpoint in self.HEALTH_ENDPOINTS:
                try:
                    response = http_client.get(f"{url}{endpoint}")
                    if response.status_code == 200:
                        return self._parse_health_response(response, endpoint)
                except httpx.TimeoutException:
                    # Timeout means port doesn't speak HTTP properly, bail out early
                    return None
                except httpx.RequestError:
                    continue

            return None

        # Use provided client or create a new one
        if client is not None:
            return _check_with_client(client)

        with httpx.Client(timeout=strict_timeout) as new_client:
            return _check_with_client(new_client)

    def _parse_health_response(
        self, response: httpx.Response, endpoint: str
    ) -> dict[str, Any] | None:
        """Parse a health endpoint response.

        Args:
            response: The HTTP response
            endpoint: The endpoint that was called

        Returns:
            Dict with parsed info or None if not Airflow
        """
        try:
            data = response.json()
        except (ValueError, TypeError):
            # Health endpoint should return JSON; if not, it's not Airflow
            return None

        # Check for Airflow health response structure
        # Airflow 2.x/3.x return {"metadatabase": {...}, "scheduler": {...}, ...}
        if isinstance(data, dict) and any(key in data for key in self.AIRFLOW_HEALTH_KEYS):
            api_version = (
                "v2" if "/api/v2" in endpoint else "v1" if "/api/v1" in endpoint else "unknown"
            )
            return {
                "detected_from": endpoint,
                "api_version": api_version,
                "health": data,
            }

        return None

    # -------------------------------------------------------------------------
    # Experimental: Async wide port scanning
    # -------------------------------------------------------------------------

    async def _async_check_port(
        self,
        host: str,
        port: int,
        timeout: float,
    ) -> int | None:
        """Async check if a port is open.

        Args:
            host: Host to check
            port: Port to check
            timeout: Timeout in seconds

        Returns:
            Port number if open, None otherwise
        """
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            writer.close()
            await writer.wait_closed()
            return port
        except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
            return None

    async def _scan_port_range_async(
        self,
        host: str,
        start_port: int,
        end_port: int,
        timeout: float = 0.1,
        concurrency: int | None = None,
        progress_callback: Any | None = None,
    ) -> list[int]:
        """Scan a range of ports asynchronously with concurrency control.

        Args:
            host: Host to scan
            start_port: Start of port range (inclusive)
            end_port: End of port range (inclusive)
            timeout: Timeout per port in seconds
            concurrency: Max concurrent connections
            progress_callback: Optional callback(scanned, total, open_ports)

        Returns:
            List of open ports
        """
        if concurrency is None:
            concurrency = self.DEFAULT_PORT_SCAN_CONCURRENCY

        semaphore = asyncio.Semaphore(concurrency)
        open_ports: list[int] = []
        scanned = 0
        total = end_port - start_port + 1

        async def scan_with_semaphore(port: int) -> int | None:
            nonlocal scanned
            async with semaphore:
                result = await self._async_check_port(host, port, timeout)
                scanned += 1
                if progress_callback and scanned % 1000 == 0:
                    progress_callback(scanned, total, len(open_ports))
                return result

        tasks = [scan_with_semaphore(port) for port in range(start_port, end_port + 1)]
        results = await asyncio.gather(*tasks)

        for result in results:
            if result is not None:
                open_ports.append(result)

        return sorted(open_ports)

    def _check_ports_for_airflow(
        self,
        host: str,
        ports: list[int],
    ) -> list[DiscoveredInstance]:
        """Check a list of open ports for Airflow instances.

        Args:
            host: Host to check
            ports: List of open ports to check

        Returns:
            List of discovered Airflow instances
        """
        instances: list[DiscoveredInstance] = []

        if not ports:
            return instances

        # Reuse a single httpx client for all checks
        strict_timeout = httpx.Timeout(
            self.DEFAULT_HTTP_TIMEOUT,
            connect=self.DEFAULT_HTTP_TIMEOUT,
            read=self.DEFAULT_HTTP_TIMEOUT,
            write=self.DEFAULT_HTTP_TIMEOUT,
        )

        with httpx.Client(timeout=strict_timeout) as client:
            for port in ports:
                url = f"http://{host}:{port}"
                airflow_info = self._detect_airflow(url, client=client)
                if airflow_info:
                    instance_name = f"localhost:{port}"
                    instances.append(
                        DiscoveredInstance(
                            name=instance_name,
                            url=url,
                            source=self.name,
                            auth_token=None,
                            metadata=airflow_info,
                        )
                    )

        return instances

    def discover_wide(
        self,
        host: str = "localhost",
        start_port: int = 1024,
        end_port: int = 65535,
        timeout: float = 0.1,
        concurrency: int | None = None,
        verbose: bool = True,
    ) -> list[DiscoveredInstance]:
        """Experimental: Scan a wide port range for Airflow instances.

        This is more intensive but can find Airflow running on non-standard ports.

        Args:
            host: Host to scan (default: localhost)
            start_port: Start of port range (default: 1024)
            end_port: End of port range (default: 65535)
            timeout: Timeout per port check in seconds (default: 0.1)
            concurrency: Max concurrent connections (default: DEFAULT_PORT_SCAN_CONCURRENCY)
            verbose: Print progress updates

        Returns:
            List of discovered Airflow instances
        """
        from rich.console import Console

        if concurrency is None:
            concurrency = self.DEFAULT_PORT_SCAN_CONCURRENCY

        console = Console()

        # Helper to run the async port scan
        def run_port_scan() -> list[int]:
            return asyncio.run(
                self._scan_port_range_async(
                    host=host,
                    start_port=start_port,
                    end_port=end_port,
                    timeout=timeout,
                    concurrency=concurrency,
                    progress_callback=None,
                )
            )

        # Run port scan (with optional spinner)
        if verbose:
            with console.status(f"[bold]Scanning for Airflow on {host}...", spinner="dots"):
                open_ports = run_port_scan()
                instances = self._check_ports_for_airflow(host, open_ports)
        else:
            open_ports = run_port_scan()
            instances = self._check_ports_for_airflow(host, open_ports)

        # Print summary
        if verbose:
            if instances:
                console.print(f"Found {len(instances)} Airflow instance(s)")
            else:
                console.print("No Airflow instances found")

        return instances
