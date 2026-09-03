---
name: airflow-custom-provider
description: Builds a custom Apache Airflow provider package - hooks, operators, sensors, the `get_provider_info()` contract, and the `apache_airflow_provider` entry point that registers connection types in the Airflow UI. Use when the user wants to package Airflow integration code for a third-party system into an installable `airflow-provider-<name>` package, add a custom connection type to the Airflow UI's connection form, or asks about `get_provider_info`, provider discovery, or turning a one-off operator into something pip-installable and shareable. Not for embedding custom UI pages or FastAPI apps into Airflow itself (see airflow-plugins), and not for a one-off operator meant to live inside a single DAG repo (see Step 1).
---

# Airflow Custom Provider Packages

A provider package is a pip-installable Python package that Airflow discovers automatically at startup and that bundles hooks, operators, sensors, and (optionally) a custom connection type for one external system. Build one when the integration needs to be versioned, released, and reused outside a single DAG repo — not for logic that only ever lives in one project.

> **Cross-references**: `airflow` for the `af config` / `af registry` discovery commands used throughout this skill; `airflow-plugins` for embedding UI pages or FastAPI apps into Airflow itself (a different extension mechanism); `setting-up-astro-project` and `managing-astro-local-env` for the Astro CLI commands used in the functional test loop below.

---

## Step 1 — Decide: provider package, or just an operator in this repo?

| Situation | Build |
|---|---|
| The integration will be reused across two or more DAG repos/projects, needs its own version and release cadence, or is meant to be published (internally or to PyPI) | A provider package (`airflow-provider-<name>`) |
| The logic is used only inside this one DAG repo and nobody else needs it | A plain hook/operator module under `include/` (or `plugins/` for a one-off registration), imported directly into DAGs |
| Needs a custom connection type to appear in the Airflow UI's connection dropdown | A provider package — only providers that declare `connection-types` in `get_provider_info()` can register a connection type |
| Needs a custom UI page, nav entry, or FastAPI route inside Airflow itself | Not this skill — that is an Airflow plugin, see `airflow-plugins` |

A hook or operator that sits in a DAG repo's `include/`/`plugins/` directory with no `pyproject.toml` and no entry point is an unfinished provider: it gets none of the discovery benefits below (no connection form, no `af config providers` visibility, no independent versioning) while still carrying packaging-shaped code. Either finish the packaging or don't start it — don't leave it half-built.

---

## Step 2 — Package skeleton

Naming convention: the top-level package (and PyPI name, if published) is `airflow-provider-<name>`; the importable Python package inside it uses underscores, e.g. `<name>_provider`.

```
airflow-provider-<name>/
├── LICENSE
├── README.md
├── pyproject.toml
├── <name>_provider/
│   ├── __init__.py          # get_provider_info() lives here
│   ├── example_dags/
│   │   └── example.py
│   ├── hooks/
│   │   ├── __init__.py
│   │   └── <name>.py
│   ├── operators/
│   │   ├── __init__.py
│   │   └── <name>.py
│   └── sensors/
│       ├── __init__.py
│       └── <name>.py
└── tests/
    ├── __init__.py
    ├── hooks/
    │   └── test_<name>_hook.py
    ├── operators/
    │   └── test_<name>_operator.py
    └── sensors/
        └── test_<name>_sensor.py
```

This mirrors [astronomer/airflow-provider-sample](https://github.com/astronomer/airflow-provider-sample), Astronomer's public reference template — clone it to see a complete working example end to end, and to check whether the layout has changed since this was written:

```bash
git clone --depth 1 https://github.com/astronomer/airflow-provider-sample /tmp/airflow-provider-sample-ref
```

---

## Step 3 — The `get_provider_info()` contract and entry point

> **This is the easiest thing to get subtly wrong.** A wrong entry-point group name, a typo in the dotted path, or a missing required field in the returned dict does not raise an error — Airflow just silently fails to discover the provider. There's no traceback to chase; the symptom is "my hook/connection type doesn't show up anywhere." Verify the exact current shape against the cloned sample repo's `pyproject.toml` and `<package>/__init__.py` rather than trusting that the snippets below haven't drifted.

`pyproject.toml`:

```toml
[project.entry-points.apache_airflow_provider]
provider_info = "<name>_provider.__init__:get_provider_info"
```

The entry-point **group name must be exactly `apache_airflow_provider`** — that literal string, not your package name, is what Airflow's provider manager scans installed distributions for at startup.

`<name>_provider/__init__.py`:

```python
__version__ = "1.0.0"


def get_provider_info():
    return {
        "package-name": "airflow-provider-<name>",  # required
        "name": "<Name>",                            # required
        "description": "A short description of the integration.",  # required
        "versions": [__version__],                   # required
        "connection-types": [
            {
                "connection-type": "<name>",
                "hook-class-name": "<name>_provider.hooks.<name>.<Name>Hook",
            }
        ],
    }
```

The four required fields above (`package-name`, `name`, `description`, `versions`) are the baseline every provider must return. `connection-types` and other optional keys (e.g. `extra-links` for custom operator links) are additive — omit them if there's nothing to register, but don't guess at additional keys from memory: check the current sample repo or the [Apache Airflow provider packages documentation](https://airflow.apache.org/docs/apache-airflow-providers/) for what your Airflow version actually supports. Keep `versions` in sync with `__version__` on every release (Step 4).

To make a connection type appear in the UI's connection form, the hook referenced in `connection-types` needs the standard discovery attributes plus two optional classmethods Airflow looks for:

```python
class <Name>Hook(BaseHook):
    conn_name_attr = "<name>_conn_id"
    default_conn_name = "<name>_default"
    conn_type = "<name>"
    hook_name = "<Name>"

    @staticmethod
    def get_connection_form_widgets() -> dict:
        ...  # extra form fields, e.g. via flask_appbuilder / wtforms

    @staticmethod
    def get_ui_field_behaviour() -> dict:
        ...  # hide, relabel, or set placeholders on the standard fields
```

---

## Step 4 — Constraints that cause real bugs if skipped

- **No network or I/O calls in `__init__`.** The scheduler re-parses every DAG file on a fixed interval, which re-imports and re-instantiates every operator referenced in it. A hook or operator that touches the network (or a database, or the filesystem) in its constructor turns every DAG parse into a live call to that system — this shows up as scheduler slowness or parse timeouts, not an obvious stack trace pointing at your code.
- **`__init__` must never call anything that only resolves to a valid value at runtime** (for example, pulling a connection or a runtime-only variable). Resolve those inside `execute()`/`poke()`, or via Jinja-templated `template_fields`, not in the constructor — otherwise DAG parsing fails outright whenever that runtime dependency isn't available yet.
- **Every operator must implement `execute(self, context)`.** A `BaseOperator` subclass without it raises `NotImplementedError` the first time a task instance actually runs.
- **Sensors implement `poke(self, context)`** (or the deferrable/async equivalent), not `execute()`.
- **Use semantic versioning**, and bump `__version__` on every release so it stays in sync with the `versions` list returned by `get_provider_info()`.
- **Keep dependency bounds relaxed**: pin a minimum minor version and leave the upper bound open at the next major (`>=2.0.0,<3`), not an exact pin. An exact pin on a widely shared library — `requests`, or `apache-airflow` itself — will eventually conflict with core Airflow's own dependency pin or another installed provider's pin, and the environment will fail to resolve.

---

## Step 5 — Functional testing loop

Unit tests live under `tests/`, mirroring the package layout (`tests/hooks/`, `tests/operators/`, `tests/sensors/`) — one test module per source module. Mock the external system (e.g. `requests_mock`, or `unittest.mock`) and mock the Airflow connection via the `AIRFLOW_CONN_<CONN_ID>` environment variable so these tests never need a live Airflow instance:

```python
@mock.patch.dict("os.environ", AIRFLOW_CONN_<NAME>_DEFAULT="http://...")
class Test<Name>Hook:
    def test_run(self, requests_mock):
        ...
```

Unit tests confirm the code works; they don't confirm Airflow can *discover* the package. For that, build and install the wheel into a real Airflow environment:

```bash
python3 -m pip install build
python3 -m build              # produces dist/<name>-<version>-py3-none-any.whl
```

Then, in an Astro project (see `setting-up-astro-project` if you don't have one yet):

1. Copy the `.whl` into the project root.
2. Install it in the Dockerfile — the exact syntax (`RUN pip install`, a local wheel entry in `requirements.txt`, etc.) depends on your Astro CLI/runtime version, so check `astro dev init --help` or the current Astro docs rather than assuming one form.
3. Drop an example DAG that imports from your provider into `dags/`.
4. Run `astro dev start` (see `managing-astro-local-env` for start/stop/logs).
5. Confirm discovery explicitly — don't just eyeball the UI:

```bash
af config providers | jq '.providers[] | select(.package_name == "airflow-provider-<name>")'
af config connections | jq '.connections[] | select(.conn_type == "<name>")'   # only if you registered a connection type
```

If the package doesn't show up here, revisit Step 3 — this is the silent discovery failure described there, not a Docker or `astro dev start` problem.

---

## Step 6 — Safety checklist

- [ ] `get_provider_info()` returns `package-name`, `name`, `description`, and `versions` — all four, every release.
- [ ] The entry-point group in `pyproject.toml` is exactly `[project.entry-points.apache_airflow_provider]`, pointing at the real dotted path to `get_provider_info`.
- [ ] No network/IO/runtime-only resolution inside any `__init__`.
- [ ] Every operator implements `execute()`; every sensor implements `poke()` (or its deferrable equivalent).
- [ ] Dependency bounds are relaxed (`>=x,<y`), not exact pins — especially for `apache-airflow` itself and any library likely shared with other installed providers.
- [ ] `__version__` bumped and reflected in `versions` for this release.
- [ ] Wheel built, installed into a real Astro/Airflow environment, and discovery confirmed via `af config providers` (and `af config connections` if a connection type was registered) — not just "it imported without error."
- [ ] Unit tests exist under `tests/{hooks,operators,sensors}/` mirroring the package structure and pass without a live Airflow instance.

---

## References

- [astronomer/airflow-provider-sample](https://github.com/astronomer/airflow-provider-sample) — canonical reference template; clone it fresh rather than trusting this skill's snippets to still be current.
- [Apache Airflow provider packages documentation](https://airflow.apache.org/docs/apache-airflow-providers/) — upstream conventions for provider metadata, capabilities, and installation.
- The Airflow Registry (`af registry providers`, or `airflow.apache.org/registry`) — browse published providers for comparison patterns.

## Related skills

- **airflow** — `af config` / `af registry` command reference used for the discovery verification in Step 5.
- **airflow-plugins** — embedding custom UI pages, FastAPI apps, or middleware into Airflow itself; a different extension point from provider packages.
- **setting-up-astro-project** — initializing the Astro project used in the functional testing loop.
- **managing-astro-local-env** — starting, stopping, and inspecting the local Airflow environment during testing.
- **authoring-dags** — general DAG-writing conventions for using the finished provider's operators.
- **testing-dags** — iterative test/debug/fix cycles once the provider is installed in a project.
