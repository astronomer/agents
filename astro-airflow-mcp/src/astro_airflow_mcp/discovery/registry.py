"""Discovery registry for managing and orchestrating backends."""

from __future__ import annotations

from typing import Any

from astro_airflow_mcp.discovery.base import (
    DiscoveredInstance,
    DiscoveryBackend,
    DiscoveryError,
)


class DiscoveryRegistry:
    """Registry for discovery backends.

    Manages multiple backends and orchestrates discovery across them.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._backends: dict[str, DiscoveryBackend] = {}

    def register(self, backend: DiscoveryBackend) -> None:
        """Register a discovery backend.

        Args:
            backend: The backend to register
        """
        self._backends[backend.name] = backend

    def unregister(self, name: str) -> None:
        """Unregister a backend by name.

        Args:
            name: The backend name to unregister
        """
        self._backends.pop(name, None)

    def get_backend(self, name: str) -> DiscoveryBackend | None:
        """Get a backend by name.

        Args:
            name: The backend name

        Returns:
            The backend or None if not found
        """
        return self._backends.get(name)

    def get_all_backends(self) -> list[DiscoveryBackend]:
        """Get all registered backends.

        Returns:
            List of all backends
        """
        return list(self._backends.values())

    def get_available_backends(self) -> list[DiscoveryBackend]:
        """Get all backends that are currently available.

        Returns:
            List of available backends
        """
        return [b for b in self._backends.values() if b.is_available()]

    def discover_all(
        self,
        backends: list[str] | None = None,
        **options: Any,
    ) -> dict[str, list[DiscoveredInstance]]:
        """Run discovery on multiple backends.

        Args:
            backends: List of backend names to use (default: all available)
            **options: Options to pass to each backend's discover method

        Returns:
            Dict mapping backend name to list of discovered instances

        Raises:
            DiscoveryError: If a specified backend is not found or unavailable
        """
        results: dict[str, list[DiscoveredInstance]] = {}

        if backends:
            # Use specified backends
            for name in backends:
                backend = self._backends.get(name)
                if backend is None:
                    raise DiscoveryError(f"Backend '{name}' not found")
                if not backend.is_available():
                    raise DiscoveryError(f"Backend '{name}' is not available")
                results[name] = backend.discover(**options)
        else:
            # Use all available backends
            for backend in self.get_available_backends():
                try:
                    results[backend.name] = backend.discover(**options)
                except DiscoveryError:
                    # Continue with other backends if one fails
                    results[backend.name] = []

        return results


def get_default_registry() -> DiscoveryRegistry:
    """Get a registry with default backends registered.

    Returns:
        A DiscoveryRegistry with Astro and Local backends
    """
    from astro_airflow_mcp.discovery.astro import AstroDiscoveryBackend
    from astro_airflow_mcp.discovery.local import LocalDiscoveryBackend

    registry = DiscoveryRegistry()
    registry.register(AstroDiscoveryBackend())
    registry.register(LocalDiscoveryBackend())
    return registry
