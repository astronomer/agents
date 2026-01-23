# Execute SQL query from file and optionally save to parquet
import json as _json
from pathlib import Path

_sql_file_path = "{{.SQLFilePath}}"
_limit = {{.Limit}}
_save_parquet = {{.SaveParquet}}
_query_num = {{.QueryNum}}
_session_data_dir = "{{.SessionDataDir}}"

# Read query from file (avoids all escaping issues)
with open(_sql_file_path, 'r', encoding='utf-8') as _f:
    _query = _f.read()

# Execute the query
_result_df = run_sql(_query, limit=_limit, return_df=True)

# Print the result
print(_result_df)

# Save to parquet if requested and we have results
_parquet_path = None
if _save_parquet and _result_df is not None and len(_result_df) > 0:
    import polars as pl
    
    _data_dir = Path(_session_data_dir)
    _data_dir.mkdir(parents=True, exist_ok=True)
    
    _parquet_path = _data_dir / f"query_{_query_num:03d}.parquet"
    
    # Write parquet file (polars or pandas)
    if isinstance(_result_df, pl.DataFrame):
        _result_df.write_parquet(_parquet_path, compression="snappy")
    elif hasattr(_result_df, 'to_parquet'):
        # pandas DataFrame
        _result_df.to_parquet(_parquet_path, compression="snappy", index=False)
    
    # Save metadata
    _metadata = {
        "query_num": _query_num,
        "query": _query,
        "row_count": len(_result_df),
        "columns": list(_result_df.columns),
        "file": f"query_{_query_num:03d}.parquet",
        "sql_file": _sql_file_path
    }
    _metadata_path = _data_dir / f"query_{_query_num:03d}.json"
    with open(_metadata_path, 'w') as _f:
        _json.dump(_metadata, _f, indent=2)
    
    print(f"\n💾 Saved to {_parquet_path} ({len(_result_df)} rows)")
