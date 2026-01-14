# List tables in a schema
import json

_db = "{{.Database}}"
_schema = "{{.Schema}}"

_query = f"""
SELECT 
    TABLE_NAME as "table_name",
    TABLE_TYPE as "table_type",
    ROW_COUNT as "row_count",
    COMMENT as "comment"
FROM {_db}.INFORMATION_SCHEMA.TABLES
WHERE UPPER(TABLE_SCHEMA) = UPPER('{_schema}')
ORDER BY TABLE_NAME
"""

_result_df = run_sql(_query, limit=-1)

# Build structured output
_tables = []
for _row in _result_df.iter_rows(named=True):
    _table = {
        "name": _row.get("table_name", ""),
        "type": _row.get("table_type", ""),
    }
    if _row.get("row_count") is not None:
        _table["row_count"] = _row.get("row_count")
    if _row.get("comment"):
        _table["comment"] = _row.get("comment")
    _tables.append(_table)

_output = {"database": _db, "schema": _schema, "tables": _tables, "count": len(_tables)}

if len(_tables) == 0:
    # Check if schema exists
    _schema_check = f"""
    SELECT SCHEMA_NAME 
    FROM {_db}.INFORMATION_SCHEMA.SCHEMATA 
    WHERE UPPER(SCHEMA_NAME) = UPPER('{_schema}')
    """
    _schema_df = run_sql(_schema_check, limit=1)
    if len(_schema_df) == 0:
        _output["error"] = f"Schema '{_schema}' not found in database '{_db}'"
    else:
        _output["message"] = "Schema exists but contains no tables"

print(json.dumps(_output, indent=2, default=str))
