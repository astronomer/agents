"""Tests for astro_pat: AstroPATResolver and AstroPATAuth."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml

from astro_airflow_mcp.astro_pat import (
    EXPIRY_SKEW_SECONDS,
    AstroAuthConfigUnreachableError,
    AstroNotLoggedInError,
    AstroPATAuth,
    AstroPATResolver,
    AstroRefreshFailedError,
    _auth_config_url,
    _CachedToken,
    _context_key,
    _find_context,
    _parse_expiry,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _write_config(astro_home: Path, *, domain: str, ctx: dict) -> Path:
    """Write a config.yaml under astro_home with the given context."""
    cfg = {
        "context": domain,
        "contexts": {_context_key(domain): ctx},
    }
    astro_home.mkdir(parents=True, exist_ok=True)
    path = astro_home / "config.yaml"
    path.write_text(yaml.safe_dump(cfg, default_flow_style=False))
    return path


@pytest.fixture
def astro_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ASTRO_HOME at a fresh temp dir for the test."""
    home = tmp_path / "astro"
    monkeypatch.setenv("ASTRO_HOME", str(home))
    return home


@pytest.fixture
def fresh_token() -> dict:
    """A context with a token that has 1h of life remaining."""
    return {
        "domain": "astronomer.io",
        "token": "Bearer fresh-jwt",
        "refreshtoken": "rt-abc",
        "expiresin": _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
    }


class TestAuthConfigURL:
    def test_plain_domain(self):
        assert _auth_config_url("astronomer.io") == (
            "https://api.astronomer.io/private/v1alpha1/cli/auth-config"
        )

    def test_dev_domain(self):
        assert _auth_config_url("astronomer-dev.io") == (
            "https://api.astronomer-dev.io/private/v1alpha1/cli/auth-config"
        )

    def test_pr_preview_domain(self):
        assert _auth_config_url("pr12345.astronomer-dev.io") == (
            "https://pr12345.api.astronomer-dev.io/private/v1alpha1/cli/auth-config"
        )

    def test_localhost(self):
        assert _auth_config_url("localhost") == (
            "http://localhost:8888/private/v1alpha1/cli/auth-config"
        )


class TestFindContext:
    def test_keyed_lookup_no_domain_field(self):
        cfg = {
            "context": "astronomer.io",
            "contexts": {"astronomer_io": {"token": "Bearer x"}},
        }
        domain, ctx = _find_context(cfg, None)
        assert domain == "astronomer.io"
        assert ctx == {"token": "Bearer x"}

    def test_explicit_domain(self):
        cfg = {
            "context": "astronomer.io",
            "contexts": {
                "astronomer_io": {"token": "Bearer prod"},
                "astronomer-dev_io": {"token": "Bearer dev"},
            },
        }
        domain, ctx = _find_context(cfg, "astronomer-dev.io")
        assert domain == "astronomer-dev.io"
        assert ctx["token"] == "Bearer dev"

    def test_fallback_to_domain_field(self):
        # Older contexts may carry a `domain` field instead of being keyed
        # by dot-replaced name.
        cfg = {
            "context": "astronomer.io",
            "contexts": {"some-key": {"domain": "astronomer.io", "token": "Bearer x"}},
        }
        domain, ctx = _find_context(cfg, None)
        assert domain == "astronomer.io"
        assert ctx["token"] == "Bearer x"

    def test_missing_active_context(self):
        with pytest.raises(AstroNotLoggedInError, match="No active astro context"):
            _find_context({}, None)

    def test_no_matching_context(self):
        cfg = {"context": "astronomer.io", "contexts": {}}
        with pytest.raises(AstroNotLoggedInError, match="No astro context for domain"):
            _find_context(cfg, None)


class TestParseExpiry:
    def test_iso_string(self):
        when = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _parse_expiry({"expiresin": when.isoformat()}) == when.timestamp()

    def test_datetime_value(self):
        # PyYAML may parse unquoted ISO timestamps as naive datetimes; treat
        # those as UTC (matches what astro CLI writes).
        when = datetime(2026, 1, 1, 12, 0, 0)
        expected = when.replace(tzinfo=timezone.utc).timestamp()
        assert _parse_expiry({"expiresin": when}) == expected

    def test_missing(self):
        assert _parse_expiry({}) == 0.0

    def test_malformed_string(self):
        assert _parse_expiry({"expiresin": "not a date"}) == 0.0

    def test_naive_iso_treated_as_utc_under_non_utc_tz(self, monkeypatch):
        # astro CLI writes expiresin without a Z suffix or offset. On a
        # non-UTC machine, datetime.fromisoformat(...).timestamp() would
        # interpret it in local time, putting expiry hours off. Confirm
        # we anchor to UTC instead.
        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        try:
            naive = "2026-01-01T12:00:00"
            expected = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
            assert _parse_expiry({"expiresin": naive}) == expected
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()

    def test_naive_datetime_treated_as_utc_under_non_utc_tz(self, monkeypatch):
        # Same case but for the PyYAML-parsed datetime branch.
        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        try:
            naive = datetime(2026, 1, 1, 12, 0, 0)
            expected = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
            assert _parse_expiry({"expiresin": naive}) == expected
        finally:
            monkeypatch.delenv("TZ", raising=False)
            time.tzset()


class TestResolverHappyPath:
    def test_returns_disk_token_when_fresh(self, astro_home, fresh_token):
        _write_config(astro_home, domain="astronomer.io", ctx=fresh_token)
        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "fresh-jwt"

    def test_caches_in_process(self, astro_home, fresh_token):
        _write_config(astro_home, domain="astronomer.io", ctx=fresh_token)
        resolver = AstroPATResolver(env={})
        # Two calls return the same token without re-reading disk.
        assert resolver.get_token() == "fresh-jwt"
        # Mutate the file — the cache should be hit on the next call.
        new_ctx = dict(fresh_token, token="Bearer different-jwt")
        _write_config(astro_home, domain="astronomer.io", ctx=new_ctx)
        assert resolver.get_token() == "fresh-jwt"


class TestResolverEnvVarFallback:
    def test_astro_api_token_env_var_wins(self, astro_home, monkeypatch):
        # Even when nothing's on disk, ASTRO_API_TOKEN suffices.
        monkeypatch.setenv("ASTRO_API_TOKEN", "static-pat-xyz")
        resolver = AstroPATResolver()
        assert resolver.get_token() == "static-pat-xyz"

    def test_astro_api_token_skips_refresh(self, astro_home, monkeypatch):
        # ASTRO_API_TOKEN takes precedence over an expired on-disk token,
        # and force_refresh keeps returning the static value (no Auth0 call).
        ctx = {
            "domain": "astronomer.io",
            "token": "Bearer expired",
            "refreshtoken": "rt-xyz",
            "expiresin": _iso(datetime.now(timezone.utc) - timedelta(hours=1)),
        }
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)
        monkeypatch.setenv("ASTRO_API_TOKEN", "api-token-static")
        resolver = AstroPATResolver()
        assert resolver.get_token() == "api-token-static"
        assert resolver.get_token(force_refresh=True) == "api-token-static"


class TestResolverRefresh:
    def _stale_ctx(self) -> dict:
        return {
            "domain": "astronomer.io",
            "token": "Bearer stale",
            "refreshtoken": "rt-xyz",
            "expiresin": _iso(datetime.now(timezone.utc) - timedelta(hours=1)),
        }

    def test_refreshes_when_disk_token_is_stale(self, astro_home, httpx_mock):
        _write_config(astro_home, domain="astronomer.io", ctx=self._stale_ctx())
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "client123", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "fresh-jwt-from-auth0", "expires_in": 3600},
        )

        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "fresh-jwt-from-auth0"

    def test_force_refresh_bypasses_cache(self, astro_home, fresh_token, httpx_mock):
        _write_config(astro_home, domain="astronomer.io", ctx=fresh_token)

        resolver = AstroPATResolver(env={})
        # First call returns disk token; cache is now populated.
        assert resolver.get_token() == "fresh-jwt"

        # Force-refresh: even though the disk token is fresh, we should hit
        # Auth0 because the resolver assumes the deployment rejected our cached
        # token.
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "client123", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "post-401-token", "expires_in": 3600},
        )
        assert resolver.get_token(force_refresh=True) == "post-401-token"

    def test_invalid_grant_raises_refresh_failed(self, astro_home, httpx_mock):
        _write_config(astro_home, domain="astronomer.io", ctx=self._stale_ctx())
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            status_code=403,
            json={"error": "invalid_grant", "error_description": "expired"},
        )
        resolver = AstroPATResolver(env={})
        with pytest.raises(AstroRefreshFailedError, match=r"invalid_grant|astro login"):
            resolver.get_token()

    def test_auth_config_unreachable_surfaces(self, astro_home, httpx_mock):
        _write_config(astro_home, domain="astronomer.io", ctx=self._stale_ctx())
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            status_code=502,
            text="bad gateway",
        )
        resolver = AstroPATResolver(env={})
        with pytest.raises(AstroAuthConfigUnreachableError, match="HTTP 502"):
            resolver.get_token()


class TestResolverNoSession:
    def test_no_config_raises_not_logged_in(self, astro_home):
        resolver = AstroPATResolver(env={})
        with pytest.raises(AstroNotLoggedInError):
            resolver.get_token()

    def test_no_refresh_token_returns_static(self, astro_home):
        # API-token flow: token but no refresh_token. We surface the token
        # with expires_at=0 (no auto-refresh).
        ctx = {"domain": "astronomer.io", "token": "Bearer api-token"}
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)
        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "api-token"


class TestResolverConcurrency:
    def test_concurrent_callers_share_one_refresh(self, astro_home, httpx_mock):
        ctx = {
            "domain": "astronomer.io",
            "token": "Bearer stale",
            "refreshtoken": "rt-xyz",
            "expiresin": _iso(datetime.now(timezone.utc) - timedelta(hours=1)),
        }
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)
        # Only one auth-config + one token response should be needed if the
        # lock works. httpx_mock will fail the test if more requests fire.
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "shared-jwt", "expires_in": 3600},
        )

        resolver = AstroPATResolver(env={})
        results: list[str] = []

        def worker() -> None:
            results.append(resolver.get_token())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == ["shared-jwt"] * 8


class TestPATAuthFlow:
    def test_attaches_bearer_header(self, astro_home, fresh_token):
        _write_config(astro_home, domain="astronomer.io", ctx=fresh_token)
        resolver = AstroPATResolver(env={})
        recorded: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded.append(request)
            return httpx.Response(200, text="ok")

        with httpx.Client(transport=httpx.MockTransport(handler), auth=AstroPATAuth(resolver)) as c:
            r = c.get("https://example.com/version")
            assert r.status_code == 200
        assert recorded[0].headers["Authorization"] == "Bearer fresh-jwt"

    def test_retries_once_on_401_with_force_refresh(self, astro_home, httpx_mock):
        # httpx mutates the same Request across auth_flow yields, so we
        # count force-refresh calls instead of inspecting headers post-hoc.
        ctx = {
            "domain": "astronomer.io",
            "token": "Bearer first",
            "refreshtoken": "rt",
            "expiresin": _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
        }
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)
        resolver = AstroPATResolver(env={})
        # Mock the refresh endpoints so force-refresh succeeds.
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "second", "expires_in": 3600},
        )
        # Deployment: 401 the first request, 200 the retry.
        httpx_mock.add_response(
            url="https://example.com/version", status_code=401, text="Not authorized"
        )
        httpx_mock.add_response(
            url="https://example.com/version", status_code=200, json={"version": "3.2.1"}
        )

        force_refresh_calls = {"n": 0}
        original_get_token = resolver.get_token

        def counting_get_token(force_refresh: bool = False) -> str:
            if force_refresh:
                force_refresh_calls["n"] += 1
            return original_get_token(force_refresh=force_refresh)

        resolver.get_token = counting_get_token  # type: ignore[method-assign]

        with httpx.Client(auth=AstroPATAuth(resolver)) as c:
            r = c.get("https://example.com/version")
            assert r.status_code == 200

        # Exactly one force-refresh: the auth_flow retried once after the 401.
        assert force_refresh_calls["n"] == 1
        # And the OAuth refresh round-trip happened.
        oauth_calls = [req for req in httpx_mock.get_requests() if "oauth/token" in str(req.url)]
        assert len(oauth_calls) == 1

    def test_does_not_loop_when_refresh_returns_same_token(self, astro_home, monkeypatch):
        # If the resolver returns the same token after force-refresh (eg
        # ASTRO_API_TOKEN static), don't retry — would just loop the same
        # bytes through the proxy.
        monkeypatch.setenv("ASTRO_API_TOKEN", "static")
        resolver = AstroPATResolver()

        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(401, text="Not authorized")

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport, auth=AstroPATAuth(resolver)) as c:
            r = c.get("https://example.com/version")
            assert r.status_code == 401
        # Only one request: refresh returned the same static token, so the
        # auth flow gave up rather than retrying.
        assert call_count["n"] == 1


class TestCachedTokenStaticVsExpiring:
    """The static flag separates "never expires" from "couldn't parse expiresin"."""

    def test_static_token_always_fresh(self, astro_home):
        resolver = AstroPATResolver(env={})
        # Static token in the past: still fresh because static=True wins.
        cached = _CachedToken(bearer="x", expires_at=0.0, static=True)
        assert resolver._fresh(cached) is True

    def test_non_static_zero_expiry_is_stale(self, astro_home):
        resolver = AstroPATResolver(env={})
        # expires_at=0 with static=False means malformed config; force
        # re-resolution rather than holding a possibly-expired bearer.
        cached = _CachedToken(bearer="x", expires_at=0.0, static=False)
        assert resolver._fresh(cached) is False

    def test_non_static_future_expiry_is_fresh(self, astro_home):
        resolver = AstroPATResolver(env={})
        cached = _CachedToken(
            bearer="x",
            expires_at=time.time() + 3600,
            static=False,
        )
        assert resolver._fresh(cached) is True


class TestRefreshTokenRotation:
    def _stale_ctx(self, refresh_token: str = "rt-old") -> dict:
        return {
            "domain": "astronomer.io",
            "token": "Bearer stale",
            "refreshtoken": refresh_token,
            "expiresin": _iso(datetime.now(timezone.utc) - timedelta(hours=1)),
        }

    def test_rotated_refresh_token_persisted_to_disk(self, astro_home, httpx_mock):
        path = _write_config(astro_home, domain="astronomer.io", ctx=self._stale_ctx("rt-old"))
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={
                "access_token": "rotated-jwt",
                "expires_in": 3600,
                "refresh_token": "rt-new",
            },
        )

        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "rotated-jwt"

        # Re-read config; rotated refresh_token should land on disk so the
        # astro CLI's own next refresh doesn't fail with invalid_grant.
        on_disk = yaml.safe_load(path.read_text())
        ctx = on_disk["contexts"][_context_key("astronomer.io")]
        assert ctx["refreshtoken"] == "rt-new"
        assert ctx["token"] == "Bearer rotated-jwt"
        # expiresin is written tz-aware to match astro CLI's viper format,
        # so future astro writes don't have to flip the user's config back.
        assert isinstance(ctx["expiresin"], datetime)
        assert ctx["expiresin"].tzinfo is not None

    def test_unchanged_refresh_token_skips_disk_write(self, astro_home, httpx_mock):
        # Common production path: Auth0 doesn't rotate. Disk shouldn't be
        # touched (verified by checking mtime).
        path = _write_config(astro_home, domain="astronomer.io", ctx=self._stale_ctx("rt-stay"))
        original_mtime = path.stat().st_mtime_ns
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            # No refresh_token in response (or it's the same).
            json={"access_token": "fresh", "expires_in": 3600},
        )
        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "fresh"
        assert path.stat().st_mtime_ns == original_mtime


class TestForceRefreshDebounce:
    """Back-to-back force_refresh requests share one Auth0 round-trip."""

    def test_second_force_refresh_returns_cached_token(self, astro_home, httpx_mock):
        ctx = {
            "domain": "astronomer.io",
            "token": "Bearer stale",
            "refreshtoken": "rt",
            "expiresin": _iso(datetime.now(timezone.utc) - timedelta(hours=1)),
        }
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)
        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        # Only one /oauth/token response is registered. If the resolver
        # hits Auth0 a second time, pytest-httpx raises a no-match error.
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "fresh", "expires_in": 3600},
        )

        resolver = AstroPATResolver(env={})
        # First force_refresh: actually hits Auth0.
        assert resolver.get_token(force_refresh=True) == "fresh"
        # Second force_refresh within the debounce window: returns cached
        # bearer; no second Auth0 round-trip.
        assert resolver.get_token(force_refresh=True) == "fresh"

        oauth_calls = [r for r in httpx_mock.get_requests() if "oauth/token" in str(r.url)]
        assert len(oauth_calls) == 1


class TestSkewBoundary:
    def test_token_within_skew_triggers_refresh(self, astro_home, httpx_mock):
        # Token expires 30s from now — under the EXPIRY_SKEW_SECONDS threshold.
        ctx = {
            "domain": "astronomer.io",
            "token": "Bearer about-to-expire",
            "refreshtoken": "rt",
            "expiresin": _iso(
                datetime.now(timezone.utc) + timedelta(seconds=EXPIRY_SKEW_SECONDS // 2)
            ),
        }
        _write_config(astro_home, domain="astronomer.io", ctx=ctx)

        httpx_mock.add_response(
            url="https://api.astronomer.io/private/v1alpha1/cli/auth-config",
            json={"clientId": "c", "domainUrl": "https://auth.astronomer.io/"},
        )
        httpx_mock.add_response(
            url="https://auth.astronomer.io/oauth/token",
            method="POST",
            json={"access_token": "renewed", "expires_in": 3600},
        )

        resolver = AstroPATResolver(env={})
        assert resolver.get_token() == "renewed"


class TestParsedYamlRobustness:
    def test_unparseable_yaml_treated_as_no_session(self, astro_home: Path):
        # Mid-write reads can return partial YAML; resolver retries once and
        # then surfaces "no session" rather than crashing on a parse error.
        astro_home.mkdir(parents=True, exist_ok=True)
        (astro_home / "config.yaml").write_text("contexts: [\n  not closed")
        resolver = AstroPATResolver(env={})
        with pytest.raises(AstroNotLoggedInError):
            resolver.get_token()

    def test_astro_home_at_dev_null_treated_as_no_session(self, monkeypatch):
        # ASTRO_HOME=os.devnull is a sentinel some wrappers use to "neutralize"
        # global astro state. Reading <devnull>/config.yaml raises
        # NotADirectoryError (not FileNotFoundError); the resolver should
        # still surface "no session" cleanly.
        if not Path(os.devnull).exists() or Path(os.devnull).is_file():
            pytest.skip("os.devnull is not a non-regular file on this platform")
        monkeypatch.setenv("ASTRO_HOME", os.devnull)
        resolver = AstroPATResolver(env={})
        with pytest.raises(AstroNotLoggedInError):
            resolver.get_token()
