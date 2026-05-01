"""Base types and protocol for discovery backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from astro_airflow_mcp.config.models import AuthKind


class DiscoveryError(Exception):
    """Base exception for discovery errors."""


@dataclass
class DiscoveredInstance:
    """An Airflow instance discovered by a backend.

    Attributes:
        name: Suggested instance name
        url: Airflow webserver URL (base, no /api/v2)
        source: Backend name (e.g., "astro", "local")
        auth_token: Static bearer token, when the backend has one.
        auth_kind: Suggested auth mode for the resulting instance.
        astro_context: Astro domain pinned for ``astro_pat`` auth (None
            means follow the active astro context at request time).
        metadata: Backend-specific metadata.
    """

    name: str
    url: str
    source: str
    auth_token: str | None = None
    auth_kind: AuthKind | None = None
    astro_context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DiscoveryBackend(Protocol):
    """Protocol for discovery backends.

    Each backend implements its own way of discovering Airflow instances.
    """

    @property
    def name(self) -> str:
        """The unique name of this backend (e.g., 'astro', 'local')."""
        ...

    def is_available(self) -> bool:
        """Check if this backend can be used.

        Returns:
            True if the backend is available (dependencies installed, etc.)
        """
        ...

    def discover(self, **options: Any) -> list[DiscoveredInstance]:
        """Discover Airflow instances.

        Args:
            **options: Backend-specific options

        Returns:
            List of discovered instances

        Raises:
            DiscoveryError: If discovery fails
        """
        ...
