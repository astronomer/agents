# Quickstart: your first hour

For the human driving the migration (with Claude Code running the skill). Everything in your first hour is read-only and reversible, with one caveat: runtime-mode inventory of a dagster-dbt project runs `prepare_if_dev`, which writes dbt's `target/` directory inside the source repo (build artifacts only, gitignored in typical projects). Nothing touches your Dagster deployment or its schedules until the cutover phase, many steps from now.

## Terms you'll meet immediately

| Term | Meaning |
|---|---|
| **unit** | One migratable definition from your Dagster repo (an asset, schedule, sensor, resource, ...). The manifest has one record per unit |
| **manifest** | The JSON file the scanner emits: every unit, its classification, and its migration state. The single source of truth for progress |
| **MECH / JUDG / REDESIGN / NONE** | Classification per unit: mechanical translation / needs judgment / semantics differ, redesign / no Airflow equivalent, documented mitigation. The manifest embeds this legend too |
| **disposition** | How a unit ended: `complete` (migrated, gates passed) or `deferred` (not migrated, with a written reason). Every unit must end as one or the other |
| **translation** | Turning a Dagster construct into its Airflow form (an asset becomes a DAG task with an asset outlet) |
| **equivalence row** | One line per schedule/sensor/trigger in the migration report: what it was, what it became, and the behavioral difference in one sentence |
| **gate / ladder** | The six validation steps each unit climbs (lint → import → structure → execution → data parity → idempotency), cheapest first |

## Prerequisites

- `python3` (commands in these docs say `python3`; bare `python` may not exist on macOS)
- `astro` CLI + Docker (needed from Phase 2 onward, not for the first hour)
- Read access to the Dagster repo; ideally the Dagster instance stays running (its outputs become your parity fixtures)

## Hour one, literally

```bash
# 1. Make a working directory for the migration run (NOT inside either project)
mkdir dagster-migration && cd dagster-migration

# 2. Scan the Dagster repo. Read-only; touches nothing.
python3 <path-to-skill>/scripts/inventory.py <path-to-dagster-repo> --out manifest.json

# 3. Better: rerun with the PROJECT's venv for runtime enrichment. Activate the
# venv (or put its bin on PATH) rather than calling its python directly: dbt
# projects need the venv's `dbt` executable resolvable, and dagster-dbt projects
# also need DAGSTER_IS_DEV_CLI=1 to prepare their manifest.
source <dagster-repo-venv>/bin/activate
DAGSTER_IS_DEV_CLI=1 python <path-to-skill>/scripts/inventory.py <path-to-dagster-repo> --runtime --out manifest.json
# (if runtime mode can't run, you get a loud STATIC-ONLY banner; the static manifest still stands)
# If the project's lockfile won't install (monorepo-relative sources), create a fresh
# venv and `pip install -e <path-to-dagster-repo>` instead; runtime mode only needs imports to resolve.

# 4. Look at what you have
python3 <path-to-skill>/scripts/status.py --manifest manifest.json summary
```

Open `manifest.json` and skim: `counts` tells you what kinds of definitions you have, and anything `spelling: "deprecated"` deserves a close look. Classifications start `pending`; the driving agent assigns MECH/JUDG/REDESIGN/NONE per record from the concept map during Phase 1 (a high MECH share afterward means an easier migration). The `legend` field decodes the tags.

The manifest lives HERE in your run directory for now. Later (Phase 2, once `astro dev init` has created the Astro project) you copy it to the project's `include/inventory/manifest.json` so the structural tests can find it; the run-dir copy stays canonical.

A `<unit-id>` in any `status.py` command is a key of the manifest's `units` map (shaped `kind:name`, e.g. `asset:daily_sales`); `status.py show` lists them. One editing rule, worth learning before it bites: the PLAN fields on a unit (`dag_id`, `task_count`, `edges`, `schedule`, `asset_outlets`, `target`) are yours to fill during planning. The STATE field (`status`) is never hand-edited; it only moves via `status.py advance / defer / reopen`.

## What to do with the skill itself

Point Claude Code at the skill (`SKILL.md`) with your Dagster repo and the manifest; it drives the workflow phase by phase and routes itself to the reference files. Your job is the judgment calls it surfaces: reviewing classifications, choosing DAG boundaries, approving per-edge IO decisions, and reading the migration report skeptically.

## When to pull in a senior engineer

Self-serve: reading the manifest, the reference routing table, running gates 1-3, MECH units. Escalate: any REDESIGN/NONE row on a pipeline you don't fully understand, the per-edge IO decisions on partitioned warehouse tables (`reference/io-and-data-passing.md` explains why they're the sharp edge), anything in the playbook you hit twice, and everything in the cutover phase.

## What can this break?

Until cutover: nothing. The scanner is read-only; the generated Astro project is a separate directory; gates 1-4 run against local/dev environments; Dagster remains the system of record and keeps running. The first action with production consequences is flipping a schedule in the cutover phase, and that has its own checklist (`reference/astro-deployment.md`) with rollback as step one's mirror.
