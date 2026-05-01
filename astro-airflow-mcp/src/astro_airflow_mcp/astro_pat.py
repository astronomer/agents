"""PAT-based authentication using the Astro CLI's user session.

When a user runs ``astro login``, the astro CLI stores a refresh-capable JWT
in ``~/.astro/config.yaml`` (per-context: ``token``, ``refreshtoken``, and
``expiresin``). This module reuses that credential as a bearer token for
Astro-hosted Airflow APIs, refreshing via Auth0 directly when the token is
near expiry or after a 401 from the deployment.

Auth0 exchange mirrors astro-cli/cmd/cloud/setup.go::refresh.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import yaml
from filelock import FileLock, Timeout

from astro_airflow_mcp._astro_session import (
    AstroNotLoggedInError,
    AstroPATError,
    _astro_home,
    _auth_config_url,
    _bearer_from_ctx,
    _config_path,
    _context_key,
    _find_context,
    _parse_expiry,
    _read_yaml,
)
from astro_airflow_mcp.logging import get_logger

# Re-exported so existing imports (eg from tests) continue to work.
__all__ = [
    "EXPIRY_SKEW_SECONDS",
    "REFRESH_DEBOUNCE_SECONDS",
    "AstroAuthConfigUnreachableError",
    "AstroNotLoggedInError",
    "AstroPATAuth",
    "AstroPATError",
    "AstroPATResolver",
    "AstroRefreshFailedError",
    "_astro_home",
    "_auth_config_url",
    "_bearer_from_ctx",
    "_config_path",
    "_context_key",
    "_find_context",
    "_parse_expiry",
    "_read_yaml",
]

logger = get_logger(__name__)

# Refresh 60s before expiry to absorb clock skew.
EXPIRY_SKEW_SECONDS = 60

# When auth_flow gets back-to-back 401s (eg af walking deployments the user
# lacks access to), don't burn Auth0 quota force-refreshing for each. If we
# already refreshed within this window, the cached bearer is fine; the next
# 401 means "no access," not "expired token." Let it propagate.
REFRESH_DEBOUNCE_SECONDS = 60

# astro CLI's writeConfigYamlLocked uses a 10s lock timeout with 100ms
# retries. Match those parameters so concurrent rewrites cooperate.
_CONFIG_LOCK_TIMEOUT = 10.0
_CONFIG_LOCK_POLL_INTERVAL = 0.1

# astro-cli's FetchDomainAuthConfig gates on the segment matching this header.
_AUTH_CONFIG_HEADER = {
    "Content-Type": "application/json",
    "X-Astro-Client-Identifier": "cli",
}

_API_TOKEN_ENV_VAR = "ASTRO_API_TOKEN"  # nosec B105 - env var name, not a credential


class AstroRefreshFailedError(AstroPATError):
    """OAuth refresh-token exchange failed terminally (eg invalid_grant)."""


class AstroAuthConfigUnreachableError(AstroPATError):
    """Couldn't fetch the per-domain auth-config (network or non-200)."""


@dataclass
class _CachedToken:
    bearer: str
    expires_at: float  # epoch seconds; 0 means "unknown" (only meaningful when static=False)
    # Static tokens (eg ASTRO_API_TOKEN) never expire and don't refresh.
    # Non-static tokens with expires_at=0 mean "couldn't parse expiresin"
    # and should be re-resolved from disk on every call.
    static: bool = False


def _persist_rotated_session(
    *,
    domain: str,
    bearer: str,
    refresh_token: str,
    expires_at: float,
) -> None:
    """Write a rotated Auth0 session back to ~/.astro/config.yaml.

    Holds the same flock astro CLI uses (config.yaml.lock, 10s timeout,
    100ms retry) and writes atomically via tmp + ``os.replace``. If the
    config file or matching context is gone by the time we re-read,
    silently skip — that means another process already mutated the file
    and our update may no longer be applicable.
    """
    path = _config_path()
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_path), timeout=_CONFIG_LOCK_TIMEOUT)
    try:
        lock.acquire(poll_interval=_CONFIG_LOCK_POLL_INTERVAL)
    except Timeout:
        logger.warning("Timed out acquiring %s; skipping refresh_token persist", lock_path)
        return
    try:
        cfg = _read_yaml(path)
        contexts = cfg.get("contexts") if isinstance(cfg, dict) else None
        if not isinstance(contexts, dict):
            return
        key = _context_key(domain)
        ctx = contexts.get(key)
        # Fall back to scanning by domain field for older configs.
        if not isinstance(ctx, dict):
            for k, v in contexts.items():
                if isinstance(v, dict) and v.get("domain") == domain:
                    key = k
                    ctx = v
                    break
        if not isinstance(ctx, dict):
            return
        ctx["token"] = f"Bearer {bearer}"
        ctx["refreshtoken"] = refresh_token
        ctx["expiresin"] = (
            datetime.fromtimestamp(expires_at, tz=timezone.utc).replace(tzinfo=None).isoformat()
        )
        contexts[key] = ctx
        cfg["contexts"] = contexts
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{os.getpid()}")
        tmp_path.write_text(yaml.safe_dump(cfg, default_flow_style=False))
        with contextlib.suppress(OSError):
            os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        lock.release()


class AstroPATResolver:
    """Resolve an Astro user JWT for use as a bearer credential.

    Reads ~/.astro/config.yaml on demand and refreshes via Auth0 directly
    when the cached token is near expiry. Thread-safe; serializes refreshes
    via an internal lock to avoid duplicate Auth0 round-trips when many
    requests miss the cache simultaneously.
    """

    def __init__(
        self,
        domain: str | None = None,
        timeout: float = 30.0,
        verify: bool | str = True,
        env: dict[str, str] | None = None,
    ) -> None:
        self._domain = domain
        self._timeout = timeout
        self._verify = verify
        self._env = env if env is not None else os.environ
        self._lock = threading.Lock()
        self._cached: _CachedToken | None = None
        # (clientId, domainUrl) is static per domain; resolver only handles
        # one domain so a single slot suffices.
        self._auth_config: dict[str, Any] | None = None
        # Tracks the last successful Auth0 refresh round-trip; used to
        # debounce force_refresh requests when callers walk a list of
        # deployments and 401 on each (no-access set).
        self._last_refresh_at: float = 0.0

    @property
    def domain(self) -> str | None:
        return self._domain

    def get_token(self, force_refresh: bool = False) -> str:
        """Return a valid bearer token for the resolver's domain.

        Args:
            force_refresh: Skip the cache TTL check and refresh now. Used by
                AstroPATAuth's 401-retry path to recover when the server
                rejects what we thought was a fresh token.

        Raises:
            AstroNotLoggedInError: No usable session on disk (and no env-var
                fallback).
            AstroRefreshFailedError: Auth0 returned an error other than
                transient network noise.
            AstroAuthConfigUnreachableError: Couldn't reach the auth-config
                endpoint to discover Auth0's clientId/domainUrl.
        """
        # ASTRO_API_TOKEN is a long-lived workspace API token; no refresh
        # story, so we cache it as static and skip the on-disk PAT path.
        api_token = self._env.get(_API_TOKEN_ENV_VAR)
        if api_token:
            if not self._cached or self._cached.bearer != api_token:
                self._cached = _CachedToken(bearer=api_token.strip(), expires_at=0.0, static=True)
            return self._cached.bearer

        # Debounce: if we just refreshed, the cached bearer is the freshest
        # we'll get. Another 401 means "no access," not "expired token";
        # skipping the redundant Auth0 round-trip lets the 401 propagate.
        if (
            force_refresh
            and self._cached
            and time.time() - self._last_refresh_at < REFRESH_DEBOUNCE_SECONDS
        ):
            return self._cached.bearer

        if not force_refresh and self._cached and self._fresh(self._cached):
            return self._cached.bearer

        with self._lock:
            # Double-check inside the lock so a winning thread's refresh is
            # reused by losers waiting on the lock.
            if (
                force_refresh
                and self._cached
                and time.time() - self._last_refresh_at < REFRESH_DEBOUNCE_SECONDS
            ):
                return self._cached.bearer
            if not force_refresh and self._cached and self._fresh(self._cached):
                return self._cached.bearer

            domain, ctx = _find_context(_read_yaml(_config_path()), self._domain)
            disk_bearer = _bearer_from_ctx(ctx)
            disk_exp = _parse_expiry(ctx)

            # If the astro CLI just refreshed for us, prefer that token over
            # spending an Auth0 round-trip.
            if not force_refresh and disk_bearer and disk_exp - time.time() > EXPIRY_SKEW_SECONDS:
                self._cached = _CachedToken(disk_bearer, disk_exp)
                return disk_bearer

            refresh_token = ctx.get("refreshtoken")
            if not refresh_token:
                # API-token flow (or malformed config): surface what's
                # there. static=False means _fresh checks expires_at, so a
                # malformed expiresin (disk_exp=0) re-reads disk on every
                # call (cheap, recovers when the user logs in again);
                # a parseable expiresin caches normally.
                if disk_bearer:
                    self._cached = _CachedToken(disk_bearer, disk_exp or 0.0)
                    return disk_bearer
                raise AstroNotLoggedInError(
                    f"No refresh_token or token in astro context for {domain!r}. Run `astro login`."
                )

            new_bearer, new_exp = self._refresh(domain, refresh_token)
            self._cached = _CachedToken(new_bearer, new_exp)
            self._last_refresh_at = time.time()
            return new_bearer

    def _fresh(self, cached: _CachedToken) -> bool:
        # Static tokens (eg ASTRO_API_TOKEN) never expire.
        if cached.static:
            return True
        # Non-static with expires_at=0 means "couldn't parse expiresin"; treat
        # as stale so the next call re-resolves from disk instead of holding a
        # possibly-expired bearer until the process restarts.
        return time.time() < cached.expires_at - EXPIRY_SKEW_SECONDS

    def _fetch_auth_config(self, domain: str) -> dict[str, Any]:
        if self._auth_config is not None:
            return self._auth_config
        url = _auth_config_url(domain)
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
                resp = client.get(url, headers=_AUTH_CONFIG_HEADER)
        except httpx.RequestError as exc:
            raise AstroAuthConfigUnreachableError(
                f"Couldn't reach auth-config at {url}: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise AstroAuthConfigUnreachableError(
                f"auth-config returned HTTP {resp.status_code} from {url}"
            )
        cfg = resp.json()
        if "clientId" not in cfg or "domainUrl" not in cfg:
            raise AstroAuthConfigUnreachableError(
                f"auth-config response missing required fields: {cfg}"
            )
        self._auth_config = cfg
        return cfg

    def _refresh(self, domain: str, refresh_token: str) -> tuple[str, float]:
        cfg = self._fetch_auth_config(domain)
        token_url = f"{cfg['domainUrl']}oauth/token"
        body = {
            "client_id": cfg["clientId"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        try:
            with httpx.Client(timeout=self._timeout, verify=self._verify) as client:
                resp = client.post(
                    token_url,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as exc:
            raise AstroRefreshFailedError(
                f"Network error during OAuth refresh to {token_url}: {exc}"
            ) from exc

        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}

        if resp.status_code != 200 or "access_token" not in data:
            err = data.get("error") if isinstance(data, dict) else None
            desc = data.get("error_description") if isinstance(data, dict) else None
            if err == "invalid_grant":
                raise AstroRefreshFailedError(
                    "Astro session expired (invalid_grant). Run `astro login`."
                )
            raise AstroRefreshFailedError(
                f"OAuth refresh failed (HTTP {resp.status_code}): "
                f"{err or 'unknown error'}: {desc or resp.text[:200]}"
            )

        bearer = data["access_token"]
        expires_in = float(data.get("expires_in") or 3600)
        new_expiry = time.time() + expires_in
        # Auth0 rotates refresh_token by default; persist the rotated value
        # so the astro CLI's own next refresh doesn't fail with invalid_grant.
        # If the response omits refresh_token (or returns the same one), skip
        # the disk write entirely — that's the common no-rotation path.
        rotated = data.get("refresh_token")
        if isinstance(rotated, str) and rotated and rotated != refresh_token:
            try:
                _persist_rotated_session(
                    domain=domain,
                    bearer=bearer,
                    refresh_token=rotated,
                    expires_at=new_expiry,
                )
            except OSError as exc:
                # Disk write failures shouldn't block the in-memory refresh;
                # the user keeps working, but the astro CLI's own next
                # refresh may need re-login.
                logger.warning("Failed to persist rotated refresh_token for %s: %s", domain, exc)
        logger.info("Refreshed astro PAT for domain %s (expires_in=%ss)", domain, int(expires_in))
        return bearer, new_expiry


class AstroPATAuth(httpx.Auth):
    """Attach the resolver's bearer; retry once on 401 with a forced refresh.

    The deployment proxy returns a bare 401 for any auth failure, so we
    can't tell expired-token from no-access; the retry is always
    speculative.
    """

    requires_response_body = False

    def __init__(self, resolver: AstroPATResolver) -> None:
        self._resolver = resolver

    def auth_flow(self, request):  # type: ignore[no-untyped-def]
        token = self._resolver.get_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        try:
            new_token = self._resolver.get_token(force_refresh=True)
        except AstroPATError as exc:
            logger.warning("PAT refresh after 401 failed: %s", exc)
            return
        # No-loop guard: if force-refresh returned the same token (static
        # ASTRO_API_TOKEN, or another thread already refreshed to the same
        # value), don't retry the same bytes through the same proxy.
        if new_token == token:
            return
        request.headers["Authorization"] = f"Bearer {new_token}"
        yield request
