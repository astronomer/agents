"""Discovery module for auto-discovering Airflow instances."""

from astro_airflow_mcp.discovery.base import (
    DiscoveredInstance,
    DiscoveryBackend,
    DiscoveryError,
)
from astro_airflow_mcp.discovery.registry import (
    DiscoveryRegistry,
    get_default_registry,
)

__all__ = [
    "DiscoveredInstance",
    "DiscoveryBackend",
    "DiscoveryError",
    "DiscoveryRegistry",
    "get_default_registry",
]
