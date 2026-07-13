# Assets: keys, URIs, and translation granularity

> **STATUS: reviewed; URI convention runtime-verified in testing.**

## The URI convention (the one rule everything depends on)

Dagster identifies assets by key (a list of parts, e.g. `["snowflake", "core", "comments"]`). Airflow identifies assets by URI string. Every generated outlet, every asset-aware schedule, every Gate 3 assertion, and every equivalence row must agree on ONE deterministic mapping, implemented once:

```python
# include/asset_uris.py
def asset_uri(*key_parts: str) -> str:
    """The canonical Airflow Asset URI for a Dagster asset key. One implementation, imported everywhere."""
    return "dagster://assets/" + "/".join(key_parts)
```

The fixed `assets` authority segment is deliberate: Airflow normalizes host-only URIs by appending a trailing slash (`Asset("dagster://foo").uri == "dagster://foo/"`, testing runtime probe), so single-part keys without the segment silently mismatch every Gate 3 assertion and `schedule=[Asset(...)]` comparison. With the authority segment, every URI has a path and round-trips unchanged.

Rules:

1. **Prefer the physical URI when the asset has one authoritative physical target** and the Dagster project already thought of it that way: `s3://bucket/prefix/...` for object-store assets, `snowflake://db/schema/table` for warehouse tables. Physical URIs make lineage and external-event wiring natural.
2. **Otherwise use the logical scheme** `dagster://<key-parts-joined-by-slash>`, preserving the full Dagster key including `key_prefix`. Never invent shortened names; key collisions after prefix-stripping are silent.
3. **Pick 1 or 2 per project, once, during Phase 2 planning, and record it in the migration report.** Mixed conventions are allowed across assets (warehouse tables physical, everything else logical) but a single asset must have exactly one URI everywhere it appears.
4. The inventory manifest stores the computed URI per asset; Gate 3 asserts against the manifest, so the convention is enforced mechanically after that point.
5. Asset **names**: Airflow assets also have a name; use the terminal key part. URIs must be RFC-3986-ish opaque strings (no globs); avoid characters needing escaping.

dbt models: Cosmos emits its own Asset URIs per model. When Python assets depend on dbt models cross-DAG, resolve the URI Cosmos actually emits (inspect one rendered DAG) rather than assuming this convention; record the dbt-side URI form in the report. See `dbt.md`.

## Translation granularity (asset → what, exactly?)

Decision order for each asset group/domain:

1. **Domain DAG** (default): a group of assets that share a schedule and ownership becomes one DAG; each asset is a task with an explicit `Asset` outlet. Intra-domain deps are task ordering; cross-domain deps are asset-aware schedules.
2. **Standalone `@asset` DAG**: an asset that is independently scheduled and consumed in multiple places. The `airflow.sdk` `@asset` decorator (auto DAG + single task + outlet) is the closest structural analog.
3. **Fused into a consumer task**: pipeline-internal intermediates per the decision tree in `io-and-data-passing.md`.

The real-world pattern that forces the choice: `define_asset_job(selection=...)` selections usually name the natural domain DAGs; overlapping selections need the dedup rules in `automation.md`.

## Per-construct notes

| Construct | Translation | Notes |
|---|---|---|
| `@asset` | Task with outlet, or standalone `@asset` DAG | Granularity above |
| `@multi_asset(specs=...)`, `can_subset=False` | `@asset.multi` or one task with multiple outlets | MECH |
| `@multi_asset(can_subset=True)` | Split or redesign | See mapping.md; `context.selected_asset_keys` has no analog |
| `@graph_asset` | TaskGroup whose final task carries the outlet | Data passing between the inner ops follows `io-and-data-passing.md` |
| External assets (bare `AssetSpec`) | `Asset` object updated by `POST /api/v2/assets/events` or an `AssetWatcher` | The external producer must be given the new endpoint + the URI from this convention |
| Observable source assets | `AssetWatcher` (event source) or a small polling DAG emitting the asset event | The observation FUNCTION (arbitrary Python computing a DataVersion: file hash, LastModified) must be PORTED into the watcher/polling DAG; only the materialization compute is absent |
| `SourceAsset` (deprecated spelling) | Same as external assets | Scanner catches the old spelling |
| `MaterializeResult` metadata | `yield Metadata(self, {...})` on the outlet event | Consumers read `inlet_events[...][-1].extra` |
| `kinds` / `tags` / `owners` / `group_name` | DAG tags + `doc_md`; group becomes the domain DAG name | Cosmetic unless something schedules on it; check before dropping |
| `code_version` / `data_version` | No equivalent; document the loss | mapping.md section 2 |

## Metadata and lineage expectations

Airflow asset events carry `extra` dicts and `Metadata`; Astro lineage is OpenLineage-based and works at task/dataset level. Dagster's column-level lineage and catalog views do not carry over; per-asset descriptions land in `doc_md`. State this in the migration report once, project-wide, rather than per asset.
