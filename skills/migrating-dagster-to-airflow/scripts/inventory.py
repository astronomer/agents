#!/usr/bin/env python3
"""Read-only inventory scanner for a Dagster project.

First step of every Dagster to Airflow 3 migration. Emits one JSON manifest, one
record per definition. Architecture (redesigned to stop tracking Dagster's
fast-rotating API surface by hand):

  RUNTIME-FIRST (primary): with `--runtime`, import the project's Definitions in
  the project's own interpreter and enumerate the RESOLVED objects (assets with
  keys/deps/partitions/automation/io_manager_key, jobs, schedules, sensors,
  checks, resources) via dagster's own public APIs. This tracks any Dagster
  version automatically. Run the scanner WITH the project's venv python, e.g.
    <project-venv>/bin/python scripts/inventory.py <root> --runtime
    uv run python scripts/inventory.py <root> --runtime
  On failure the static manifest still stands and a loud STATIC-ONLY banner plus
  a top-level `runtime_error` field are emitted.

  STATIC (completeness net): a thin, import-based scan. Per file it tracks what
  is imported from dagster* modules (including aliases: `import dagster as dg`,
  `from dagster import asset as a`) and records any decorator/call whose origin
  resolves to a dagster* module as a definition site, kind = the original dagster
  symbol name. No curated symbol table, so aliased decorators and new APIs are
  caught for free. Integration packages (dagster_dbt etc.) resolve the same way.

CLASSIFICATION is the AGENT's job, not the scanner's: every record ships
`classification: "pending"`; the driving agent classifies each against
reference/mapping.md during Phase 1 and writes MECH/JUDG/REDESIGN/NONE back.

Usage: inventory.py <project_root> [--runtime] [--out manifest.json]
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# The stable, non-rotting past: legacy spellings never change. Used only to flag
# spelling=deprecated and attach a note; NOT to decide what is a definition.
DEPRECATED_SYMBOLS = {
    "solid": "legacy solid; modern @op",
    "pipeline": "legacy pipeline; modern @job",
    "composite_solid": "legacy composite_solid; modern @graph",
    "lambda_solid": "legacy lambda_solid; modern @op",
    "repository": "classic @repository; modern Definitions",
    "ModeDefinition": "legacy mode; modern resources",
    "PresetDefinition": "legacy preset; modern config on job",
    "hourly_schedule": "legacy partitioned schedule decorator",
    "daily_schedule": "legacy partitioned schedule decorator",
    "weekly_schedule": "legacy partitioned schedule decorator",
    "monthly_schedule": "legacy partitioned schedule decorator",
    "SourceAsset": "SourceAsset; modern AssetSpec external asset",
    "load_assets_from_dbt_project": "legacy dbt loader; modern @dbt_assets",
    "load_assets_from_dbt_manifest": "legacy dbt loader; modern @dbt_assets",
    "dbt_cli_resource": "legacy dbt_cli_resource; modern DbtCliResource",
    "fivetran_resource": "legacy op-based fivetran",
    "FivetranResource": "legacy fivetran resource",
    "airbyte_resource": "legacy op-based airbyte",
    "AirbyteResource": "legacy airbyte resource",
    "build_fivetran_assets": "legacy op-based; modern _definitions",
    "build_airbyte_assets": "legacy op-based; modern _definitions",
    "databricks_pyspark_step_launcher": "step launcher superseded by Pipes",
    "emr_pyspark_step_launcher": "step launcher superseded by Pipes",
    "build_snowflake_io_manager": "legacy builder; modern SnowflakeIOManager class",
    "build_duckdb_io_manager": "legacy builder; modern DuckDBIOManager class",
    "build_bigquery_io_manager": "legacy builder; modern BigQueryIOManager class",
    "snowflake_pandas_io_manager": "deprecated fn; modern SnowflakePandasIOManager",
    "duckdb_pandas_io_manager": "deprecated fn; modern DuckDBPandasIOManager",
    "bigquery_pandas_io_manager": "deprecated fn; modern BigQueryPandasIOManager",
    "AutoMaterializePolicy": "deprecated; normalize to AutomationCondition",
    "auto_materialize_policy": "deprecated kwarg spelling",
    "static_partitioned_config": "partitioned-config era",
    "dynamic_partitioned_config": "partitioned-config era",
}

# Base classes that make a user `class X(...)` a resource / IO manager. Base
# class names are stable API (they do not rotate like the full symbol surface),
# so this small set is safe to keep; transitive subclasses resolve via the
# package-wide inheritance map.
IO_MANAGER_BASES = {
    "IOManager",
    "ConfigurableIOManager",
    "ConfigurableIOManagerFactory",
    "UPathIOManager",
    "InputManager",
}
RESOURCE_BASES = {"ConfigurableResource", "ConfigurableResourceFactory"}

# Library builder helpers recorded even inside a factory body (every other call
# inside a `def defs(): return Definitions(...)` factory is skipped, so DOP's
# per-module container pattern does not mint phantom units).
FACTORY_HELPER_SYMBOLS = {"make_slack_on_run_failure_sensor", "make_values_resource"}

# Well-known dagster UTILITIES that resolve from a dagster* module but never
# produce a definition (loggers, context/test builders, value wrappers). This is
# a short DENYLIST of stable helpers, not the old definition allowlist: these
# names do not rotate, and excluding them keeps the import-based net from
# recording `logger = get_dagster_logger()` and friends as phantom units.
DAGSTER_NON_DEFINITIONS = {
    "get_dagster_logger",
    "get_current_context",
    "build_op_context",
    "build_asset_context",
    "build_resources",
    "build_init_resource_context",
    "materialize",
    "materialize_to_memory",
    "instance_for_test",
}

_DEFAULT_IO_MANAGER_KEY = "io_manager"  # Dagster's default IO manager resource key

LEGEND = {
    "MECH": "mechanical translation, low risk",
    "JUDG": "needs per-instance judgment",
    "REDESIGN": "semantics differ; redesign, not translate",
    "NONE": "no Airflow equivalent; documented mitigation required",
    "pending": "not yet classified; the driving agent fills this from mapping.md",
    "status": "migration state; owned by status.py, never hand-edited",
}


# ---------------------------------------------------------------- AST helpers


def _callee_name(node):
    """Bare symbol name of a decorator or call target, or None."""
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _kwargs_present(call):
    """Map keyword-name -> rendered value for a Call node's keyword args."""
    out = {}
    if not isinstance(call, ast.Call):
        return out
    for kw in call.keywords:
        if kw.arg is not None:
            out[kw.arg] = _render(kw.value)
    return out


def _render(node, limit=120):
    """Best-effort short rendering: literal value if simple, else source text."""
    try:
        val = ast.literal_eval(node)
        if isinstance(val, (int, float, bool, str, type(None))):
            return val
    except Exception:
        pass
    return _safe_unparse(node, limit)


def _safe_unparse(node, limit=120):
    """Short source text for a node, never raising."""
    try:
        text = ast.unparse(node)
    except Exception:
        return "<expr>"
    return text if len(text) <= limit else text[:limit] + "..."


def _annotation_name(ann):
    """Bare name of a parameter annotation (Name, Attribute, or subscript base)."""
    if isinstance(ann, ast.Subscript):
        ann = ann.value
    if isinstance(ann, ast.Name):
        return ann.id
    if isinstance(ann, ast.Attribute):
        return ann.attr
    return None


_NON_ASSET_PARAMS = {"self", "context", "config"}
# Annotation suffixes that mark a param as an injected resource/client, not an
# upstream asset. Tight on purpose: a false resource-edge is pruned at planning
# (visible), but dropping a real asset edge is a silent omission.
_RESOURCE_ANN_SUFFIXES = ("Resource", "Client", "Config", "Connection", "Session")


def _signature_deps(func_node):
    """Upstream asset names inferred from an asset function's parameters (syntax,
    not API): non-context/config/resource params name upstream assets."""
    args = func_node.args
    deps = []
    for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        if a.arg in _NON_ASSET_PARAMS:
            continue
        ann = _annotation_name(a.annotation)
        if ann and ann.endswith(_RESOURCE_ANN_SUFFIXES):
            continue
        deps.append(a.arg)
    return deps


def _multi_asset_outputs(kwargs):
    """Output names declared by @multi_asset (outs dict keys + AssetSpec names)."""
    names = []
    outs = kwargs.get("outs")
    if isinstance(outs, str):
        names += re.findall(r"['\"]([A-Za-z_]\w*)['\"]\s*:", outs)
    specs = kwargs.get("specs")
    if isinstance(specs, str):
        names += re.findall(r"AssetSpec\(\s*['\"]([A-Za-z_]\w*)['\"]", specs)
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _declared_name(kwargs, node, kind, fallback):
    """The definition's DECLARED name (name= kwarg, then a name-positional for
    define_asset_job), so static and runtime keys align. Else the fallback."""
    n = kwargs.get("name")
    if isinstance(n, str) and n.strip():
        return n.strip()
    if kind == "define_asset_job" and isinstance(node, ast.Call) and node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return fallback


def _record_name(node, kind, fallback):
    """Name for a call-constructed record: assigned var, then resource dict key."""
    assigned = getattr(node, "_dagster_assign_target", None)
    if assigned:
        return assigned
    if _coarse_family(kind) == "resource":
        key = getattr(node, "_dagster_dict_key", None)
        if key:
            return key
    return fallback


# --------------------------------------------------- dagster import resolution


def _is_dagster_module(mod):
    return bool(mod) and (
        mod == "dagster" or mod.startswith("dagster.") or mod.startswith("dagster_")
    )


def _resolve_dagster_symbol(func_node, mod_aliases, sym_imports):
    """The original dagster symbol name a decorator/call resolves to, or None.

    Handles `@asset` (from-import), `@a` (aliased from-import), `@dg.asset`
    (module alias), and builder forms `dg.FreshnessPolicy.cron(...)` (the symbol
    is the attribute nearest the module base, not the builder method)."""
    n = func_node.func if isinstance(func_node, ast.Call) else func_node
    attrs = []
    while isinstance(n, ast.Attribute):
        attrs.append(n.attr)
        n = n.value
    if not isinstance(n, ast.Name):
        return None
    origin = sym_imports.get(n.id)  # from dagster[_x] import SYM [as n]
    if origin and _is_dagster_module(origin[0]):
        return origin[1]  # ignore builder attrs after the symbol
    mod = mod_aliases.get(n.id)  # import dagster[_x] [as n]
    if mod and _is_dagster_module(mod):
        return attrs[-1] if attrs else None
    return None


# --------------------------------------------------------------- coarse family


def _coarse_family(kind):
    """Group a raw dagster symbol name into a stable structural family for merge
    dedup. Keys on role words Dagster does not rename, not a curated symbol list.
    Order matters: asset_check -> check, asset_job -> job."""
    k = str(kind).lower()
    if "check" in k:
        return "check"
    if "sensor" in k:
        return "sensor"
    if "schedule" in k:
        return "schedule"
    if "job" in k:
        return "job"
    if "iomanager" in k or "io_manager" in k:
        return "resource"
    if "resource" in k or "workspace" in k:
        return "resource"
    if "asset" in k:
        return "asset"
    return k


def _normalize_name(name):
    """Collapse a name or asset key to a comparable slug (terminal component)."""
    s = str(name).strip()
    m = re.search(r"AssetKey\(\[([^\]]*)\]\)", s)
    if m:
        parts = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
        if parts:
            s = parts[-1]
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    return s.strip().lower()


def _resolves_to(class_name, targets, imap, seen=None):
    """True if class_name transitively inherits from any base in `targets`."""
    if seen is None:
        seen = set()
    if class_name in seen:
        return False
    seen.add(class_name)
    for base in imap.get(class_name, []):
        if base in targets or _resolves_to(base, targets, imap, seen):
            return True
    return False


# --------------------------------------------------------------- static scanner


def _tag_assignments(tree):
    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            if stmt.targets and isinstance(stmt.targets[0], ast.Name):
                stmt.value._dagster_assign_target = stmt.targets[0].id


def _tag_dict_keys(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and isinstance(k.value, str)
                    and isinstance(v, ast.Call)
                ):
                    v._dagster_dict_key = k.value


def _tag_nested_calls(tree):
    """Mark Call nodes that are ARGUMENTS to another call, so helper calls used
    as arguments (AssetOut inside outs=, EnvVar in a default) are not recorded as
    their own definition sites."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Call):
                        sub._dagster_nested_call = True


class Scanner(ast.NodeVisitor):
    def __init__(self, path, source, imap=None):
        self.path = path
        self.source = source
        self.records = []
        self.imap = imap or {}
        self.mod_aliases = {}  # local alias -> module (import X as Y)
        self.sym_imports = {}  # local name -> (module, symbol) (from X import S)
        self._factory_stack = []
        self._cond_stack = []

    # -- imports ------------------------------------------------------------
    def visit_Import(self, node):
        for alias in node.names:
            self.mod_aliases[alias.asname or alias.name] = alias.name

    def visit_ImportFrom(self, node):
        if node.module:
            for alias in node.names:
                self.sym_imports[alias.asname or alias.name] = (node.module, alias.name)

    # -- resolution helpers -------------------------------------------------
    def _symbol_for(self, node):
        return _resolve_dagster_symbol(node, self.mod_aliases, self.sym_imports)

    def _ctx_fields(self):
        out = {}
        if self._factory_stack:
            out["factory"] = self._factory_stack[-1]
        if self._cond_stack:
            out["conditional"] = " and ".join(self._cond_stack)
        return out

    def _add(self, kind, name, node, kwargs=None, extra=None, deprecated=None):
        kwargs = kwargs or {}
        rec = {
            "kind": kind,
            "name": str(name).strip(),
            "location": f"{self.path}:{getattr(node, 'lineno', 0)}",
            "params": kwargs,
            "spelling": "deprecated" if deprecated else "current",
            "classification": "pending",
            "note": deprecated or "",
            "source_edges": extra.get("source_edges", []) if extra else [],
            "status": "pending",
        }
        if deprecated:
            rec["deprecated_reason"] = deprecated
        if extra:
            rec.update({k: v for k, v in extra.items() if k != "source_edges"})
        rec.update(self._ctx_fields())
        self.records.append(rec)

    # -- definitions --------------------------------------------------------
    def _visit_def(self, node):
        for dec in node.decorator_list:
            sym = self._symbol_for(dec)
            bare = _callee_name(dec)
            dep = DEPRECATED_SYMBOLS.get(bare)
            kind = sym or (bare if dep else None)
            if kind is None or kind in DAGSTER_NON_DEFINITIONS:
                continue
            kwargs = _kwargs_present(dec) if isinstance(dec, ast.Call) else {}
            extra = self._asset_extra(kind, kwargs, func_node=node)
            self._add(
                kind,
                _declared_name(kwargs, dec, kind, node.name),
                dec,
                kwargs,
                extra,
                deprecated=dep,
            )
        # descend into the body: factories define decorated defs (and call builder
        # helpers) inside a function; tag records with the enclosing function.
        self._factory_stack.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self._factory_stack.pop()

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def

    def visit_ClassDef(self, node):
        """Custom IO managers / resources defined as subclasses (transitive)."""
        direct = [_callee_name(b) for b in node.bases]
        if _resolves_to(node.name, IO_MANAGER_BASES, self.imap):
            self._add(
                "io_manager",
                node.name,
                node,
                extra={"subclass_of": next((b for b in direct if b), None)},
            )
        elif _resolves_to(node.name, RESOURCE_BASES, self.imap):
            self._add(
                "resource",
                node.name,
                node,
                extra={"subclass_of": next((b for b in direct if b), None)},
            )
        # class bodies hold fields/methods (EnvVar defaults etc.), not definitions

    def visit_Call(self, node):
        # arguments-of-a-call helper constructs are not definition sites
        if getattr(node, "_dagster_nested_call", False):
            self.generic_visit(node)
            return
        sym = self._symbol_for(node)
        bare = _callee_name(node)
        dep = DEPRECATED_SYMBOLS.get(bare)
        kind = sym or (bare if dep else None)
        if kind is not None and kind not in DAGSTER_NON_DEFINITIONS:
            # inside a factory body only record explicit builder helpers; generic
            # container calls (Definitions, define_asset_job) there just assemble
            # module-level objects and would double-count.
            if self._factory_stack and bare not in FACTORY_HELPER_SYMBOLS:
                pass
            else:
                kw = _kwargs_present(node)
                name = _declared_name(kw, node, kind, _record_name(node, kind, bare))
                self._add(kind, name, node, kw, deprecated=dep)
        self.generic_visit(node)

    def visit_If(self, node):
        # visit BOTH branches, each flagged with its condition, so an alternate
        # integration branch (dbt Cloud vs local) is never silently absent.
        test = _safe_unparse(node.test)
        self._cond_stack.append(test)
        for stmt in node.body:
            self.visit(stmt)
        self._cond_stack.pop()
        if node.orelse:
            self._cond_stack.append("not (%s)" % test)
            for stmt in node.orelse:
                self.visit(stmt)
            self._cond_stack.pop()

    def visit_Try(self, node):
        self._cond_stack.append("try")
        for stmt in node.body:
            self.visit(stmt)
        self._cond_stack.pop()
        for handler in node.handlers:
            for stmt in handler.body:
                self.visit(stmt)
        for stmt in list(node.orelse) + list(node.finalbody):
            self.visit(stmt)

    def _asset_extra(self, kind, kwargs, func_node=None):
        """Syntactic extras for asset-family definitions: source_edges (from
        deps/ins/signature) and multi_asset outputs. Generic kwarg capture is in
        `params`; nothing here interprets them (that is the agent's job)."""
        extra = {}
        if _coarse_family(kind) != "asset":
            return extra
        edges = []
        deps, ins = kwargs.get("deps"), kwargs.get("ins")
        if deps:
            edges.append({"upstream": deps, "io_manager": None})
        if ins:
            edges.append({"upstream_ins": ins, "io_manager": None})
        if not deps and not ins and func_node is not None:
            for pname in _signature_deps(func_node):
                edges.append(
                    {"upstream": pname, "io_manager": None, "from": "signature"}
                )
        if edges:
            extra["source_edges"] = edges
        outputs = _multi_asset_outputs(kwargs)
        if outputs:
            extra["outputs"] = [{"name": n} for n in outputs]
        return extra


def scan_python_file(path, root, imap=None):
    rel = path.relative_to(root)
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [
            {
                "kind": "parse_error",
                "name": path.name,
                "location": f"{rel}:0",
                "params": {"error": str(exc)},
                "spelling": "unknown",
                "classification": "pending",
                "note": "file did not parse; inspect manually",
                "source_edges": [],
                "status": "pending",
            }
        ]
    _tag_assignments(tree)
    _tag_dict_keys(tree)
    _tag_nested_calls(tree)
    scanner = Scanner(rel, source, imap=imap)
    scanner.visit(tree)
    text_findings(source, rel, scanner.records)
    return scanner.records


# --------------------------------------------------- structural text tells

TEXT_PATTERNS = [
    (
        re.compile(
            r"DAGSTER_CLOUD_(?:IS_BRANCH_DEPLOYMENT|PULL_REQUEST_ID|DEPLOYMENT_NAME)"
        ),
        "branch_env_ref",
        "branch-deploy env var IN CODE (DB naming/URLs); find and rewrite for Astro",
    ),
    (
        re.compile(r"dagster-k8s/config"),
        "k8s_config_tag",
        "per-job pod resources; map to per-task executor_config / pod_override",
    ),
    (
        re.compile(r"dagster/concurrency_key"),
        "concurrency_tag",
        "tag-based op concurrency; map to Airflow Pools",
    ),
]


def text_findings(source, rel, records):
    seen = set()
    for line_no, line in enumerate(source.splitlines(), start=1):
        for pattern, kind, note in TEXT_PATTERNS:
            match = pattern.search(line)
            if not match or (kind, match.group(0)) in seen:
                continue
            seen.add((kind, match.group(0)))
            records.append(
                {
                    "kind": kind,
                    "name": match.group(0),
                    "location": f"{rel}:{line_no}",
                    "params": {},
                    "spelling": "current",
                    "classification": "pending",
                    "note": note,
                    "source_edges": [],
                    "status": "pending",
                }
            )


def _split_yaml_docs(text):
    """Split a YAML file into (doc_text, start_line) on `---` document markers."""
    docs, cur, start = [], [], 1
    for i, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^---(\s|$)", line):
            if any(ln.strip() for ln in cur):
                docs.append(("\n".join(cur), start))
            cur, start = [], i + 1
        else:
            if not cur:
                start = i
            cur.append(line)
    if any(ln.strip() for ln in cur):
        docs.append(("\n".join(cur), start))
    return docs


def _raw_attributes_block(doc_text):
    out, capturing, base_indent = [], False, 0
    for line in doc_text.splitlines():
        if not capturing:
            m = re.match(r"^(\s*)attributes:\s*(.*)$", line)
            if m:
                capturing = True
                base_indent = len(m.group(1))
                if m.group(2).strip():
                    out.append(m.group(2).strip())
            continue
        if line.strip() == "":
            out.append("")
            continue
        if len(line) - len(line.lstrip()) <= base_indent:
            break
        out.append(line)
    block = "\n".join(out).strip()
    return block[:2000] if block else None


def _parse_component_doc(doc_text):
    type_val, attributes = None, None
    try:
        import yaml  # optional; the scanner must run without it

        data = yaml.safe_load(doc_text)
        if isinstance(data, dict):
            type_val, attributes = data.get("type"), data.get("attributes")
    except Exception:
        pass
    if type_val is None:
        m = re.search(r"^\s*type:\s*(\S+)", doc_text, re.M)
        if m:
            type_val = m.group(1).strip().strip("\"'")
    if attributes is None:
        attributes = _raw_attributes_block(doc_text)
    return type_val, attributes


def scan_component_yaml(path, root):
    """Parse a Components defs.yaml / component.yaml: one record per document."""
    rel = path.relative_to(root)
    records = []
    for doc_text, start_line in _split_yaml_docs(path.read_text(encoding="utf-8")):
        type_val, attributes = _parse_component_doc(doc_text)
        if type_val is None:
            continue
        params = {"type": type_val}
        if attributes is not None:
            params["attributes"] = attributes
        records.append(
            {
                "kind": "component_instance",
                "name": type_val,
                "location": f"{rel}:{start_line}",
                "params": params,
                "spelling": "current",
                "classification": "pending",
                "note": "unwrap YAML to the integration's mapping row; custom Component subclass ports build_defs output",
                "source_edges": [],
                "status": "pending",
            }
        )
    return records


# --------------------------------------------------------- file discovery


def _is_test_path(rel):
    """A test file or a file under a test package (relative to the project root)."""
    for part in rel.parts[:-1]:
        if part == "tests" or part.endswith("_tests") or part.startswith("test_"):
            return True
    name = rel.name
    return (
        name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
    )


def _skip_dir(path):
    return any(
        p in (".venv", "venv", "__pycache__", ".tox", "node_modules")
        for p in path.parts
    )


def _scannable_files(root):
    for path in sorted(root.rglob("*.py")):
        if _skip_dir(path) or _is_test_path(path.relative_to(root)):
            continue
        yield path


def _component_yaml_files(root):
    for pattern in ("defs.yaml", "component.yaml"):
        for path in sorted(root.rglob(pattern)):
            if not _skip_dir(path):
                yield path


def _build_inheritance_map(files):
    """Package-wide `class name -> [direct base bare-names]`, across all files."""
    imap = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                imap[node.name] = [
                    b for b in (_callee_name(base) for base in node.bases) if b
                ]
    return imap


def run_static(root):
    records = []
    files = list(_scannable_files(root))
    imap = _build_inheritance_map(files)
    for path in files:
        records.extend(scan_python_file(path, root, imap=imap))
    for path in _component_yaml_files(root):
        records.extend(scan_component_yaml(path, root))
    return records


# Cross-domain dbt-manifest coupling (load-time). Hits OUTSIDE the dbt domain
# dictate migration order (dbt first, or those edges get deferred).
DBT_COUPLING_PATTERN = re.compile(
    r"\b(get_asset_key_for_model|dbt_asset_key|DbtManifestAssetSelection)\b"
)


def _is_dbt_domain(path):
    return any("dbt" in part.lower() for part in path.parts)


def _dbt_coupling_scan(root):
    hits = []
    for path in list(_scannable_files(root)) + list(_component_yaml_files(root)):
        if _is_dbt_domain(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if DBT_COUPLING_PATTERN.search(line):
                hits.append(f"{path.relative_to(root)}:{lineno}")
    return sorted(set(hits))


# ------------------------------------------------------- runtime (primary)


def run_runtime(root):
    """Import the project and enumerate resolved Definitions. Returns
    (records, error); on any failure returns ([], reason)."""
    module_name, syspaths = _resolve_entrypoint(root)
    for d in syspaths:
        if d not in sys.path:
            sys.path.insert(0, d)
    try:
        import importlib
        import dagster as dg  # noqa: F401  guarded project-venv import
    except Exception as exc:
        return [], f"dagster not importable in this interpreter: {exc}"
    if not module_name:
        return [], (
            "could not locate a Definitions entrypoint module "
            "(checked dagster_cloud.yaml, workspace.yaml, pyproject, definitions.py)"
        )
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        return [], f"import of {module_name} failed: {exc}"
    defs = next(
        (a for a in vars(mod).values() if type(a).__name__ == "Definitions"), None
    )
    if defs is None:
        return [], f"no Definitions object found in {module_name}"
    records = []
    _enumerate(defs, module_name, records)
    return records, None


def _resolve_entrypoint(root):
    """(module_name, [sys.path dirs]) honoring dagster_cloud.yaml / workspace.yaml
    code_source + working_directory and src-layout uv packages."""
    syspaths = [str(root)]
    if (root / "src").is_dir():
        syspaths.append(str(root / "src"))
    module_name = None
    for cfg in ("dagster_cloud.yaml", "workspace.yaml"):
        p = root / cfg
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        m = re.search(r"module_name:\s*['\"]?([A-Za-z0-9_.]+)", text)
        if m and module_name is None:
            module_name = m.group(1)
        w = re.search(r"working_directory:\s*['\"]?([^\s'\"#]+)", text)
        if w:
            wdir = (root / w.group(1)).resolve()
            for d in (wdir, wdir / "src"):
                if d.is_dir() and str(d) not in syspaths:
                    syspaths.append(str(d))
    if module_name is None:
        module_name = _discover_module(root)
    else:
        top = module_name.split(".")[0]
        for cand in root.rglob(top):
            if cand.is_dir() and (cand / "__init__.py").exists():
                if str(cand.parent) not in syspaths:
                    syspaths.append(str(cand.parent))
                break
    return module_name, syspaths


def _discover_module(root):
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        m = re.search(
            r"root_module\s*=\s*[\"']([^\"']+)[\"']",
            pyproject.read_text(encoding="utf-8"),
        )
        if m:
            return m.group(1) + ".definitions"
    for candidate in root.rglob("definitions.py"):
        if not any(p in (".venv", "venv", "__pycache__") for p in candidate.parts):
            return ".".join(candidate.relative_to(root).with_suffix("").parts)
    return None


def _runtime_obj_name(obj):
    name = getattr(obj, "name", None)
    if name:
        return str(name).strip()
    for attr in ("check_keys", "keys", "check_specs"):
        val = getattr(obj, attr, None)
        if val:
            first = next(iter(val), None)
            if first is not None:
                return _normalize_name(str(first))
    return type(obj).__name__.strip()


def _runtime_check_pairs(obj):
    """(check_name, normalized_asset_key) per check in an AssetChecksDefinition."""
    items = list(
        getattr(obj, "check_specs", None) or getattr(obj, "check_keys", None) or []
    )
    pairs = []
    for it in items:
        cname = getattr(it, "name", None)
        akey = getattr(it, "asset_key", None)
        pairs.append(
            (
                str(cname).strip() if cname else None,
                _normalize_name(str(akey)) if akey is not None else None,
            )
        )
    return pairs


def _enumerate(defs, module_name, records):
    """Enumerate resolved objects via dagster's public APIs. Captures structural
    facts (deps, partitions/automation presence, io_manager_key); classification
    stays pending for the agent."""

    def emit(kind, name, params=None):
        records.append(
            {
                "kind": kind,
                "name": str(name).strip(),
                "location": f"{module_name} (runtime)",
                "params": params or {},
                "spelling": "current",
                "classification": "pending",
                "note": "",
                "source_edges": [],
                "status": "pending",
                "source": "runtime",
            }
        )

    try:
        for spec in defs.resolve_all_asset_specs():
            params = {}
            deps = getattr(spec, "deps", None)
            if deps:
                params["deps"] = [str(getattr(d, "asset_key", d)) for d in deps]
            if getattr(spec, "partitions_def", None) is not None:
                params["partitioned"] = True
            if getattr(spec, "automation_condition", None) is not None:
                params["automation_condition"] = True
            md = getattr(spec, "metadata", None) or {}
            if isinstance(md, dict) and md.get("dagster/io_manager_key"):
                params["io_manager_key"] = str(md["dagster/io_manager_key"])
            emit("asset", getattr(spec, "key", spec), params)
    except Exception:
        pass
    # io_manager_key BINDINGS live on the assets definitions, not the specs;
    # walk defs.assets and stamp each key's binding onto its record (G1).
    try:
        by_name = {}
        for r in records:
            if r["kind"] == "asset":
                by_name[r["name"]] = r
        for adef in getattr(defs, "assets", None) or []:
            keys_by_out = getattr(adef, "keys_by_output_name", None)
            node = getattr(adef, "node_def", None)
            outs = getattr(node, "output_defs", None) if node is not None else None
            if not keys_by_out or not outs:
                continue
            io_by_out = {o.name: getattr(o, "io_manager_key", None) for o in outs}
            for out_name, akey in keys_by_out.items():
                io_key = io_by_out.get(out_name)
                rec = by_name.get(str(akey))
                if rec is not None and io_key and io_key != "io_manager":
                    rec.setdefault("params", {}).setdefault(
                        "io_manager_key", str(io_key)
                    )
    except Exception:
        pass
    for attr, kind in (
        ("jobs", "job"),
        ("schedules", "schedule"),
        ("sensors", "sensor"),
    ):
        try:
            for obj in getattr(defs, attr, None) or []:
                params = {}
                cron = getattr(obj, "cron_schedule", None)
                if cron:
                    params["cron_schedule"] = str(cron)
                emit(kind, _runtime_obj_name(obj), params or None)
        except Exception:
            pass
    try:
        for obj in getattr(defs, "asset_checks", None) or []:
            pairs = _runtime_check_pairs(obj)
            if pairs:
                for cname, akey in pairs:
                    emit(
                        "asset_check",
                        cname or _runtime_obj_name(obj),
                        {"asset": akey} if akey else None,
                    )
            else:
                emit("asset_check", _runtime_obj_name(obj))
    except Exception:
        pass
    try:
        for key in defs.resources or {}:
            emit("resource", key)
    except Exception:
        pass


# ---------------------------------------------------------- manifest assembly


def _best_static_match(candidates, rt):
    """Which static record a runtime record aligns with; disambiguate checks by
    target asset when names collide."""
    rt_asset = (rt.get("params") or {}).get("asset")
    if rt_asset:
        for c in candidates:
            c_asset = (c.get("params") or {}).get("asset")
            if c_asset is not None and _normalize_name(c_asset) == _normalize_name(
                rt_asset
            ):
                return c
    for c in candidates:
        if c["kind"] == rt["kind"]:
            return c
    return candidates[0]


def _merge_runtime_first(runtime_records, static_records):
    """RUNTIME-FIRST reconciliation. Runtime records are the primary inventory;
    each is grafted with the matching static site's syntactic extras (source
    edges, spelling, conditional/factory context). Static-only sites (dead code,
    an alternate conditional branch, a runtime miss) are appended flagged
    `not_in_runtime` so the completeness net never drops them."""
    index = {}
    for s in static_records:
        index.setdefault(
            (_coarse_family(s["kind"]), _normalize_name(s["name"])), []
        ).append(s)
    used = set()
    combined = []
    for rt in runtime_records:
        rt = dict(rt)
        key = (_coarse_family(rt["kind"]), _normalize_name(rt["name"]))
        cands = [s for s in index.get(key, []) if id(s) not in used]
        if cands:
            s = _best_static_match(cands, rt)
            used.add(id(s))
            for f in (
                "source_edges",
                "spelling",
                "conditional",
                "factory",
                "deprecated_reason",
                "outputs",
            ):
                if s.get(f) and not rt.get(f):
                    rt[f] = s[f]
            rt["static_location"] = s.get("location")
        combined.append(rt)
    for s in static_records:
        if id(s) not in used:
            s = dict(s)
            s["not_in_runtime"] = True
            combined.append(s)
    return combined


def _edge_upstream_names(edge):
    raw = edge.get("upstream") or edge.get("upstream_ins")
    return re.findall(r"[A-Za-z_]\w*", str(raw)) if raw is not None else []


def _resolve_edge_io_managers(records):
    """Attribute each source-edge's io_manager to the PRODUCER (default key when
    unset); fall back to the consumer's key marked `consumer-side guess`."""
    producer = {}
    for r in records:
        if _coarse_family(r["kind"]) == "asset":
            key = (r.get("params") or {}).get("io_manager_key")
            producer[_normalize_name(r["name"])] = key
            for o in r.get("outputs", []):
                producer.setdefault(_normalize_name(o["name"]), key)
    for r in records:
        consumer_key = (r.get("params") or {}).get("io_manager_key")
        for edge in r.get("source_edges", []):
            keys = [
                producer[_normalize_name(n)] or _DEFAULT_IO_MANAGER_KEY
                for n in _edge_upstream_names(edge)
                if _normalize_name(n) in producer
            ]
            edge["consumer_io_manager"] = consumer_key
            if keys:
                uniq = sorted(set(keys))
                edge["io_manager"] = uniq[0] if len(uniq) == 1 else uniq
                edge["io_manager_source"] = "producer"
            else:
                edge["io_manager"] = consumer_key or _DEFAULT_IO_MANAGER_KEY
                edge["io_manager_source"] = "consumer-side guess"


def build_manifest(root, use_runtime):
    static_records = run_static(root)
    for rec in static_records:
        rec["name"] = str(rec["name"]).strip()

    manifest = {"project_root": str(root), "modes": ["static"], "legend": LEGEND}
    records = static_records
    if use_runtime:
        runtime_records, error = run_runtime(root)
        if error:
            manifest["runtime_error"] = error
        else:
            # runtime-first: runtime is the primary inventory, static is the net
            manifest["modes"] = ["runtime", "static"]
            records = _merge_runtime_first(runtime_records, static_records)
            manifest["runtime_records"] = len(runtime_records)
            manifest["static_only"] = sum(1 for r in records if r.get("not_in_runtime"))

    _resolve_edge_io_managers(records)
    counts = {}
    for rec in records:
        counts[rec["kind"]] = counts.get(rec["kind"], 0) + 1
    manifest["counts"] = counts  # counts per KIND (classification is pending)
    manifest["total"] = len(records)
    manifest["dbt_manifest_coupling"] = _dbt_coupling_scan(root)

    # units: the records keyed by a stable unit id, the shape status.py and
    # validate_dag.py consume. The planner later adds TARGET expectations under
    # DISTINCT keys (dag_id, edges, schedule, asset_schedule, timetable_type,
    # asset_outlets); source_edges stays scanner-owned so the two never collide.
    units = {}
    for rec in records:
        base = "{0}:{1}".format(rec["kind"], rec["name"])
        unit_id, n = base, 2
        while unit_id in units:
            unit_id, n = "{0}#{1}".format(base, n), n + 1
        units[unit_id] = rec
    manifest["units"] = units
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only Dagster project inventory scanner."
    )
    parser.add_argument(
        "project_root", type=Path, help="path to the Dagster project root"
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="runtime-first: import the project and enumerate Definitions",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write manifest JSON here (default: stdout)",
    )
    args = parser.parse_args(argv)

    root = args.project_root.resolve()
    if not root.exists():
        parser.error(f"project root does not exist: {root}")

    manifest = build_manifest(root, args.runtime)

    if args.runtime and manifest.get("runtime_error"):
        sys.stderr.write(
            "\n!!! runtime mode did not run: " + manifest["runtime_error"] + "\n"
            "    The manifest is STATIC-ONLY (the completeness net, not the primary\n"
            "    runtime inventory). Runtime mode imports the project in THIS\n"
            "    interpreter, so run the scanner with the project's own venv python:\n"
            "      <project-venv>/bin/python scripts/inventory.py "
            + str(args.project_root)
            + " --runtime\n"
            "      uv run python scripts/inventory.py "
            + str(args.project_root)
            + " --runtime\n\n"
        )

    text = json.dumps(manifest, indent=2, default=str)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {manifest['total']} records to {args.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
