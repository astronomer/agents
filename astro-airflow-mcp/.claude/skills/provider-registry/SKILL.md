---
name: provider-registry
description: Airflow Provider Registry CLI for looking up providers, modules, parameters, and connections. Use when working with af registry commands, registry caching, or the registry API endpoints.
---

# Provider Registry CLI

Query the public Airflow Provider Registry from the terminal. No Airflow instance or auth required — hits the static JSON API directly with httpx (not the adapter/instance system).

## Commands

```bash
af registry providers                          # All providers (id, name, version, lifecycle)
af registry modules <provider_id>              # Operators, hooks, sensors, transfers
af registry parameters <provider_id>           # Constructor params for all classes
af registry connections <provider_id>          # Connection types with fields
```

All commands accept `--version <ver>` to pin a specific release and `--no-cache` to bypass local cache.

## Detailed reference

- [api-endpoints.md](api-endpoints.md) — Registry API endpoints and response shapes
- [caching.md](caching.md) — Cache location, TTLs, and implementation details

## Examples

```bash
# Find all hooks in amazon provider
af registry modules amazon | jq '.modules[] | select(.type == "hook") | .name'

# Get constructor params for FTPHook
af registry parameters ftp | jq '.classes["airflow.providers.ftp.hooks.ftp.FTPHook"]'

# List connection types
af registry connections amazon | jq '.connection_types[] | .connection_type'

# Override registry URL
af registry providers --registry-url https://custom-registry.example.com/registry
```
