# Components and dynamic definition generation

> **STATUS: reviewed; validated against dagster-open-platform in testing.**

Components-based projects (`pyproject.toml [tool.dg]`, `defs.yaml` instance files, `src/<pkg>/defs/` autoload) are the current Dagster project shape and half of real-world code. The migration question per component instance is always the same: **is this a library component configured by YAML, or a custom `Component` subclass whose `build_defs` is a program?**

## Library component instances (JUDG)

A `defs.yaml` whose `type:` points at a shipped component (`DbtProjectComponent`, `SlingReplicationCollectionComponent`, ...) is configuration for a known generator. Do not migrate the YAML; migrate what it generates:

1. Identify the component type and read its `attributes:` (the YAML is the inventory).
2. Route to the integration's own mapping: dbt components → `dbt.md`, sling/dlt/fivetran/airbyte → the integration rows in `mapping.md` section 10.
3. The YAML's config values (project paths, connection names, selectors, cron strings in attributes) carry over into the translated DAG's config.

Also catch the preview-era filename `component.yaml` (same treatment).

## Custom `Component` subclasses (REDESIGN)

Real projects subclass `Component` (or an integration's workspace class) and override `build_defs`. These are PROGRAMS that generate definitions at load time. From real projects:

- `FivetranComponent`: fetches the connector list from the LIVE Fivetran API at definition-load time, applies per-connector automation conditions from a YAML cron map, overrides `_sync_and_poll` to skip-but-succeed when Fivetran reschedules a sync, and registers a separate connection-test job + schedule.
- `ProdDbReplicationsComponent`: fans out `@sling_assets` per shard from `shard_*.yaml` config files.

Porting rule: **port the OUTPUT of `build_defs`, not the class.**

1. **Snapshot to a static manifest.** Run the component in the source project (or call its discovery path) once at migration time and record what it generated: the concrete asset list, per-item schedules/conditions, connector ids. Airflow DAG parsing must not call live APIs; dynamic discovery becomes a committed manifest file plus a documented refresh procedure (regenerate the manifest, re-render the DAGs, PR the diff).
2. **Translate the generated definitions normally** using the manifest: each generated asset/schedule/sensor goes through the same mapping as hand-written ones.
3. **Port the embedded business logic explicitly.** Overridden methods (like skip-on-reschedule polling) are invisible in the generated definitions; read the subclass body. They usually become custom operator subclasses or `@task` wrappers around the provider hook, and they are exactly the code a provider operator does NOT give you. List each override in the migration report.
4. **Config-file fan-out** (per-shard YAML) maps well to Airflow: keep the config files, render one task (or dynamic-mapped task) per entry at parse time from the LOCAL files (local file reads at parse time are fine; network calls are not).

## Env-branched definitions

Real projects branch their `Definitions` at import time on environment variables (one module returns the dbt-CLI wiring or the dbt-Cloud wiring depending on env). Treat these like a two-branch component: the scanner emits records for both branches flagged with the condition; the plan migrates the branch the target deployment actually runs and dispositions the other as a recorded alternate (with what re-activating it would take). Never let the un-taken branch vanish silently.

## Blocked-at-source inputs

Some component/integration domains cannot generate their input artifacts in the migration environment (a dbt manifest whose models are stripped from the mirror, a Fivetran discovery call needing live credentials). The pattern (verified in testing): ship COMPLETE translated code in a `deferred/` directory with an activation runbook (the exact commands that produce the missing artifact and move the code live), record a partial manifest with a `blocked_at_source` flag and reason, and include a refresh script so the activation is mechanical. A blocked domain with complete deferred code and a runbook is a `deferred` disposition, not a failure; a stub pretending the artifact exists is.

Also flag load-time coupling: helpers like `get_asset_key_for_model(...)` called in OTHER domains couple their definition loading to the dbt manifest; a blocked dbt domain then cascades. The scanner surfaces these (`dbt_manifest_coupling`); plan migration order around them.

## Scanner notes

- `component_instance` records in the inventory manifest carry the `type:` and attributes; classify library types JUDG and unknown/custom types REDESIGN.
- Custom subclasses live outside `defs/` (a `lib/` or `components/` package); inventory the class file too, since `build_defs` bodies contain schedules and jobs the YAML never shows.
- `AutomationConditionSensorDefinition` registered by components: the sensor the Dagster daemon evaluates (~every 30s) to drive declarative automation; it does not migrate (Airflow's scheduler plays that role). Its existence just confirms the project used declarative automation; map the conditions themselves per `automation.md`.
