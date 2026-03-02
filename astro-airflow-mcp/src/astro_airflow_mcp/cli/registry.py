"""CLI commands for querying the Airflow Provider Registry."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Annotated

import httpx
import typer

from astro_airflow_mcp.cli.output import output_error, output_json

app = typer.Typer(help="Query the Airflow Provider Registry", no_args_is_help=True)

DEFAULT_REGISTRY_URL = "https://airflow.apache.org/registry"
CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_registry_url(registry_url: str | None) -> str:
    """Resolve registry base URL from flag > env > default."""
    if registry_url:
        return registry_url.rstrip("/")
    env_url = os.environ.get("AF_REGISTRY_URL")
    if env_url:
        return env_url.rstrip("/")
    return DEFAULT_REGISTRY_URL


def _cache_dir() -> Path:
    """Return the cache directory path."""
    return Path.home() / ".af" / ".registry_cache"


def _read_cache(url: str) -> dict | None:
    """Read cached response for a URL if it exists and hasn't expired."""
    cache_key = hashlib.sha256(url.encode()).hexdigest()
    cache_file = _cache_dir() / f"{cache_key}.json"
    try:
        if not cache_file.exists():
            return None
        data = json.loads(cache_file.read_text())
        age = time.time() - data.get("_cached_at", 0)
        if age < 0 or age > CACHE_TTL_SECONDS:
            return None
        return data.get("_payload")
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _write_cache(url: str, payload: dict) -> None:
    """Write response to cache. Errors are silently ignored."""
    try:
        cache_key = hashlib.sha256(url.encode()).hexdigest()
        cache_path = _cache_dir()
        cache_path.mkdir(parents=True, exist_ok=True)
        cache_file = cache_path / f"{cache_key}.json"
        cache_file.write_text(
            json.dumps({"_cached_at": time.time(), "_url": url, "_payload": payload})
        )
    except OSError:
        pass


def _fetch(url: str, no_cache: bool) -> dict:
    """Fetch JSON from the registry, using cache unless bypassed."""
    if not no_cache:
        cached = _read_cache(url)
        if cached is not None:
            return cached

    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
    except httpx.ConnectError as e:
        output_error(f"Failed to connect to registry: {e}")
        return {}  # unreachable — output_error raises SystemExit
    except httpx.HTTPError as e:
        output_error(f"Failed to connect to registry: {e}")
        return {}  # unreachable

    if response.status_code == 404:
        output_error(f"Not found: {url}")
    elif response.status_code >= 400:
        output_error(f"Registry returned HTTP {response.status_code} for {url}")

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        output_error("Registry returned invalid JSON")
        return {}  # unreachable

    if not no_cache:
        _write_cache(url, data)

    return data


def _build_url(base: str, provider_id: str | None, version: str | None, resource: str) -> str:
    """Build a registry API URL."""
    if provider_id is None:
        return f"{base}/api/{resource}"
    if version:
        return f"{base}/api/providers/{provider_id}/{version}/{resource}"
    return f"{base}/api/providers/{provider_id}/{resource}"


# Common options
RegistryUrlOption = Annotated[
    str | None,
    typer.Option(
        "--registry-url",
        help="Override registry base URL (or set AF_REGISTRY_URL)",
    ),
]

NoCacheOption = Annotated[
    bool,
    typer.Option(
        "--no-cache",
        help="Bypass local cache",
    ),
]


@app.command("providers")
def list_providers(
    registry_url: RegistryUrlOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """List all providers in the Airflow Provider Registry."""
    base = _get_registry_url(registry_url)
    url = _build_url(base, None, None, "providers.json")
    data = _fetch(url, no_cache)

    providers = data.get("providers", [])
    result = {
        "total_providers": len(providers),
        "providers": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "version": p.get("version"),
                "lifecycle": p.get("lifecycle"),
                "description": p.get("description"),
            }
            for p in providers
        ],
    }
    output_json(result)


@app.command("modules")
def list_modules(
    provider_id: Annotated[str, typer.Argument(help="Provider ID (e.g. 'amazon', 'google')")],
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Provider version"),
    ] = None,
    registry_url: RegistryUrlOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """List modules (operators, hooks, sensors, etc.) for a provider."""
    base = _get_registry_url(registry_url)
    url = _build_url(base, provider_id, version, "modules.json")
    data = _fetch(url, no_cache)

    modules = data.get("modules", [])
    result = {
        "provider_id": data.get("provider_id", provider_id),
        "version": data.get("version"),
        "total_modules": len(modules),
        "modules": modules,
    }
    output_json(result)


@app.command("parameters")
def list_parameters(
    provider_id: Annotated[str, typer.Argument(help="Provider ID (e.g. 'amazon', 'google')")],
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Provider version"),
    ] = None,
    registry_url: RegistryUrlOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """Show constructor parameters for a provider's classes."""
    base = _get_registry_url(registry_url)
    url = _build_url(base, provider_id, version, "parameters.json")
    data = _fetch(url, no_cache)

    classes = data.get("classes", {})
    result = {
        "provider_id": data.get("provider_id", provider_id),
        "total_classes": len(classes),
        "classes": classes,
    }
    output_json(result)


@app.command("connections")
def list_connections(
    provider_id: Annotated[str, typer.Argument(help="Provider ID (e.g. 'amazon', 'google')")],
    version: Annotated[
        str | None,
        typer.Option("--version", "-v", help="Provider version"),
    ] = None,
    registry_url: RegistryUrlOption = None,
    no_cache: NoCacheOption = False,
) -> None:
    """Show connection types provided by a provider."""
    base = _get_registry_url(registry_url)
    url = _build_url(base, provider_id, version, "connections.json")
    data = _fetch(url, no_cache)

    connection_types = data.get("connection_types", [])
    result = {
        "provider_id": data.get("provider_id", provider_id),
        "total_connection_types": len(connection_types),
        "connection_types": connection_types,
    }
    output_json(result)
