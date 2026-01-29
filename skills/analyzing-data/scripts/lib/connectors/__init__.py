"""Database connector registry and factory."""

from typing import Any

from .base import DatabaseConnector

_CONNECTOR_REGISTRY: dict[str, type[DatabaseConnector]] = {}


def register_connector(cls: type[DatabaseConnector]) -> type[DatabaseConnector]:
    _CONNECTOR_REGISTRY[cls.connector_type()] = cls
    return cls


def get_connector_class(connector_type: str) -> type[DatabaseConnector]:
    if connector_type not in _CONNECTOR_REGISTRY:
        available = ", ".join(sorted(_CONNECTOR_REGISTRY.keys()))
        raise ValueError(
            f"Unknown connector type: {connector_type!r}. Available: {available}"
        )
    return _CONNECTOR_REGISTRY[connector_type]


def create_connector(data: dict[str, Any]) -> DatabaseConnector:
    connector_type = data.get("type", "snowflake")
    cls = get_connector_class(connector_type)
    return cls.from_dict(data)


def list_connector_types() -> list[str]:
    return sorted(_CONNECTOR_REGISTRY.keys())


# Import connectors to register them
from .bigquery import BigQueryConnector  # noqa: E402, F401
from .postgres import PostgresConnector  # noqa: E402, F401
from .snowflake import SnowflakeConnector  # noqa: E402, F401
from .sqlalchemy import SQLAlchemyConnector  # noqa: E402, F401

__all__ = [
    "DatabaseConnector",
    "register_connector",
    "get_connector_class",
    "create_connector",
    "list_connector_types",
    "SnowflakeConnector",
    "PostgresConnector",
    "BigQueryConnector",
    "SQLAlchemyConnector",
]
