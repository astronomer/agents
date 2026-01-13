# List schemas from configured databases (kepler-cli compatible format)
import json

_configured_dbs = {{.DatabaseList}}

# Collect schema info from each database
_all_schemas = {}
for _db in _configured_dbs:
    try:
        _query = f"""
        SELECT 
            '{_db}' as "database",
            SCHEMA_NAME as "schema_name",
            (SELECT COUNT(*) FROM {_db}.INFORMATION_SCHEMA.TABLES t 
             WHERE t.TABLE_SCHEMA = s.SCHEMA_NAME) as "table_count"
        FROM {_db}.INFORMATION_SCHEMA.SCHEMATA s
        WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA')
        ORDER BY SCHEMA_NAME
        """
        _result_df = run_sql(_query, limit=-1)
        
        _schemas_list = []
        for _row in _result_df.iter_rows(named=True):
            _schemas_list.append({
                "name": _row.get("schema_name", ""),
                "table_count": _row.get("table_count", 0)
            })
        
        if _schemas_list:
            _all_schemas[_db] = _schemas_list
    except Exception as e:
        print(f"Could not access {_db}: {e}")

print(json.dumps(_all_schemas, indent=2, default=str))





