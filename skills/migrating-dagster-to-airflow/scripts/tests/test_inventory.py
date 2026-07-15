"""Static-scan tests for the redesigned (import-based) inventory.py.

The scanner no longer curates a symbol table: it records any decorator/call whose
origin resolves to a dagster* module, kind = the raw dagster symbol name, and
leaves classification = "pending" for the agent."""

import inventory


def _scan(root):
    return inventory.build_manifest(root, use_runtime=False)


def _by_kind(records, kind):
    return [r for r in records if r["kind"] == kind]


def _names(records, kind):
    return sorted(r["name"] for r in records if r["kind"] == kind)


def test_import_based_detection_kinds(synth_project):
    m = _scan(synth_project)
    recs = list(m["units"].values())
    assert m["modes"] == ["static"]
    # kinds are the RAW dagster symbol names (no internal remapping)
    assert {"daily_sales", "raw_sales", "local_only_asset"} <= set(
        _names(recs, "asset")
    )
    assert _names(recs, "multi_asset") == ["multi_outs", "multi_specs"]
    assert _by_kind(recs, "op") and _by_kind(recs, "define_asset_job")
    assert _by_kind(recs, "component_instance")


def test_classification_is_pending_everywhere(synth_project):
    # the scanner stops proposing MECH/JUDG/REDESIGN/NONE; the agent classifies
    m = _scan(synth_project)
    assert all(r["classification"] == "pending" for r in list(m["units"].values()))
    assert set(m["legend"]) >= {"MECH", "JUDG", "REDESIGN", "NONE", "pending"}


def test_counts_are_per_kind(synth_project):
    m = _scan(synth_project)
    assert m["counts"].get("asset", 0) >= 3
    assert m["total"] == len(list(m["units"].values()))


def test_bare_from_import_decorator(synth_project):
    # `from dagster import asset` then `@asset` resolves to kind "asset"
    m = _scan(synth_project)
    assert "raw_sales" in _names(list(m["units"].values()), "asset")


def test_module_alias_decorator(synth_project):
    # `import dagster as dg` then `@dg.asset` resolves to kind "asset"
    m = _scan(synth_project)
    assert "local_only_asset" in _names(list(m["units"].values()), "asset")


def test_aliased_decorator_import(synth_project):
    # `from dagster import sensor as sensor_decorator` then `@sensor_decorator`
    # must still resolve to the dagster symbol `sensor` (the old blind spot)
    m = _scan(synth_project)
    assert "the_real_sensor_name" in _names(list(m["units"].values()), "sensor")


def test_integration_package_origin(synth_project):
    # `from dagster_dbt import dbt_cloud_assets` resolves (dagster_* origin)
    m = _scan(synth_project)
    assert "cloud_models" in _names(list(m["units"].values()), "dbt_cloud_assets")


def test_deprecated_spelling_flagged(synth_project):
    # DEPRECATED_SYMBOLS (the stable past) still flags spelling + note
    m = _scan(synth_project)
    solids = _by_kind(list(m["units"].values()), "solid")
    assert len(solids) == 1 and solids[0]["spelling"] == "deprecated"
    assert solids[0]["note"]


def test_declared_name_prefers_kwarg_over_binding(synth_project):
    m = _scan(synth_project)
    assert "the_real_job_name" in _names(list(m["units"].values()), "define_asset_job")
    assert "the_real_sensor_name" in _names(list(m["units"].values()), "sensor")


def test_custom_io_manager_subclass_chain(synth_project):
    m = _scan(synth_project)
    io = {r["name"] for r in _by_kind(list(m["units"].values()), "io_manager")}
    assert {"BaseParquetIO", "DerivedParquetIO"} <= io


def test_resource_dict_key_naming(synth_project):
    # a dagster IO-manager constructed as a resources-dict value is named by key
    m = _scan(synth_project)
    assert "warehouse" in _names(list(m["units"].values()), "DuckDBPandasIOManager")


def test_multi_asset_outputs_are_fields(synth_project):
    m = _scan(synth_project)
    outs = {
        r["name"]: [o["name"] for o in r.get("outputs", [])]
        for r in _by_kind(list(m["units"].values()), "multi_asset")
    }
    assert outs["multi_outs"] == ["out_a", "out_b"]
    # output names are not minted as standalone asset units
    assert not ({"out_a", "out_b"} & set(_names(list(m["units"].values()), "asset")))


def test_signature_edges_and_producer_io_manager(synth_project):
    m = _scan(synth_project)
    daily = next(r for r in list(m["units"].values()) if r["name"] == "daily_sales")
    e = daily["source_edges"][0]
    assert e["upstream"] == "raw_sales" and e.get("from") == "signature"
    assert e["io_manager"] == "io_manager" and e["io_manager_source"] == "producer"
    assert e["consumer_io_manager"] == "warehouse"


def test_both_conditional_branches_visible(synth_project):
    m = _scan(synth_project)
    by_name = {r["name"]: r for r in list(m["units"].values())}
    assert "cloud_models" in by_name and "local_only_asset" in by_name
    assert isinstance(by_name["cloud_models"].get("conditional"), str)
    assert "not (" in by_name["local_only_asset"].get("conditional", "")


def test_multidoc_component_yaml(synth_project):
    m = _scan(synth_project)
    assert _names(list(m["units"].values()), "component_instance") == [
        "my_lib.ComponentA",
        "my_lib.ComponentB",
    ]


def test_dagster_cloud_ref_and_coupling_field(synth_project):
    m = _scan(synth_project)
    assert _by_kind(list(m["units"].values()), "branch_env_ref")
    assert m["dbt_manifest_coupling"] == []


def test_freshness_policy_both_spellings(synth_project):
    # import-based: kind is the raw symbol; the agent classifies legacy vs GA
    m = _scan(synth_project)
    kinds = {r["kind"] for r in list(m["units"].values())}
    assert {"FreshnessPolicy", "LegacyFreshnessPolicy"} <= kinds


def test_helper_calls_not_recorded(synth_project):
    # AssetOut inside outs=, EnvVar defaults, etc. are not definition sites
    m = _scan(synth_project)
    kinds = {r["kind"] for r in list(m["units"].values())}
    assert not (kinds & {"AssetOut", "AssetSpec", "AssetIn", "get_dagster_logger"})


def test_units_shape_for_downstream_scripts(synth_project):
    m = _scan(synth_project)
    assert m["units"] and all(":" in uid for uid in m["units"])
    assert all(
        "source_edges" in rec and "edges" not in rec for rec in m["units"].values()
    )
