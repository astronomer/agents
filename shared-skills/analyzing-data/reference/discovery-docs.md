# Documentation Discovery

Fetch product documentation to discover all related components before querying warehouse.

## Why Fetch Docs?

ILIKE patterns only find name matches. Documentation reveals **feature groupings** - components that belong together but don't share naming patterns.

Example: ApprovalOperator is part of HITL feature but doesn't contain "HITL" in name.

## When to Fetch Docs

- Query involves a **product feature** (operators, integrations, SDKs)
- The feature likely has **related components**
- You need the **complete list**, not just pattern matches

## Pattern

1. Read `data-tools-context.md` for URL patterns
2. Construct the documentation URL
3. WebFetch to discover all related components
4. Query warehouse with the complete list

## URL Patterns

See `data-tools-context.md` for:
- Airflow provider URL patterns
- Cosmos (dbt in Airflow) docs
- Astro learn guides
