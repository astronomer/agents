"""Abstract base class for database connectors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DatabaseConnector(ABC):
    """Base class for database connectors."""

    databases: list[str]

    @classmethod
    @abstractmethod
    def connector_type(cls) -> str:
        """Return type identifier (e.g., 'snowflake', 'postgres')."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseConnector":
        """Create from config dict."""

    @abstractmethod
    def validate(self, name: str) -> None:
        """Validate config. Raise ValueError if invalid."""

    @abstractmethod
    def get_required_packages(self) -> list[str]:
        """Return pip packages needed."""

    @abstractmethod
    def get_env_vars_for_kernel(self) -> dict[str, str]:
        """Return env vars to inject into kernel."""

    @abstractmethod
    def to_python_prelude(self) -> str:
        """Generate Python code for connection + helpers."""
