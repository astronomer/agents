"""PAT-based authentication using the Astro CLI's user session.

When a user runs ``astro login``, the astro CLI stores a refresh-capable JWT
in ``~/.astro/config.yaml`` (per-context: ``token``, ``refreshtoken``, and
``expiresin``). This module reuses that credential as a bearer token for
Astro-hosted Airflow APIs, refreshing via Auth0 directly when the token is
near expiry or after a 401 from the deployment.

Replaces the older deployment-token-mint flow that ran ``astro deployment
token create`` per deployment during discover. Those tokens were
``DEPLOYMENT_ADMIN``, never expired, and accumulated until manually revoked
in the Astro UI.

The Auth0 refresh exchange and auth-config endpoint are the same ones the
astro CLI uses internally (see ``astro-cli/cmd/cloud/setup.go::refresh``).
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)

# Match astro-cli's accessTokenExpThreshold (5 min). We refresh slightly more
# eagerly than the CLI does (60s skew) so we don't bake clock-skew failures
# into the happy path.
EXPIRY_SKEW_SECONDS = 60

# astro-cli's FetchDomainAuthConfig requires this header; the endpoint is
# gated on the path segment matching the header value.
_AUTH_CONFIG_HEADER = {
    "Content-Type": "application/json",
    "X-Astro-Client-Identifier": "cli",
}
_AUTH_CONFIG_PATH = "private/v1alpha1/cli/auth-config"

# CI / headless: an Astro Workspace API Token set as ASTRO_API_TOKEN is the
# canonical credential for non-interactive contexts. When present we honour
# it as a static bearer (no refresh) and skip the on-disk PAT path.
_API_TOKEN_ENV_VAR = "ASTRO_API_TOKEN"  # nosec B105 - env var name, not a credential


class AstroPATError(Exception):
    """Base class for PAT auth failures."""


class AstroNotLoggedIn(AstroPATError):
    """No usable session in ~/.astro/config.yaml — user needs `astro login`."""


class AstroRefreshFailed(AstroPATError):
    """OAuth refresh-token exchange failed terminally (eg invalid_grant)."""


class AstroAuthConfigUnreachable(AstroPATError):
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
        raise AstroNotLoggedIn("No active astro context. Run `astro login` to authenticate.")
    key = target.replace(".", "_")
    ctx = contexts.get(key)
    if ctx:
        return target, ctx
    # Backward-compat fallback for contexts that DO carry a `domain` field.
    for c in contexts.values():
        if c and c.get("domain") == target:
            return target, c
    raise AstroNotLoggedIn(f"No astro context for domain {target!r}. Run `astro login` first.")


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


class AstroPATResolver:
    """Resolve an Astro user JWT for use as a bearer credential.

    Reads ~/.astro/config.yaml on demand and refreshes via Auth0 directly
    when the cached token is near expiry. Thread-safe; serializes refreshes
    via an internal lock to avoid duplicate Auth0 round-trips when many
    requests miss the cache simultaneously.

    The resolver does NOT write back to ~/.astro/config.yaml. Each af
    process refreshes in-process; this avoids racing against the astro CLI's
    in-place writes (see otto's ``writeConfigYamlLocked`` for the pattern
    you'd need if you wanted to coordinate cross-process).
    """

    def __init__(
        self,
        domain: str | None = None,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self._domain = domain
        self._timeout = timeout
        self._env = env if env is not None else os.environ
        self._lock = threading.Lock()
        self._cached: _CachedToken | None = None
        # Auth-config (clientId, domainUrl) is static per domain.
        self._auth_config_cache: dict[str, dict[str, Any]] = {}

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
            AstroNotLoggedIn: No usable session on disk (and no env-var
                fallback).
            AstroRefreshFailed: Auth0 returned an error other than transient
                network noise.
            AstroAuthConfigUnreachable: Couldn't reach the auth-config
                endpoint to discover Auth0's clientId/domainUrl.
        """
        # Headless / CI: ASTRO_API_TOKEN trumps the on-disk session. It's a
        # long-lived workspace API token (no refresh story), so we treat it
        # as static — caching it once means future calls skip the env lookup
        # too.
        api_token = self._env.get(_API_TOKEN_ENV_VAR)
        if api_token:
            if not self._cached or self._cached.bearer != api_token:
                self._cached = _CachedToken(bearer=api_token.strip(), expires_at=0.0)
            return self._cached.bearer

        if not force_refresh and self._cached and self._fresh(self._cached):
            return self._cached.bearer

        with self._lock:
            # Double-check inside the lock so that a winning thread's
            # refresh is reused by losers waiting on the lock.
            if not force_refresh and self._cached and self._fresh(self._cached):
                return self._cached.bearer

            domain, ctx = _find_context(_read_yaml(_config_path()), self._domain)
            disk_bearer = _bearer_from_ctx(ctx)
            disk_exp = _parse_expiry(ctx)

            # If disk has a fresh token (eg the astro CLI just refreshed for
            # us), prefer it over an Auth0 round-trip.
            if not force_refresh and disk_bearer and disk_exp - time.time() > EXPIRY_SKEW_SECONDS:
                self._cached = _CachedToken(disk_bearer, disk_exp)
                return disk_bearer

            refresh_token = ctx.get("refreshtoken")
            if not refresh_token:
                # No refresh token = either an API-token flow (the user is
                # logged in via a static token) or a malformed config. We
                # surface whatever's there with expires_at=0 so callers
                # don't keep retrying.
                if disk_bearer:
                    self._cached = _CachedToken(disk_bearer, disk_exp or 0.0)
                    return disk_bearer
                raise AstroNotLoggedIn(
                    f"No refresh_token or token in astro context for {domain!r}. Run `astro login`."
                )

            new_bearer, new_exp = self._refresh(domain, refresh_token)
            self._cached = _CachedToken(new_bearer, new_exp)
            return new_bearer

    def _fresh(self, cached: _CachedToken) -> bool:
        if cached.expires_at == 0.0:
            # Static (eg ASTRO_API_TOKEN or API-token-flow) — don't auto-refresh.
            return True
        return time.time() < cached.expires_at - EXPIRY_SKEW_SECONDS

    def _fetch_auth_config(self, domain: str) -> dict[str, Any]:
        if domain in self._auth_config_cache:
            return self._auth_config_cache[domain]
        url = _auth_config_url(domain)
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(url, headers=_AUTH_CONFIG_HEADER)
        except httpx.RequestError as exc:
            raise AstroAuthConfigUnreachable(f"Couldn't reach auth-config at {url}: {exc}") from exc
        if resp.status_code != 200:
            raise AstroAuthConfigUnreachable(
                f"auth-config returned HTTP {resp.status_code} from {url}"
            )
        cfg = resp.json()
        if "clientId" not in cfg or "domainUrl" not in cfg:
            raise AstroAuthConfigUnreachable(f"auth-config response missing required fields: {cfg}")
        self._auth_config_cache[domain] = cfg
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
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    token_url,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.RequestError as exc:
            raise AstroRefreshFailed(
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
                raise AstroRefreshFailed(
                    "Astro session expired (invalid_grant). Run `astro login`."
                )
            raise AstroRefreshFailed(
                f"OAuth refresh failed (HTTP {resp.status_code}): "
                f"{err or 'unknown error'}: {desc or resp.text[:200]}"
            )

        bearer = data["access_token"]
        expires_in = float(data.get("expires_in") or 3600)
        logger.info("Refreshed astro PAT for domain %s (expires_in=%ss)", domain, int(expires_in))
        return bearer, time.time() + expires_in


class AstroPATAuth(httpx.Auth):
    """httpx.Auth flow that attaches the resolver's bearer and retries 401 once.

    On a 401 response we force-refresh and retry exactly once. The deployment
    proxy returns a bare 401 with ``Not authorized`` body for *any* auth
    failure (expired token, invalid signature, no workspace access), so we
    can't disambiguate from the response — we always try one refresh and
    surface the second 401 to the caller if it persists.
    """

    # We don't need the response body, just the status code.
    requires_response_body = False

    def __init__(self, resolver: AstroPATResolver) -> None:
        self._resolver = resolver

    def auth_flow(self, request):  # type: ignore[no-untyped-def]
        token = self._resolver.get_token()
        request.headers["Authorization"] = f"Bearer {token}"
        response = yield request
        if response.status_code != 401:
            return
        # 401 — force a refresh once. If the resolver returns the same token
        # (eg ASTRO_API_TOKEN static, or a parallel thread already refreshed
        # to the same value), don't retry — that would loop the same bytes
        # through the same proxy.
        try:
            new_token = self._resolver.get_token(force_refresh=True)
        except AstroPATError as exc:
            logger.warning("PAT refresh after 401 failed: %s", exc)
            return
        if new_token == token:
            return
        request.headers["Authorization"] = f"Bearer {new_token}"
        yield request
