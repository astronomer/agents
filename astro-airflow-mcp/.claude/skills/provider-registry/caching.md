# Registry Caching

## Location

Cache directory: `~/.af/.registry_cache/`

Each cached response is stored as `{sha256_of_url}.json` containing:

```json
{"_cached_at": 1709400000.0, "_url": "https://...", "_payload": {...}}
```

## TTL Strategy

| Request type | TTL | Rationale |
|---|---|---|
| Unversioned ("latest") | 1 hour (3600s) | Points to latest version, changes on new releases |
| Versioned (pinned) | 30 days (2592000s) | Immutable snapshots, content never changes |

The TTL is determined by whether `--version` was passed to the command. The URL itself encodes this — versioned URLs contain the version segment (e.g. `/providers/amazon/9.22.0/modules.json`).

## Cache Bypass

- `--no-cache` flag skips both read and write
- Delete the directory to clear all: `rm -rf ~/.af/.registry_cache/`

## Implementation

- `_read_cache(url, ttl)` — SHA256 key lookup, TTL check with negative-age guard (handles backward clock jumps)
- `_write_cache(url, payload)` — Creates directory if needed, silently ignores write errors
- `_fetch(url, no_cache, versioned)` — Orchestrates cache read → HTTP fetch → cache write

## Adding New Cached Commands

When adding a new registry command:

1. Call `_build_url()` to construct the URL
2. Pass `versioned=version is not None` to `_fetch()` — this selects the right TTL
3. The caching is automatic from there
