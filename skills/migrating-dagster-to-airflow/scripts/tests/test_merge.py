"""Runtime-first reconciliation tests for the redesigned inventory.py.

Runtime records are the primary inventory; each is grafted with a matching
static site's syntactic extras. Static-only sites are appended flagged
`not_in_runtime`. Family matching is a stable structural heuristic, not a table."""

import inventory


def _rt(kind, name, **params):
    return {
        "kind": kind,
        "name": name,
        "classification": "pending",
        "note": "",
        "params": params,
        "source_edges": [],
        "status": "pending",
        "source": "runtime",
    }


def _st(kind, name, **extra):
    r = {
        "kind": kind,
        "name": name,
        "classification": "pending",
        "note": "",
        "params": {},
        "source_edges": [],
        "status": "pending",
    }
    r.update(extra)
    return r


def test_runtime_primary_static_grafted():
    runtime = [_rt("asset", "AssetKey(['users'])")]
    static = [
        _st(
            "asset",
            "users",
            source_edges=[{"upstream": "raw", "io_manager": None}],
            location="a.py:1",
        )
    ]
    combined = inventory._merge_runtime_first(runtime, static)
    assert len(combined) == 1
    assert combined[0]["source"] == "runtime"  # runtime is primary
    assert combined[0]["source_edges"]  # static extras grafted on
    assert combined[0]["static_location"] == "a.py:1"
    assert not any(r.get("not_in_runtime") for r in combined)


def test_static_only_site_is_supplemented():
    # a static site the runtime enumeration does not surface (an op lives inside
    # a job, not a top-level object) is kept, flagged not_in_runtime
    runtime = [_rt("asset", "users")]
    static = [_st("op", "my_op", location="o.py:1")]
    combined = inventory._merge_runtime_first(runtime, static)
    assert len(combined) == 2
    only = [r for r in combined if r.get("not_in_runtime")]
    assert len(only) == 1 and only[0]["kind"] == "op"


def test_job_family_alignment():
    # runtime kind `job` aligns with static `define_asset_job` via coarse family
    runtime = [_rt("job", "weekly_job")]
    static = [_st("define_asset_job", "weekly_job", location="d.py:1")]
    combined = inventory._merge_runtime_first(runtime, static)
    assert len(combined) == 1 and combined[0]["kind"] == "job"
    assert not any(r.get("not_in_runtime") for r in combined)


def test_check_does_not_align_with_asset():
    # a check and an asset of the same name are different families
    runtime = [_rt("asset_check", "row_check")]
    static = [_st("asset", "row_check", location="a.py:1")]
    combined = inventory._merge_runtime_first(runtime, static)
    assert len(combined) == 2
    assert any(r.get("not_in_runtime") and r["kind"] == "asset" for r in combined)


def test_coarse_family_heuristic():
    f = inventory._coarse_family
    assert f("asset_check") == "check" and f("multi_asset_check") == "check"
    assert f("asset_job") == "job" and f("define_asset_job") == "job"
    assert f("ScheduleDefinition") == "schedule"
    assert f("run_status_sensor") == "sensor"
    assert f("multi_asset") == "asset" and f("dbt_assets") == "asset"
    assert (
        f("DuckDBPandasIOManager") == "resource"
        and f("DbtCloudWorkspace") == "resource"
    )


def test_runtime_check_pairs_extracts_check_name():
    class _Key:
        def __init__(self, name, asset):
            self.name = name
            self.asset_key = asset

    class _ChecksDef:
        def __init__(self, keys):
            self.check_keys = keys

    obj = _ChecksDef([_Key("row_count_positive", "AssetKey(['us_sector_etfs_raw'])")])
    assert inventory._runtime_check_pairs(obj) == [
        ("row_count_positive", "us_sector_etfs_raw")
    ]


def test_dagster_import_resolution():
    # module alias, from-import, aliased from-import, builder form
    mod = {"dg": "dagster", "ddbt": "dagster_dbt"}
    sym = {
        "asset": ("dagster", "asset"),
        "a": ("dagster", "asset"),
        "FreshnessPolicy": ("dagster", "FreshnessPolicy"),
    }
    import ast

    def resolve(src):
        node = ast.parse(src, mode="eval").body
        return inventory._resolve_dagster_symbol(node, mod, sym)

    assert resolve("dg.asset") == "asset"
    assert resolve("dg.multi_asset()") == "multi_asset"
    assert resolve("asset") == "asset"
    assert resolve("a") == "asset"  # aliased import
    assert resolve("FreshnessPolicy.cron()") == "FreshnessPolicy"  # builder form
    assert resolve("ddbt.dbt_assets") == "dbt_assets"  # integration package
    assert resolve("pandas.DataFrame") is None  # non-dagster origin
