# Discovery Guide

When analyzing data, choose the right discovery approach based on the query type.

## Which Approach?

| Query Type | Approach | Reference |
|------------|----------|-----------|
| Product feature (operators, integrations) | Fetch docs first | `discovery-docs.md` |
| General data lookup | Warehouse discovery | `discovery-warehouse.md` |
| Both | Parallel - fetch docs + query warehouse | Both files |

## Product-Specific Queries

If the query is about a **product feature** (operators, integrations, SDKs):

→ See `discovery-docs.md` - fetch documentation to discover all related components before querying warehouse.

**Why docs first:** ILIKE patterns only find name matches. Documentation reveals feature groupings - components that belong together but don't share naming patterns.

## General Data Queries

If the query is about general data (customers, metrics, etc.):

→ See `discovery-warehouse.md` - patterns for finding tables, handling large datasets, value discovery.
