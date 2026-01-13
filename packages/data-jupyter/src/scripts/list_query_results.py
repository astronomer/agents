# List all saved query results in the session
import json
from pathlib import Path

_session_data_dir = "{{.SessionDataDir}}"
_data_dir = Path(_session_data_dir)

if not _data_dir.exists():
    print("No query results saved yet.")
else:
    _parquet_files = sorted(_data_dir.glob("query_*.parquet"))
    
    if not _parquet_files:
        print("No query results saved yet.")
    else:
        print(f"📁 Saved query results ({len(_parquet_files)} files):")
        print(f"   Directory: {_data_dir}")
        print("-" * 60)
        
        for _pf in _parquet_files:
            _query_num = _pf.stem.replace("query_", "")
            _metadata_path = _data_dir / f"{_pf.stem}.json"
            
            if _metadata_path.exists():
                with open(_metadata_path, 'r') as _f:
                    _meta = json.load(_f)
                _query_preview = _meta.get("query", "")[:50]
                if len(_meta.get("query", "")) > 50:
                    _query_preview += "..."
                print(f"\n  {_pf}")
                print(f"    Rows: {_meta.get('row_count', 'N/A')}")
                print(f"    Columns: {', '.join(_meta.get('columns', []))[:60]}...")
                print(f"    Query: {_query_preview}")
            else:
                # Just show file info without metadata
                import polars as pl
                try:
                    _df = pl.read_parquet(_pf)
                    print(f"\n  {_pf}")
                    print(f"    Rows: {len(_df)}")
                    print(f"    Columns: {', '.join(_df.columns)[:60]}...")
                except Exception as _e:
                    print(f"\n  {_pf} (error reading: {_e})")
        
        print("\n" + "-" * 60)
        print("Use get_query_result(query_num=N) to load a specific result.")





