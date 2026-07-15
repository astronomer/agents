---
name: migrating-dagster-to-airflow
description: Guide for migrating Dagster projects to Apache Airflow 3 on Astro. Use when the user mentions migrating, converting, or porting Dagster (or Dagster+) code to Airflow or Astro, wants to plan or assess such a migration, or asks what a Dagster construct maps to in Airflow. Covers assets, partitions, schedules, sensors, declarative automation, resources, IO managers, ops/jobs, dbt, Pipes, Components, and Dagster+ platform config. Always load this skill as the first step for any Dagster-to-Airflow request.
hooks:
  PostToolUse:
    - matcher: "Edit"
      hooks:
        - type: command
          command: "echo 'Migrated DAG edited: consider re-running gates 1-3: python3 scripts/validate_dag.py <astro_project> --manifest manifest.json'"
---

# Dagster → Airflow 3 (Astro) migration

Migrate a Dagster project to Airflow 3 on Astro Runtime, honestly. The migration is asset-first (Dagster asset graphs translate to Airflow assets and asset-aware schedules, not flattened DAGs), incremental (domain by domain, Dagster stays authoritative until parity), and honest (every definition gets an explicit disposition; semantic deltas are documented, never papered over).

First time driving this? Read `reference/quickstart.md` first: hour-one commands, the glossary, and what can and cannot break.

## Migration at a glance

1. Baseline the source project's tests, then inventory it read-only (`scripts/inventory.py` → manifest).
2. Review classifications (MECH/JUDG/REDESIGN/NONE per `reference/mapping.md`); make the go/no-go call (three outcomes; migrate-with-conditions is the common case, stay is the narrow one); plan DAG boundaries, per-edge IO decisions, and Gate 3 expectations into the manifest.
3. Trial-migrate 2-3 representative units end-to-end through every validation gate.
4. Migrate domain by domain through the six-gate ladder (`reference/validation.md`), tracking per-unit state (`scripts/status.py`); fix failure classes via `reference/troubleshooting.md`, never stub.
5. Map the platform layer (secrets, alerts, CI/CD, Deployments) per `reference/astro-deployment.md`.
6. Run side by side, then cut over per domain (consumers unpause first; see the checklist), keeping rollback one step away.
7. Deliver the migration report: every definition dispositioned, an equivalence row per trigger, losses stated plainly.

## Version drift

Verified against Airflow 3.3.0 / Astro Runtime 3.3-2 / astronomer-cosmos 1.15 / Dagster 1.13 (2026-07). Version-sensitive rows in the references carry their floor (notably the 3.2-vs-3.3 partition surface). Before relying on a version-gated claim: check the target (`airflow version`, `astro deployment inspect`), probe imports for sdk surface (`python3 -c "from airflow.sdk import X"`), and prefer `--help` / API spec discovery over assuming verbatim CLI/REST contracts on newer versions. Playbook entries are version-scoped per entry.

## Requirements

- Target **Astro Runtime 3.3+** (Airflow 3.3+); the native asset-partition surface requires it. Below 3.2 the mapping degrades badly; say so and recommend upgrading before migrating.
- The Dagster repo, and ideally a running Dagster instance (its materialization metadata provides parity-test fixtures).
- `astro` CLI for the target project.

## Hard rules

1. **Never stub.** A translated unit either works through its validation gate or is deferred with a written reason. Fake-success bodies and workaround code with long justifying comments are failures.
2. **No silent omissions.** Every record in the inventory manifest ends `complete` or `deferred (reason)`. `scripts/status.py summary` exits nonzero otherwise; run it before claiming done.
3. **Equivalence rows for every trigger.** Each schedule/sensor/automation condition gets a report row: source spelling, target spelling, delta in one sentence. Semantic deltas exist (catchup, on_cron inversion, eager guarantees); the sin is not the delta, it is the undocumented delta.
4. **Fix classes, not instances.** When a translation pattern fails validation, fix the pattern (and record it in `reference/troubleshooting.md`), then re-apply; do not hand-patch one unit.
5. **Do not invent APIs.** The references contain verified names only. Anything not covered there gets verified against official docs before use.

## Workflow

### Phase 0: Preflight

Confirm target Runtime version, `astro` CLI presence, and repo access. Detect the project layout: classic (`@repository`/`workspace.yaml`), modern (`Definitions`), or Components (`pyproject.toml [tool.dg]`, `defs.yaml` files); all three occur, sometimes together. Baseline the source project's test suite now: pre-existing failures are recorded and excluded from migration blame.

### Phase 1: Inventory (read-only)

```
python3 scripts/inventory.py <dagster_repo> --out manifest.json          # static scan
python3 scripts/inventory.py <dagster_repo> --runtime --out manifest.json # + runtime introspection when the project imports
```

The manifest lists every definition with file:line, captured params, current-vs-deprecated spelling, and dependency edges with their IO manager; every record starts `classification: "pending"`. Classifying is YOUR first judgment task: assign each record MECH / JUDG / REDESIGN / NONE from its row in `reference/mapping.md` and write it into the manifest. The scanner enumerates (deterministic completeness); the agent classifies (judgment). A record you cannot map to a mapping.md row is itself a finding: record it, do not guess. Also grep for `DAGSTER_CLOUD_` and `EnvVar(` (platform layer, Phase 5).

Manifest conventions: the canonical manifest lives in the migration run directory. Once the Astro project exists (Phase 2 scaffold), copy the manifest to its `include/inventory/manifest.json` so the Gate 3 pytest and `status.py` defaults find it; until then it just stays in the run dir (keep the two in sync afterward, the run-dir copy wins). Static records are the canonical migration units; runtime-mode enrichment merges into them, and only genuinely runtime-only definitions (factory-generated) become new units.

Emit the migration report skeleton now: one section per manifest record, plus the secrets/env naming map from `reference/astro-deployment.md`. Scale the skeleton to the project: a secretless local project gets a one-line "no secrets/platform layer" note, not empty boilerplate sections.

### Phase 1.5: Go/no-go (the honest gate)

Before translating anything, answer the project-level question the inventory makes answerable: **what does this team give up by migrating, and does each loss have an acceptable answer?** Assess the NONE and REDESIGN rows against what is load-bearing for THIS team, evaluating the mitigation, not just the loss:

| If load-bearing | The Airflow-world answer | Stay-signal only if |
|---|---|---|
| dbt rebuild-on-code-change (`code_version_changed()`) | State-aware dbt builds on a cron (Fusion / dbt State skip unchanged models per run, so the post-deploy tick rebuilds exactly what changed), and/or CI-triggered `dbt build` on merge (PR-gated, often an upgrade) | The team can neither run a state-aware dbt stack nor dbt from CI |
| Freshness driving materialization | Astro Observe freshness SLAs / Timeliness alerts + scheduled runs sized to the SLA | Freshness-triggered compute is genuinely irreplaceable by schedule+alerting |
| Per-asset cost accounting (Insights) | Astro Observe pipeline-level warehouse cost management; per-asset granularity is lost | Per-ASSET chargeback is a contractual/organizational requirement |
| Asset catalog / column-level lineage as daily tools | Airflow 3 asset views + OpenLineage/Astro lineage (asset-level) | Column-level lineage is embedded in daily workflows with no external catalog |
| Deep AutomationCondition compositions, `can_subset`, selective per-partition materialization | Most decompose to cron/asset schedules (see `reference/automation.md`); the residue is redesigned per domain | Multiple domains depend on compositions that decompose to nothing |
| Sensor cursor transactionality, run-scoped teardown | Idempotent consumers + `max_active_runs`; context managers in task bodies | Exactly-once event coalescing is a correctness requirement that idempotency cannot absorb |

One rule the table implies, stated plainly: **no dbt-only condition reaches "stay."** Between Cosmos, state-aware dbt builds, and CI-triggered builds, every dbt-workflow loss has an accepted-practice mitigation (execution-proven in this skill's eval program, including on a real warehouse); dbt items are conditions to record, never blockers. The observability rows (per-asset cost, column-level lineage) are separate conditions and are evaluated on their own, even for dbt-heavy teams.

The gate's outcome is three-valued, and the middle one is the common case:

- **Migrate**: no stay-signals; proceed to Phase 2.
- **Migrate with conditions** (most real projects): losses exist, mitigations are named and accepted in writing in the report's first section, specific domains may carry REDESIGN work; proceed to Phase 2 with those conditions recorded.
- **Stay on Dagster, today**: reserved for the case where MULTIPLE stay-signal conditions in the right column genuinely hold at once and the migration is not externally mandated. Then the honest deliverable is that recommendation, in writing, with the specific unmitigated losses named, and the run stops there. A migration guide that cannot say "don't" cannot be trusted when it says "do", but "don't" is earned by unmitigatable losses, not by the mere existence of deltas.

### Phase 2: Plan

- **DAG boundaries**: decide which asset-dependency edges become asset-aware schedules (cross-DAG) vs task ordering (intra-DAG). Group by domain/schedule cadence/team ownership; `define_asset_job` selections usually name the natural domains.
- **Per-edge IO decisions** via the tree in `reference/io-and-data-passing.md` (fuse / explicit storage / XCom).
- **Order**: leaf domains first, dependency order after; the platform layer last.
- **Fill each planned unit's target expectations into the manifest**: `dag_id`, `task_count`, `edges`, `schedule`, `asset_outlets` per unit. Gate 3 asserts against exactly these fields; a unit without them is skipped by validation, so an unenriched manifest means Gate 3 checks nothing (validate_dag reports skipped counts loudly, do not ignore them).
- Scaffold the target: `astro dev init`, shared helpers under `include/`. House conventions the scaffold imposes (e.g. a test demanding `retries >= 2`) do NOT override source fidelity: source behavior wins; convention adoption is a post-cutover improvement listed in the report, and the scaffold test gets skipped with an explicit reason.

### Phase 3: Trial

Migrate 2-3 representative units end-to-end through every gate before fanning out. Pick one MECH asset, one partitioned asset, one JUDG case, or the nearest available mix (small projects may have no partitioned or no MECH assets; pick one full path through a real DAG instead). What the trial teaches goes into `reference/troubleshooting.md` before scaling; if the trial fails structurally, stop and rework the plan, not the units.

### Phase 4: Migrate, domain by domain

Per unit, the state machine (tracked in the manifest):

```
pending → translate → fix-import → fix-lint → fix-tests → verify-parity → complete
                                    ↘ deferred (reason required)
```

- Translate using the reference file for the construct (routing table below). Rich context beats cleverness: read the source unit, its mapping rows, and a nearby already-migrated example.
- Validate through the gates: `python3 scripts/validate_dag.py <astro_project> --manifest manifest.json` (gates 1-3), then execution and parity per `reference/validation.md`.
- On gate failure, retry with the latest validator output in context (cap ~10 attempts, then defer with the failure class).
- Advance state only on gate pass: `python3 scripts/status.py advance <unit-id> ...`. A wrong disposition is corrected with `status.py reopen <unit-id> --reason ...`. The no-hand-editing rule applies to the STATE field (`status`) only; the PLAN fields (`dag_id`, `task_count`, `edges`, `schedule`, `asset_outlets`, `target`) are the planner's to write in Phase 2.
- Units that deliberately translate to NO DAG of their own (helpers absorbed into tasks, policies that became alerts, resources that became connections) are dispositioned `complete` with `target: "none"` and evidence naming where they went; Gate 3 skips them by design.
- Commit per unit, atomically.

### Phase 5: Platform layer

`reference/astro-deployment.md`: Deployments topology, secrets/connection naming map, CI/CD and preview Deployments, alert-policy mapping, Observe/lineage expectations, the `DAGSTER_CLOUD_*` in-code rewrite checklist.

### Phase 6: Side-by-side and cutover

Dagster remains authoritative. Run migrated DAGs shadowed/paused; compare outputs over the same logical window (row counts + checksums; recompute expected values from the Dagster-produced output itself, using recorded materialization metadata only opportunistically, per `reference/validation.md` Gate 5). Flip schedules one domain per change window: pause the Dagster schedule, unpause the Airflow DAG; rollback is the reverse. Keep Dagster readable after cutover (run history does not migrate).

### Phase 7: Final report

`scripts/status.py summary` must pass. The report contains: the go/no-go assessment (Phase 1.5) and its rationale, disposition table for every definition, all equivalence rows, the NONE/REDESIGN losses stated plainly (lineage depth, code_version triggers, Insights cost accounting, sensor cursor transactionality), the secrets map, and the deferred list with reasons. Spot-check ten `complete` claims before delivering it.

## Reference routing

| Construct encountered | Read |
|---|---|
| First hour, glossary, what can break | `reference/quickstart.md` |
| Anything (first stop: one row per construct) | `reference/mapping.md` |
| Asset-key → URI convention, translation granularity, external/observable assets | `reference/assets.md` |
| Asset deps, IO managers, XCom, storage decisions | `reference/io-and-data-passing.md` |
| Any `partitions_def`, partition mappings, backfills | `reference/partitions.md` |
| Schedules, sensors, AutomationCondition, freshness | `reference/automation.md` |
| `@dbt_assets`, translators, dbt Cloud | `reference/dbt.md` |
| Components (defs.yaml), custom Component subclasses, dynamic generation | `reference/components.md` |
| dagster_cloud.yaml, secrets, alerts, CI/CD, cutover | `reference/astro-deployment.md` |
| Gates, parity testing, state machine | `reference/validation.md` |
| Failure classes seen before | `reference/troubleshooting.md` |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/inventory.py` | Scan the Dagster repo → JSON manifest (static + optional runtime mode) |
| `scripts/validate_dag.py` | Gates 1-3 against the generated Astro project |
| `scripts/status.py` | Per-unit state machine + completeness gate |
