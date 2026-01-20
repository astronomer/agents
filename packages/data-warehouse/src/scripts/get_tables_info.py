# Get information for multiple tables (batch version of get_table_info)
import json

_table_list = {{.TableList}}

_tables_query = """
SELECT
    TABLE_CATALOG as "database",
    TABLE_SCHEMA as "schema",
    TABLE_NAME as "name",
    TABLE_TYPE as "entity_type",
    ROW_COUNT as "row_count",
    BYTES as "size_bytes",
    COMMENT as "description"
FROM {{.Database}}.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '{{.Schema}}' AND TABLE_NAME IN (""" + ", ".join(f"'{t}'" for t in _table_list) + ")"

_columns_query = """
SELECT
    TABLE_NAME as "table_name",
    COLUMN_NAME as "name",
    DATA_TYPE as "type",
    IS_NULLABLE as "nullable",
    COLUMN_DEFAULT as "default_value",
    COMMENT as "description",
    ORDINAL_POSITION as "position"
FROM {{.Database}}.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '{{.Schema}}' AND TABLE_NAME IN (""" + ", ".join(f"'{t}'" for t in _table_list) + """)
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""

# Get table metadata and column information in parallel
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=2) as _executor:
    _tables_future = _executor.submit(run_sql, _tables_query, limit=-1)
    _columns_future = _executor.submit(run_sql, _columns_query, limit=-1)
    _tables_df = _tables_future.result()
    _columns_df = _columns_future.result()

# Group columns by table name
_columns_by_table = {}
for _col in _columns_df.iter_rows(named=True):
    _tbl_name = _col.get("table_name", "")
    if _tbl_name not in _columns_by_table:
        _columns_by_table[_tbl_name] = []
    _col_info = {
        "name": _col.get("name", ""),
        "type": _col.get("type", "UNKNOWN"),
        "nullable": _col.get("nullable", "YES") == "YES",
    }
    if _col.get("description"):
        _col_info["description"] = _col["description"]
    if _col.get("default_value"):
        _col_info["default"] = _col["default_value"]
    _columns_by_table[_tbl_name].append(_col_info)

# Build result for each found table
_found_tables = []
_found_names = set()
for _table_row in _tables_df.iter_rows(named=True):
    _name = _table_row.get("name", "")
    _found_names.add(_name)

    _table_info = {
        "name": _name,
        "database": "{{.Database}}",
        "schema": "{{.Schema}}",
        "full_name": f"{{.Database}}.{{.Schema}}.{_name}",
        "entity_type": _table_row.get("entity_type", "TABLE").lower(),
        "columns": _columns_by_table.get(_name, []),
    }

    if _table_row.get("description"):
        _table_info["description"] = _table_row["description"]
    if _table_row.get("row_count") is not None:
        _table_info["row_count"] = _table_row["row_count"]
    if _table_row.get("size_bytes") is not None:
        _table_info["size_bytes"] = _table_row["size_bytes"]

    _found_tables.append(_table_info)

# Determine which tables were not found
_not_found = [t for t in _table_list if t not in _found_names]

_result = {
    "database": "{{.Database}}",
    "schema": "{{.Schema}}",
    "tables": _found_tables,
    "not_found": _not_found,
}

print(json.dumps(_result, indent=2, default=str))
