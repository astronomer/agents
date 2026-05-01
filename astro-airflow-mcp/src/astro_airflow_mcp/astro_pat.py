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
from pathlib import Path
from typing import Any

import httpx
import yaml
from filelock import FileLock, Timeout

from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Refresh 60s before expiry to absorb clock skew.
EXPIRY_SKEW_SECONDS = 60

# astro CLI's writeConfigYamlLocked uses a 10s lock timeout with 100ms
# retries. Match those parameters so concurrent rewrites cooperate.
_CONFIG_LOCK_TIMEOUT = 10.0
_CONFIG_LOCK_POLL_INTERVAL = 0.1

# astro-cli's FetchDomainAuthConfig gates on the segment matching this header.
_AUTH_CONFIG_HEADER = {
    "Content-Type": "application/json",
    "X-Astro-Client-Identifier": "cli",
}
_AUTH_CONFIG_PATH = "private/v1alpha1/cli/auth-config"

_API_TOKEN_ENV_VAR = "ASTRO_API_TOKEN"  # nosec B105 - env var name, not a credential


class AstroPATError(Exception):
    """Base class for PAT auth failures."""


class AstroNotLoggedInError(AstroPATError):
    """No usable session in ~/.astro/config.yaml — user needs `astro login`."""


class AstroRefreshFailedError(AstroPATError):
    """OAuth refresh-token exchange failed terminally (eg invalid_grant)."""


class AstroAuthConfigUnreachableError(AstroPATError):
    """Couldn't fetch the per-domain auth-config (network or non-200)."""


@dataclass
class _CachedToken:
    bearer: str
    expires_at: float  # epoch seconds; 0 means "unknown / treat as fresh"


def _astro_home() -> Path:
    return Path(os.environ.get("ASTRO_HOME") or (Path.home() / ".astro"))


def _config_path() -> Path:
    return _astro_home() / "config.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read and parse the astro config. Empty/missing → {}."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return {}
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError:
        # Astro CLI rewrites this file in place (truncate+write under flock).
        # If we happen to read mid-write we get a partial document. One short
        # retry catches the race; if it persists, surface as empty (caller
        # decides whether that means "log in" or "use env var fallback").
        time.sleep(0.05)
        try:
            return yaml.safe_load(path.read_text()) or {}
        except (FileNotFoundError, yaml.YAMLError):
            return {}


def _find_context(cfg: dict[str, Any], domain: str | None) -> tuple[str, dict[str, Any]]:
    """Locate (domain, context_dict) by domain or by active context.

    astro CLI keys contexts by domain with dots replaced by underscores
    (``astronomer.io`` → ``astronomer_io``). Some context dicts don't carry
    an explicit ``domain`` field, so the keyed lookup is the canonical path
    and we fall back to scanning ``ctx.domain`` only for older configs.
    """
    contexts = cfg.get("contexts") or {}
    target = domain or cfg.get("context")
    if not target:
        raise AstroNotLoggedInError("No active astro context. Run `astro login` to authenticate.")
    ctx = contexts.get(_context_key(target))
    if ctx:
        return target, ctx
    # Backward-compat fallback for contexts that DO carry a `domain` field.
    for c in contexts.values():
        if c and c.get("domain") == target:
            return target, c
    raise AstroNotLoggedInError(f"No astro context for domain {target!r}. Run `astro login` first.")


def _context_key(domain: str) -> str:
    """Key under which astro CLI stores `domain`'s context (dots → underscores)."""
    return domain.replace(".", "_")


def _auth_config_url(domain: str) -> str:
    """URL of the per-domain auth-config endpoint.

    Mirrors ``pkg/domainutil/domain.go::GetURLToEndpoint`` in astro-cli:
    plain domain → ``api.<domain>``, PR-preview ``prNNN.astronomer-dev.io``
    → ``prNNN.api.astronomer-dev.io``, and ``localhost`` → port 8888.
    """
    if domain == "localhost":
        return f"http://localhost:8888/{_AUTH_CONFIG_PATH}"
    head, _, rest = domain.partition(".")
    if head.startswith("pr") and rest:
        return f"https://{head}.api.{rest}/{_AUTH_CONFIG_PATH}"
    return f"https://api.{domain}/{_AUTH_CONFIG_PATH}"


def _parse_expiry(ctx: dict[str, Any]) -> float:
    """Return token expiry as epoch seconds. 0 if unknown."""
    expiresin = ctx.get("expiresin")
    if isinstance(expiresin, str):
        try:
            return datetime.fromisoformat(expiresin).timestamp()
        except ValueError:
            pass
    elif isinstance(expiresin, datetime):
        # PyYAML parses unquoted ISO timestamps as datetime when possible.
        return expiresin.timestamp()
    return 0.0


def _bearer_from_ctx(ctx: dict[str, Any]) -> str:
    raw = ctx.get("token") or ""
    return raw.removeprefix("Bearer ").strip()


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
                self._cached = _CachedToken(bearer=api_token.strip(), expires_at=0.0)
            return self._cached.bearer

        if not force_refresh and self._cached and self._fresh(self._cached):
            return self._cached.bearer

        with self._lock:
            # Double-check inside the lock so a winning thread's refresh is
            # reused by losers waiting on the lock.
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
                # API-token flow (or malformed config): surface what's there
                # with expires_at=0 so callers don't keep retrying.
                if disk_bearer:
                    self._cached = _CachedToken(disk_bearer, disk_exp or 0.0)
                    return disk_bearer
                raise AstroNotLoggedInError(
                    f"No refresh_token or token in astro context for {domain!r}. Run `astro login`."
                )

            new_bearer, new_exp = self._refresh(domain, refresh_token)
            self._cached = _CachedToken(new_bearer, new_exp)
            return new_bearer

    def _fresh(self, cached: _CachedToken) -> bool:
        # expires_at=0 means static (eg ASTRO_API_TOKEN); never auto-refresh.
        if cached.expires_at == 0.0:
            return True
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
