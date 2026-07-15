"""Shared fixtures for the migration-scripts test suite.

Self-contained: builds tiny synthetic Dagster projects under tmp_path so the
suite has no dependency on the repo's test-projects/ or example-migrations/ (which stay behind when
this skill subtree moves to astronomer/agents). The scripts are imported by
adding the parent scripts/ directory to sys.path.
"""

import sys
from pathlib import Path

import pytest

# Make the scripts (one level up from tests/) importable as top-level modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# A minimal Dagster project exercising the constructs the scanner must catch.
# It is never imported or executed: the static scan only parses text, so the
# `dagster` imports and decorators need not resolve.
_ASSETS = """\
import dagster as dg
from dagster import asset, multi_asset, AssetOut, AssetSpec, op


@asset
def raw_sales(context):
    return 1


@asset(io_manager_key="warehouse")
def daily_sales(context, raw_sales):
    # raw_sales is a signature-inferred upstream edge
    return raw_sales


@multi_asset(can_subset=True, outs={"out_a": AssetOut(), "out_b": AssetOut()})
def multi_outs():
    yield None


@multi_asset(specs=[AssetSpec("spec_x", deps=["raw_sales"]), AssetSpec("spec_y")])
def multi_specs():
    yield None


@op
def legacy_op(x):
    return x


@solid
def old_solid(x):
    return x
"""

_RESOURCES = """\
import dagster as dg


class BaseParquetIO(dg.ConfigurableIOManager):
    def handle_output(self, context, obj):
        pass

    def load_input(self, context):
        return None


class DerivedParquetIO(BaseParquetIO):
    prefix: str = "x"
"""

_FRESHNESS = """\
import dagster as dg

NEW_FP = dg.FreshnessPolicy.cron(deadline_cron="0 9 * * *")
LEGACY_FP = dg.LegacyFreshnessPolicy(maximum_lag_minutes=120)
"""

_CLOUD = """\
import os

IS_BRANCH = os.environ.get("DAGSTER_CLOUD_IS_BRANCH_DEPLOYMENT", "")
"""

_DEFINITIONS = """\
import dagster as dg
from dagster import Definitions, ScheduleDefinition, define_asset_job


warehouse_job = define_asset_job("warehouse_job", selection="*")

resources = {
    "io_manager": DerivedParquetIO(),
    "warehouse": dg.DuckDBPandasIOManager(database="x"),
}

defs = Definitions(
    schedules=[ScheduleDefinition(job=warehouse_job, cron_schedule="@weekly")],
    resources=resources,
)
"""

_BRANCHED = """\
import os
import dagster as dg
from dagster import define_asset_job
from dagster import sensor as sensor_decorator  # aliased import
from dagster_dbt import dbt_cloud_assets          # integration package origin


# name= kwarg / first-positional should win over the Python binding name
named_job = define_asset_job(name="the_real_job_name", selection="*")


# aliased decorator must still resolve to the dagster symbol `sensor`
@sensor_decorator(name="the_real_sensor_name")
def binding_sensor_name(context):
    ...


# import-time env branch selecting an alternate integration: BOTH branches must
# produce records, each flagged with its condition.
if os.getenv("ORCH_MODE") == "cloud":

    @dbt_cloud_assets(workspace=None)
    def cloud_models(context):
        ...

else:

    @dg.asset
    def local_only_asset():
        return 1
"""

_DEFS_YAML = """\
type: my_lib.ComponentA
attributes:
  cron: "@daily"
  key: alpha
---
type: my_lib.ComponentB
attributes:
  key: beta
"""


@pytest.fixture()
def synth_project(tmp_path):
    """Write the synthetic Dagster project and return its root path."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "assets.py").write_text(_ASSETS)
    (pkg / "resources.py").write_text(_RESOURCES)
    (pkg / "freshness.py").write_text(_FRESHNESS)
    (pkg / "cloud.py").write_text(_CLOUD)
    (pkg / "definitions.py").write_text(_DEFINITIONS)
    (pkg / "branched.py").write_text(_BRANCHED)
    comps = pkg / "components"
    comps.mkdir()
    (comps / "defs.yaml").write_text(_DEFS_YAML)
    return tmp_path
