---
name: airflow-custom-provider
description: Builds a custom Apache Airflow provider package - hooks, operators, sensors, get_provider_info(), the apache_airflow_provider entry point, and custom connection types in the Airflow UI. Use when the user wants to package integration code for a third-party system as a pip-installable Airflow provider, mentions get_provider_info, apache_airflow_provider, provider.yaml, "build a provider package", "airflow-provider-<name>", or wants a custom connection type to appear in the Airflow UI connection form. Not for a one-off operator used inside a single DAG repo (see the decision table below) or for Airflow 3.1+ UI/FastAPI plugins (see airflow-plugins).
---

# Airflow Custom Provider Packages

Package a hook, operator, or sensor for a third-party system into an independently distributed, pip-installable Airflow provider — the same mechanism every official Apache provider (`apache-airflow-providers-amazon`, `-snowflake`, etc.) uses. Any DAG repo can then `pip install` it and get the operators, sensors, and a custom connection type in the UI.

> **Canonical template**: [astronomer/airflow-provider-sample](https://github.com/astronomer/airflow-provider-sample). Clone it fresh before starting — this skill explains the parts of that template that are easy to get subtly wrong, not a frozen copy of its files.
>
> **Cross-references**: `setting-up-astro-project` for `include/`/`plugins/` (lighter-weight alternative below); `airflow-plugins` for Airflow 3.1+ FastAPI/UI plugins (a different "plugin" concept entirely); `airflow` for the `af registry` / `af config providers` discovery commands used below; `managing-astro-local-env` for `astro dev` lifecycle commands.

---

## Step 1 — Decide: provider package, or something lighter?

| Situation | Reach for |
|---|---|
| Integration code will be shared across 2+ DAG repos, released independently, or installed by other teams (or the public) | A provider package (this skill) |
| A one-off integration used by a single DAG in one repo, not meant to be reused elsewhere | A plain Python class in `include/` of that repo (or a legacy `plugins/` registration) — see `setting-up-astro-project` |
| A custom UI page, FastAPI endpoint, or React app embedded in the Airflow webserver | Not this skill — see `airflow-plugins` |

A sign you should have built a provider package: the same hook or operator class gets copy-pasted into a second DAG repo.

A common mistake going the other direction: dropping a `provider.yaml` manifest with an `airflow.providers.<name>` import path into a single project's `plugins/` folder. That manifest format is for providers vendored inside the `apache/airflow` source tree itself and is discovered from that source tree at build time — it does nothing for an independently pip-installed package sitting in `plugins/`. An externally distributed provider needs `get_provider_info()` plus the `apache_airflow_provider` entry point (Step 3), not a YAML manifest.

---

## Step 2 — Package skeleton

Directory layout, verified against the canonical template:

```
airflow-provider-<name>/
├── LICENSE
├── README.md
├── pyproject.toml
├── <name>_provider/
│   ├── __init__.py          # __version__ + get_provider_info()
│   ├── hooks/
│   │   ├── __init__.py
│   │   └── <name>.py
│   ├── operators/
│   │   ├── __init__.py
│   │   └── <name>.py
│   ├── sensors/
│   │   ├── __init__.py
│   │   └── <name>.py
│   └── example_dags/
│       └── <name>.py
└── tests/
    ├── __init__.py
    ├── hooks/
    ├── operators/
    └── sensors/
```

Naming convention: the distributed package name is hyphenated, `airflow-provider-<name>`; the importable Python module is underscored, `<name>_provider` (not `airflow_provider_<name>`). This split is consistent across the ecosystem's provider packages — don't merge the two.

Layouts drift less than code, but don't take this listing as gospel forever. Before scaffolding a new provider, re-clone the template and diff:

```bash
git clone --depth 1 https://github.com/astronomer/airflow-provider-sample /tmp/airflow-provider-sample-ref
find /tmp/airflow-provider-sample-ref -type f -not -path '*/.git/*'
```

---

## Step 3 — `get_provider_info()` and the entry point (the part that silently breaks)

Two files have to agree. Using a fictitious "Acme" integration:

`pyproject.toml`:

```toml
[project.entry-points.apache_airflow_provider]
provider_info = "acme_provider.__init__:get_provider_info"
```

`acme_provider/__init__.py`:

```python
__version__ = "1.0.0"


def get_provider_info():
    return {
        "package-name": "airflow-provider-acme",  # required
        "name": "Acme",  # required
        "description": "Apache Airflow provider for the Acme API.",  # required
        "versions": [__version__],  # required
        "connection-types": [
            {"connection-type": "acme", "hook-class-name": "acme_provider.hooks.acme.AcmeHook"}
        ],
        "extra-links": ["acme_provider.operators.acme.AcmeOperatorExtraLink"],
    }
```

Two ways this fails discovery with no error and no log line:

- **Wrong entry-point group name.** It must be exactly `apache_airflow_provider` — not `apache-airflow-provider`, not `airflow.providers`. Airflow's provider manager scans installed distributions for that exact group string. Get it wrong and the package still `pip install`s cleanly, still imports cleanly — Airflow just never lists it as a provider.
- **Missing a required metadata field, or a typo in the entry-point target.** `package-name`, `name`, `description`, and `versions` are required; `connection-types` and `extra-links` are optional additions that unlock specific UI features. If the target function (`module:function`) doesn't resolve, or the dict is missing a required key, the failure mode is the same: silent absence, not an exception surfaced to the user.

Verify instead of trusting the file:

```bash
# Does Python even see the entry point?
python -c "from importlib.metadata import entry_points; print(list(entry_points(group='apache_airflow_provider')))"

# Does Airflow list it as a provider? (af is the Airflow MCP CLI - see the `airflow` skill)
af config providers | jq '.providers[] | select(.package_name == "airflow-provider-acme")'
```

If the first command comes back empty, the entry point in `pyproject.toml` is wrong. If the first succeeds but the second doesn't, the entry point resolved but `get_provider_info()` likely raised or returned a dict missing a required key.

**Making the connection type show up in the UI's connection form.** Declaring `connection-types` in `get_provider_info()` is necessary but not sufficient for a good form — the hook needs the standard discovery attributes plus two optional classmethods Airflow looks for when rendering the "Add Connection" screen:

```python
from airflow.hooks.base import BaseHook


class AcmeHook(BaseHook):
    conn_name_attr = "acme_conn_id"
    default_conn_name = "acme_default"
    conn_type = "acme"
    hook_name = "Acme"

    @staticmethod
    def get_connection_form_widgets() -> dict:
        ...  # extra form fields, via flask_appbuilder / wtforms

    @staticmethod
    def get_ui_field_behaviour() -> dict:
        ...  # hide, relabel, or placeholder the standard fields
```

Verify the registered connection type the same way as the provider itself, rather than only eyeballing the UI:

```bash
af config connections | jq '.connections[] | select(.conn_type == "acme")'
```

---

## Step 4 — Constraints that cause real bugs if skipped

- **No network or I/O calls inside `__init__`.** Hook, operator, and sensor constructors run every time the scheduler parses the DAG file — by default every ~30 seconds, for every DAG that imports them. An `__init__` that opens a connection hammers the target system and can stall DAG parsing entirely. Store the `conn_id` in `__init__`; resolve the real connection only inside `execute()` / `poke()` / `get_conn()`.
- **`__init__` must not call anything that only returns valid objects at runtime.** That breaks DAG import outright, not just performance, because operators are constructed at parse time. Anything only known at task-run time belongs in a templated field (Jinja), not a constructor call.
- **Every operator implements `execute(self, context)`.** This is what Airflow calls at task-run time; skip it and every task instance fails with `NotImplementedError` from `BaseOperator`.
- **Every sensor implements `poke(self, context)`** returning a bool (or uses the deferrable/trigger pattern) — same contract via `BaseSensorOperator`.
- **Semantic versioning, read from one place.** Bump `__version__` in `__init__.py`; wire `pyproject.toml` to read it (`[tool.setuptools.dynamic]` / `version = { attr = "acme_provider.__version__" }`) rather than hardcoding the version a second time.
- **Relaxed dependency bounds.** Pin a floor, leave the ceiling open: `depx>=2.0,<3`, not `depx==2.3.1`. This applies doubly to `apache-airflow` itself — declare a floor (e.g. `apache-airflow>=2.9`) and let the runtime supply the actual version. A tightly pinned or exact-match dependency is the most common cause of "provider X conflicts with provider Y" install failures.

---

## Step 5 — Functional testing loop

Two layers: unit tests (fast, every commit) and a functional test that confirms Airflow actually discovers the package (unit tests can't catch a broken entry point).

**Unit tests mirror the package structure:**

```
tests/
├── hooks/test_acme_hook.py
├── operators/test_acme_operator.py
└── sensors/test_acme_sensor.py
```

Mock the network boundary (e.g. `requests_mock`, or mock the underlying client) and mock the Airflow connection rather than requiring a live one. Test `get_provider_info()` itself too — assert the required keys are present and that every `hook-class-name` / `extra-links` string actually imports.

**Functional test via the Astro CLI** — the only step that proves real discovery, not just importability:

```bash
# 1. Build the wheel
python -m build

# 2. Drop it into an Astro project and declare it as a dependency
cp dist/*.whl <astro-project>/
echo "./$(basename dist/*.whl)" >> <astro-project>/requirements.txt

# 3. Start Airflow and confirm discovery
cd <astro-project> && astro dev start
af config providers | jq '.providers[] | select(.package_name == "airflow-provider-acme")'

# 4. If a connection-type was registered, confirm it in the UI too:
#    Admin -> Connections -> Add -> Connection Type dropdown should list it
```

After changing the wheel, `astro dev restart`; for a clean slate, `astro dev kill` (see `managing-astro-local-env` for the full lifecycle reference).

---

## Step 6 — Safety checklist

- [ ] Distributed name is `airflow-provider-<name>`; importable module is `<name>_provider` — no drift between the two.
- [ ] `pyproject.toml` entry-point group is exactly `apache_airflow_provider`, target resolves to a real `module:function`.
- [ ] `get_provider_info()` returns `package-name`, `name`, `description`, and `versions` — confirmed with the `importlib.metadata` + `af config providers` pair from Step 3, not assumed from reading the code.
- [ ] No network/IO and nothing runtime-only inside any `__init__`.
- [ ] Every operator implements `execute()`; every sensor implements `poke()` or a deferrable trigger.
- [ ] Dependency bounds are relaxed (`>=x,<y`), especially for `apache-airflow` itself — no exact pins.
- [ ] `__version__` bumped following semver; `pyproject.toml` reads it via `dynamic`, not a second hardcoded copy.
- [ ] Unit tests exist under `tests/{hooks,operators,sensors}/`, mirroring the package tree.
- [ ] Confirmed via `astro dev start` + `af config providers` that Airflow lists the package as a provider — `pip install` succeeding is not sufficient proof.

---

## References

- Canonical template: [astronomer/airflow-provider-sample](https://github.com/astronomer/airflow-provider-sample) — directory layout, `get_provider_info()` shape, and dependency-bound guidance above were verified directly against this repo's `pyproject.toml`, `__init__.py`, and README. Re-clone it if anything here looks stale; it is the source of truth, not this file.
- [Apache Airflow provider packages documentation](https://airflow.apache.org/docs/apache-airflow-providers/) — upstream conventions for provider metadata and capabilities beyond what this skill covers.
- The Airflow Registry (`af registry providers`, or `airflow.apache.org/registry`) — browse published providers for comparison patterns.

## Related skills

- **setting-up-astro-project** — `include/`/`plugins/` for one-off operators that don't warrant their own package.
- **airflow-plugins** — Airflow 3.1+ FastAPI/UI plugins (a different "plugin" concept from a provider package).
- **airflow** — `af registry` / `af config providers` command reference used for discovery verification above.
- **managing-astro-local-env** — `astro dev start` / `stop` / `restart` / `kill` lifecycle for the functional testing loop.
- **authoring-dags** — general DAG writing conventions once the provider is installed.
- **testing-dags** — iterative test/debug/fix cycles once the provider is installed in a project.
