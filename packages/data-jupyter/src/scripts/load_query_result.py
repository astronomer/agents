# Load a saved query result from parquet file
import polars as pl
from pathlib import Path

_session_data_dir = "{{.SessionDataDir}}"
_query_num = {{.QueryNum}}

_data_dir = Path(_session_data_dir)
_parquet_path = _data_dir / f"query_{_query_num:03d}.parquet"

if not _parquet_path.exists():
    print(f"Error: Query result not found: {_parquet_path}")
    print(f"Use list_query_results to see available results.")
else:
    _df = pl.read_parquet(_parquet_path)
    print(f"Loaded {_parquet_path} ({len(_df)} rows, {len(_df.columns)} columns)")
    print(_df)





