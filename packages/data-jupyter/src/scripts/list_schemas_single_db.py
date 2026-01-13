# List schemas in database (kepler-cli compatible format)
import json

_query = """
SELECT 
    CATALOG_NAME as "database",
    SCHEMA_NAME as "schema_name",
    (SELECT COUNT(*) FROM {{.Database}}.INFORMATION_SCHEMA.TABLES t 
     WHERE t.TABLE_SCHEMA = s.SCHEMA_NAME) as "table_count"
FROM {{.Database}}.INFORMATION_SCHEMA.SCHEMATA s
WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA')
ORDER BY SCHEMA_NAME
"""

_result_df = run_sql(_query, limit=-1)

# Build structured output
_schemas = {}
for _row in _result_df.iter_rows(named=True):
    _db = _row.get("database", "{{.Database}}")
    _schema = _row.get("schema_name", "")
    _count = _row.get("table_count", 0)
    
    if _db not in _schemas:
        _schemas[_db] = []
    _schemas[_db].append({"name": _schema, "table_count": _count})

print(json.dumps(_schemas, indent=2, default=str))





