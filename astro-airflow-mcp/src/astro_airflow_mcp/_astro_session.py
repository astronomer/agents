"""Shared helpers for reading the Astro CLI's user session on disk.

Both ``astro_pat`` (resolves a bearer for httpx) and
``discovery.astro_cli`` (reads the active context to label discovered
deployments) need the same primitives: where ``~/.astro/config.yaml``
lives, how to parse it, how to find the active context, how to compute
expiry. Hosting them here lets the auth side and the discovery side
share one canonical source without one importing the other's privates.

Names start with an underscore to signal "internal to astro-airflow-mcp".
``astro_pat`` re-exports them for backward compatibility with tests that
already import from there.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_AUTH_CONFIG_PATH = "private/v1alpha1/cli/auth-config"


class AstroPATError(Exception):
    """Base class for errors reading or refreshing the astro CLI session.

    Lives here (rather than under ``astro_pat``) so this module has no
    upward dependency. ``astro_pat`` re-exports it; existing
    ``except AstroPATError`` call sites keep working.
    """


class AstroNotLoggedInError(AstroPATError):
    """No usable session in ~/.astro/config.yaml: user needs ``astro login``."""


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


def _context_key(domain: str) -> str:
    """Key under which astro CLI stores `domain`'s context (dots → underscores)."""
    return domain.replace(".", "_")


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
    """Return token expiry as epoch seconds. 0 if unknown.

    astro CLI (via viper) writes ``expiresin`` as a tz-aware ISO timestamp
    with the local offset (eg ``2026-05-01T16:48:36+01:00``). We anchor
    naive datetimes to UTC as defense-in-depth in case a user hand-edits
    the file or another writer drops the offset, since ``.timestamp()``
    would otherwise interpret naive values as local time.
    """
    expiresin = ctx.get("expiresin")
    if isinstance(expiresin, str):
        try:
            dt = datetime.fromisoformat(expiresin)
        except ValueError:
            return 0.0
    elif isinstance(expiresin, datetime):
        # PyYAML parses unquoted ISO timestamps as datetime when possible.
        dt = expiresin
    else:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _bearer_from_ctx(ctx: dict[str, Any]) -> str:
    raw = ctx.get("token") or ""
    return raw.removeprefix("Bearer ").strip()
