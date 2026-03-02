"""Local discovery backend for scanning ports for Airflow instances."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx

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

    def _parse_docker_port_mapping(self, ports: str) -> int | None:
        """Parse Docker port mapping string to extract host port.

        Port mapping formats:
        - "0.0.0.0:8081->8080/tcp"
        - ":::8082->8081/tcp"
        - "0.0.0.0:8081->8080/tcp, :::8081->8080/tcp" (multiple bindings)

        Args:
            ports: Port mapping string from Docker

        Returns:
            Host port number if found, None otherwise
        """
        if not ports or "->" not in ports:
            return None

        # Split by comma in case of multiple bindings (IPv4 and IPv6)
        # Take the first binding
        first_mapping = ports.split(",")[0].strip()

        # Extract the host portion (before ->)
        host_part = first_mapping.split("->")[0]

        # Extract port number after last colon
        if ":" not in host_part:
            return None

        port_str = host_part.split(":")[-1]

        try:
            return int(port_str)
        except ValueError:
            return None

    def _parse_docker_json_output(self, output: str) -> int | None:
        """Parse docker ps JSON output to extract webserver/api-server port.

        Docker outputs one JSON object per line when using --format json.

        Example JSON object:
        {
            "Names": "myproject-webserver-1",
            "Ports": "0.0.0.0:8081->8080/tcp",
            "State": "running",
            ...
        }

        Args:
            output: JSON output from docker ps command

        Returns:
            Host port number if found, None otherwise
        """
        if not output.strip():
            return None

        # Target container types for Airflow web interface (api-server used in AF 3.x)
        target_containers = {"webserver", "api-server"}

        # Docker outputs one JSON object per line
        for line in output.strip().split("\n"):
            try:
                container = json.loads(line)
                name = container.get("Names", "").lower()

                # Check if this is a webserver/api-server container
                if not any(container_type in name for container_type in target_containers):
                    continue

                # Parse the Ports field
                ports = container.get("Ports", "")
                if ports:
                    return self._parse_docker_port_mapping(ports)

            except (json.JSONDecodeError, KeyError):
                continue

        return None

    def _get_running_astro_port(self, project_dir: Path | None = None) -> int | None:
        """Check what port Astro containers are actually using at runtime.

        Uses Docker's JSON output format to query containers by project directory.
        This is more reliable than reading .astro/config.yaml when:
        - Ports are dynamically assigned at startup
        - Multiple Astro projects are running in parallel
        - Config file doesn't reflect actual running state

        Args:
            project_dir: Directory to check (default: current working directory)

        Returns:
            Port number if found, None otherwise
        """
        if project_dir is None:
            project_dir = Path.cwd()

        try:
            # Query Docker for containers in this project using JSON format
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"label=com.docker.compose.project.working_dir={project_dir}",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            return self._parse_docker_json_output(result.stdout)

        except (subprocess.SubprocessError, FileNotFoundError):
            return None

    def _build_port_scan_list(self, explicit_ports: list[int] | None) -> list[int]:
        """Build list of ports to scan with smart detection.

        Priority:
        1. Use explicitly provided ports if available
        2. Check actual running Astro containers (handles dynamic ports)
        3. Fall back to default common ports

        Args:
            explicit_ports: Explicitly provided ports to scan

        Returns:
            List of ports to scan
        """
        if explicit_ports:
            return explicit_ports

        # Try to detect running Astro container port
        running_port = self._get_running_astro_port()
        if running_port:
            # Prioritize detected port, then scan other defaults
            return [running_port] + [p for p in self.DEFAULT_PORTS if p != running_port]

        return self.DEFAULT_PORTS

    def _is_unique_url(self, url: str, seen_urls: set[str]) -> bool:
        """Check if URL is unique, treating localhost and 127.0.0.1 as equivalent.

        Args:
            url: URL to check
            seen_urls: Set of already seen URLs (will be updated)

        Returns:
            True if URL is unique and was added to seen_urls
        """
        # Normalize localhost to 127.0.0.1 for comparison
        normalized_url = url.replace("localhost", "127.0.0.1")

        if normalized_url in seen_urls:
            return False

        seen_urls.add(normalized_url)
        return True

    def discover(
        self,
        ports: list[int] | None = None,
        hosts: list[str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> list[DiscoveredInstance]:
        """Discover local Airflow instances by scanning ports.

        Port detection priority (when ports not explicitly provided):
        1. Runtime detection via Docker JSON output (most reliable for dynamic ports)
        2. Default common ports

        Args:
            ports: Ports to scan (default: auto-detect from running containers)
            hosts: Hosts to scan (default: localhost, 127.0.0.1)
            timeout: Connection timeout in seconds
            **kwargs: Additional options (ignored)

        Returns:
            List of discovered instances
        """
        if timeout is None:
            timeout = self.DEFAULT_HTTP_TIMEOUT

        # Build port list with smart detection
        scan_ports = self._build_port_scan_list(ports)

        scan_hosts = hosts if hosts else self.DEFAULT_HOSTS

        instances: list[DiscoveredInstance] = []
        seen_urls: set[str] = set()

        for host in scan_hosts:
            for port in scan_ports:
                # Check if port is open first (fast check)
                if not self._is_port_open(host, port, timeout):
                    continue

                url = f"http://{host}:{port}"

                # Skip duplicate URLs (localhost and 127.0.0.1 are equivalent)
                if not self._is_unique_url(url, seen_urls):
                    continue

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
