# List schemas from configured databases (kepler-cli compatible format)
import json

_configured_dbs = {{.DatabaseList}}

# Build a single UNION ALL query across all databases
_union_parts = []
for _db in _configured_dbs:
    _union_parts.append(f"""
        SELECT 
            '{_db}' as "database",
            SCHEMA_NAME as "schema_name",
            (SELECT COUNT(*) FROM {_db}.INFORMATION_SCHEMA.TABLES t 
             WHERE t.TABLE_SCHEMA = s.SCHEMA_NAME) as "table_count"
        FROM {_db}.INFORMATION_SCHEMA.SCHEMATA s
        WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA')""")

_query = " UNION ALL ".join(_union_parts) + " ORDER BY \"database\", \"schema_name\""

# Execute single query and group results by database
_all_schemas = {}
try:
    _result_df = run_sql(_query, limit=-1)
    for _row in _result_df.iter_rows(named=True):
        _db = _row.get("database", "")
        if _db not in _all_schemas:
            _all_schemas[_db] = []
        _all_schemas[_db].append({
            "name": _row.get("schema_name", ""),
            "table_count": _row.get("table_count", 0)
        })
except Exception as e:
    print(f"Error querying schemas: {e}")

print(json.dumps(_all_schemas, indent=2, default=str))





