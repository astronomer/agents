"""Local discovery backend for scanning ports for Airflow instances."""

from __future__ import annotations

import asyncio
import socket
import time
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

    DEFAULT_PORTS = [8080, 8081, 8082, 8083, 8084, 8085, 8086, 8087, 8088, 8089, 8090, 8793]
    DEFAULT_HOSTS = ["localhost", "127.0.0.1"]

    # Indicators that a service is Airflow
    AIRFLOW_INDICATORS = [
        "airflow",
        "metadatabase",
        "scheduler",
        "triggerer",
        "dag_processor",
    ]

    def __init__(self) -> None:
        """Initialize the local discovery backend."""

    @property
    def name(self) -> str:
        """The backend name."""
        return "local"

    def is_available(self) -> bool:
        """Local discovery is always available."""
        return True

    def discover(
        self,
        ports: list[int] | None = None,
        hosts: list[str] | None = None,
        timeout: float = 2.0,
        **kwargs: Any,
    ) -> list[DiscoveredInstance]:
        """Discover local Airflow instances by scanning ports.

        Args:
            ports: Ports to scan (default: 8080, 8081, 8082, 8793)
            hosts: Hosts to scan (default: localhost, 127.0.0.1)
            timeout: Connection timeout in seconds
            **kwargs: Additional options (ignored)

        Returns:
            List of discovered instances
        """
        scan_ports = ports if ports else self.DEFAULT_PORTS
        scan_hosts = hosts if hosts else self.DEFAULT_HOSTS

        instances: list[DiscoveredInstance] = []
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
                    instance_name = f"local-{port}"
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

    def _detect_airflow(self, url: str, timeout: float) -> dict[str, Any] | None:
        """Try to detect if a URL is an Airflow instance.

        Checks various health endpoints and looks for Airflow indicators.

        Args:
            url: Base URL to check
            timeout: Request timeout in seconds

        Returns:
            Dict with Airflow info if detected, None otherwise
        """
        # Endpoints to try (in order of preference)
        health_endpoints = [
            "/api/v1/health",  # Airflow 2.x REST API
            "/api/v2/health",  # Airflow 3.x REST API
            "/health",  # Legacy health endpoint
        ]

        # Use strict timeout that applies to entire request, not per-phase
        strict_timeout = httpx.Timeout(timeout, connect=timeout, read=timeout, write=timeout)

        with httpx.Client(timeout=strict_timeout) as client:
            for endpoint in health_endpoints:
                try:
                    response = client.get(f"{url}{endpoint}")
                    if response.status_code == 200:
                        return self._parse_health_response(response, endpoint)
                except httpx.TimeoutException:
                    # Timeout means port doesn't speak HTTP properly, bail out early
                    return None
                except httpx.RequestError:
                    continue

            # Try to detect from root or other endpoints
            try:
                response = client.get(url)
                if response.status_code == 200 and self._looks_like_airflow(response.text):
                    return {"detected_from": "root", "api_version": "unknown"}
            except httpx.RequestError:
                pass

        return None

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
            # Not JSON, check if it looks like Airflow anyway
            if self._looks_like_airflow(response.text):
                return {"detected_from": endpoint, "api_version": "unknown"}
            return None

        # Check for Airflow health response structure
        # Airflow 2.x/3.x return {"metadatabase": {...}, "scheduler": {...}, ...}
        if isinstance(data, dict) and any(key in data for key in self.AIRFLOW_INDICATORS):
            api_version = (
                "v2" if "/api/v2" in endpoint else "v1" if "/api/v1" in endpoint else "unknown"
            )
            return {
                "detected_from": endpoint,
                "api_version": api_version,
                "health": data,
            }

        return None

    def _looks_like_airflow(self, text: str) -> bool:
        """Check if text content looks like it's from Airflow.

        Args:
            text: Response text to check

        Returns:
            True if content appears to be from Airflow
        """
        text_lower = text.lower()
        # Look for Airflow-specific strings
        airflow_strings = [
            "airflow",
            "apache airflow",
            "dag",
            "airflow webserver",
        ]
        return any(s in text_lower for s in airflow_strings)

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
        concurrency: int = 500,
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

    def discover_wide(
        self,
        host: str = "localhost",
        start_port: int = 1024,
        end_port: int = 65535,
        timeout: float = 0.1,
        concurrency: int = 200,
        verbose: bool = True,
    ) -> list[DiscoveredInstance]:
        """Experimental: Scan a wide port range for Airflow instances.

        This is more intensive but can find Airflow running on non-standard ports.

        Args:
            host: Host to scan (default: localhost)
            start_port: Start of port range (default: 1024)
            end_port: End of port range (default: 65535)
            timeout: Timeout per port check in seconds (default: 0.1)
            concurrency: Max concurrent connections (default: 200, higher values may miss ports)
            verbose: Print progress updates

        Returns:
            List of discovered Airflow instances
        """
        from rich.console import Console

        console = Console()
        start_time = time.time()
        total_ports = end_port - start_port + 1

        # Run the async port scan with spinner
        if verbose:
            with console.status(
                f"[bold]Scanning {total_ports:,} ports on {host}...", spinner="dots"
            ):
                open_ports = asyncio.run(
                    self._scan_port_range_async(
                        host=host,
                        start_port=start_port,
                        end_port=end_port,
                        timeout=timeout,
                        concurrency=concurrency,
                        progress_callback=None,
                    )
                )
        else:
            open_ports = asyncio.run(
                self._scan_port_range_async(
                    host=host,
                    start_port=start_port,
                    end_port=end_port,
                    timeout=timeout,
                    concurrency=concurrency,
                    progress_callback=None,
                )
            )

        scan_time = time.time() - start_time

        # Check each open port for Airflow with spinner
        instances: list[DiscoveredInstance] = []
        if open_ports:
            if verbose:
                with console.status(
                    f"[bold]Checking {len(open_ports)} open ports for Airflow...",
                    spinner="dots",
                ):
                    for port in open_ports:
                        url = f"http://{host}:{port}"
                        airflow_info = self._detect_airflow(url, timeout=2.0)
                        if airflow_info:
                            instance_name = f"local-{port}"
                            instances.append(
                                DiscoveredInstance(
                                    name=instance_name,
                                    url=url,
                                    source=self.name,
                                    auth_token=None,
                                    metadata=airflow_info,
                                )
                            )
            else:
                for port in open_ports:
                    url = f"http://{host}:{port}"
                    airflow_info = self._detect_airflow(url, timeout=2.0)
                    if airflow_info:
                        instance_name = f"local-{port}"
                        instances.append(
                            DiscoveredInstance(
                                name=instance_name,
                                url=url,
                                source=self.name,
                                auth_token=None,
                                metadata=airflow_info,
                            )
                        )

        total_time = time.time() - start_time

        # Print summary
        if verbose:
            console.print(
                f"Scanned {total_ports:,} ports in {scan_time:.1f}s, "
                f"found {len(open_ports)} open, "
                f"{len(instances)} Airflow instance(s) ({total_time:.1f}s total)"
            )

        return instances
