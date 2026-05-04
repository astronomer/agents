"""Adapter factory for creating version-specific Airflow clients."""

from collections.abc import Callable

import httpx

from astro_airflow_mcp.adapters.airflow_v2 import AirflowV2Adapter
from astro_airflow_mcp.adapters.airflow_v3 import AirflowV3Adapter
from astro_airflow_mcp.adapters.base import AirflowAdapter, NotFoundError
from astro_airflow_mcp.astro_pat import AstroPATError
from astro_airflow_mcp.utils import normalize_airflow_url


def detect_version(
    airflow_url: str,
    token_getter: Callable[[], str | None] | None = None,
    basic_auth_getter: Callable[[], tuple[str, str] | None] | None = None,
    auth_handler: httpx.Auth | None = None,
    verify: bool | str = True,
) -> tuple[int, str]:
    """Detect Airflow version by probing API endpoints.

    Args:
        airflow_url: Base URL of Airflow webserver
        token_getter: Callable that returns current auth token (or None)
        basic_auth_getter: Callable that returns (username, password) tuple or None
        auth_handler: Optional ``httpx.Auth`` instance (eg ``AstroPATAuth``);
            takes precedence over token/basic getters when provided.
        verify: SSL verification setting for httpx.Client

    Returns:
        Tuple of (major_version, full_version_string)

    Raises:
        RuntimeError: If version detection fails
    """
    airflow_url = normalize_airflow_url(airflow_url)

    headers: dict[str, str] = {}
    auth: tuple[str, str] | httpx.Auth | None = None

    if auth_handler is not None:
        auth = auth_handler
    else:
        if token_getter:
            token = token_getter()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        if basic_auth_getter:
            auth = basic_auth_getter()

    probe_failures: list[str] = []

    def _probe(api_path: str, default_version: str) -> tuple[int, str] | None:
        try:
            with httpx.Client(timeout=10.0, verify=verify) as client:
                response = client.get(
                    f"{airflow_url}{api_path}/version",
                    headers=headers,
                    auth=auth,
                )
        except AstroPATError:
            # PAT misconfiguration (no astro login, refresh failed, etc) —
            # surface to the caller rather than masking as a version
            # detection failure.
            raise
        except Exception as e:
            probe_failures.append(f"{api_path}: {type(e).__name__}: {e}")
            return None

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as e:
                probe_failures.append(
                    f"{api_path}: 200 but non-JSON body ({type(e).__name__}); "
                    f"got Content-Type={response.headers.get('content-type', '?')}"
                )
                return None
            version = data.get("version", default_version)
            major = int(version.split(".")[0])
            return (major, version)

        probe_failures.append(f"{api_path}: HTTP {response.status_code}")
        return None

    result = _probe("/api/v2", "3.0.0")
    if result is not None:
        return result
    result = _probe("/api/v1", "2.0.0")
    if result is not None:
        return result

    detail = "; ".join(probe_failures) if probe_failures else "no response"
    raise RuntimeError(
        f"Failed to detect Airflow version at {airflow_url}. "
        f"Probes: {detail}. Ensure Airflow is running and accessible."
    )


def create_adapter(
    airflow_url: str,
    token_getter: Callable[[], str | None] | None = None,
    basic_auth_getter: Callable[[], tuple[str, str] | None] | None = None,
    auth_handler: httpx.Auth | None = None,
    verify: bool | str = True,
) -> AirflowAdapter:
    """Create appropriate adapter based on detected Airflow version.

    Args:
        airflow_url: Base URL of Airflow webserver
        token_getter: Callable that returns current auth token (or None)
        basic_auth_getter: Callable that returns (username, password) tuple or None
                         Used as fallback for Airflow 2.x which doesn't support token auth
        auth_handler: Optional ``httpx.Auth`` instance (eg ``AstroPATAuth``);
            attaches bearer and handles 401 retries.
        verify: SSL verification setting for httpx.Client

    Returns:
        Version-specific adapter instance

    Raises:
        RuntimeError: If version detection fails or version is unsupported
    """
    major_version, full_version = detect_version(
        airflow_url,
        token_getter=token_getter,
        basic_auth_getter=basic_auth_getter,
        auth_handler=auth_handler,
        verify=verify,
    )

    if major_version == 2:
        return AirflowV2Adapter(
            airflow_url,
            full_version,
            token_getter=token_getter,
            basic_auth_getter=basic_auth_getter,
            auth_handler=auth_handler,
            verify=verify,
        )
    if major_version >= 3:
        return AirflowV3Adapter(
            airflow_url,
            full_version,
            token_getter=token_getter,
            basic_auth_getter=basic_auth_getter,
            auth_handler=auth_handler,
            verify=verify,
        )
    raise RuntimeError(f"Unsupported Airflow version: {major_version}")


__all__ = [
    "AirflowAdapter",
    "AirflowV2Adapter",
    "AirflowV3Adapter",
    "NotFoundError",
    "create_adapter",
    "detect_version",
]
