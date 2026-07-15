# Platform: Dagster+ / OSS instance → Astro

> **STATUS: reviewed; hardened in testing** (dagster-open-platform platform layer).

Everything outside the DAG code: topology, config, secrets, CI/CD, alerting, observability, and the cutover itself.

## Topology

| Dagster+ | Astro | Class | Notes |
|---|---|---|---|
| Organization / full deployment (prod, staging) | Workspace + one Deployment per env | JUDG | |
| Code location (in `dagster_cloud.yaml` `locations`) | Usually one Astro project per code location; small/coupled locations can merge into one project | JUDG | Team ownership and dependency isolation drive the call |
| `agent_queue` routing (e.g. EU location on EU agents) | Separate Astro Deployment in the right region | JUDG | Data-residency boundaries become Deployment boundaries; each has its own image registry |
| Serverless | Astro hosted | JUDG | |
| Hybrid agent (K8s/ECS/Docker) | Astro hosted, or dedicated/hybrid options | JUDG | Most Hybrid users migrate to hosted; keep network access requirements in view |
| Private-network sources reachable only from the agent (VPN/Tailscale hostnames, VPC-internal DBs) | Explicit reachability plan per connection | JUDG | Invisible in code until the first run fails (verified in testing). For every Connection in the secrets map ask: reachable from Astro's workers? Answer decides hosted vs dedicated/VPC peering, and gates Gate 4 for entire ingest domains |

## `dagster_cloud.yaml` → Astro project

Per location: `code_source` (package/module/file) has no Airflow equivalent, DAG files in `dags/` are the unit; `build.directory`/`registry` and `image` map to the Astro project `Dockerfile` and Astro's managed image build (`astro deploy` builds and pushes); `working_directory`/`executable_path` disappear (the Runtime image defines the environment); `container_context` is where the real content lives:

| `container_context` key | Astro | Class |
|---|---|---|
| `k8s.env_vars` | Deployment environment variables (UI/API/`astro deployment variable`) | MECH |
| `k8s.env_secrets` (named K8s secrets) | Astro Environment secrets (secret env vars) and/or Airflow Connections | JUDG |
| `k8s.namespace`, `service_account_name`, `server_k8s_config`, `run_k8s_config` | Managed by Astro; per-task pod tweaks via `executor_config`/`pod_override` | JUDG |
| `ecs.*` (task roles, subnets, security groups) | Astro workload identity / cloud connection config | JUDG |

**Secrets naming map.** Build this table during inventory and fill the right column deliberately; nothing does it automatically:

| Dagster reference | Kind | Astro target |
|---|---|---|
| `EnvVar("SNOWFLAKE_PASSWORD")` | resource credential | Airflow Connection `snowflake_default` (password field) |
| `env_secrets: [cloud-ops-slack-token]` | K8s secret NAME (not an env var) | The secret object's KEYS are the env-var names, and they are not in dagster_cloud.yaml; inspect the cluster (`kubectl get secret cloud-ops-slack-token -o yaml`) to enumerate them, then map each key to an Astro secret env var or Connection |
| `os.getenv(...)` at definition load | plain env var | Deployment env var (note: load-time in Dagster, parse-time in Airflow) |

Snowflake specifics (verified in testing): key-pair auth wires via the Connection's `extra.private_key_file` pointing at a gitignored mounted key (never `private_key_content` in a committed file), and dbt-snowflake's profile takes `private_key_path`; pin `session_parameters` (TIMEZONE, TIMESTAMP_TYPE_MAPPING) on the Connection to match the Dagster resource's session, because window predicates can silently change meaning under different mappings (see `io-and-data-passing.md`).

Rule of thumb: anything a provider Hook can consume becomes a Connection (typed, per-Deployment, testable); everything else becomes a Deployment env var, secret-flagged when sensitive.

## CI/CD and branch deployments

Dagster+ branch deployments (ephemeral per-PR deployments) map to **Astro preview Deployments**: per-branch ephemeral Deployments created/deleted by CI, mirroring a base Deployment's config. The `astronomer/deploy-action` GitHub Action ships sub-actions for the full lifecycle (create on branch create, deploy on push, delete on branch delete, deploy to base on merge). Templates: astronomer.io/docs/astro/ci-cd-templates/github-actions-deployment-preview.

| Dagster+ | Astro | Class |
|---|---|---|
| `dg plus deploy` / `dagster-cloud ci` pipeline | `astro deploy` in CI (deploy-action or plain CLI) | MECH |
| Branch deployment per PR | Preview Deployment per branch | JUDG |
| Change Tracking on branch deployments | PR diff + preview Deployment testing; no direct asset-diff feature | NONE (document) |
| `DAGSTER_CLOUD_IS_BRANCH_DEPLOYMENT`, `DAGSTER_CLOUD_PULL_REQUEST_ID` **referenced in code** | Rewrite against env vars you set on preview Deployments in CI | JUDG |

That last row is a code-migration task, not a platform task: grep the repo for `DAGSTER_CLOUD_` before claiming the platform layer is done. Real projects do exactly this (PR-numbered database clones in the dbt translator; see `dbt.md`).

## Alerting

Dagster+ alert policies map onto Astro alerts (UI-configured, no DAG code) plus Airflow-level callbacks for in-code reactions. Real deployments usually configure alerts in the Dagster+ UI with NOTHING in the repo (verified in testing): the migration plan needs an export-at-cutover step (pull live alert policies via the UI/API) rather than assuming an `alert_policies` YAML exists. Likewise, verify each `dagster_cloud.yaml` code location's module actually exists in the repo you're migrating; mirrors and partial checkouts lie.

| Dagster+ `event_types` | Astro alert type | Class |
|---|---|---|
| `JOB_FAILURE` / `JOB_SUCCESS` | DAG Failure / DAG Success | MECH |
| `JOB_LONG_RUNNING` | DAG Duration / Task Duration | MECH |
| `ASSET_MATERIALIZATION_FAILURE`, `ASSET_CHECK_*` | Task Failure on the translated task/check task | JUDG |
| `ASSET_FRESHNESS_PASS/WARN/FAIL` | DAG Timeliness alert and/or Astro Observe freshness SLA | JUDG |
| `TICK_FAILURE` | No direct analog (scheduler-level); Deployment Health | NONE (document) |
| `AGENT_UNAVAILABLE`, `CODE_LOCATION_ERROR` | Deployment Health (preview) / not applicable on hosted | JUDG |
| `INSIGHTS_CONSUMPTION_EXCEEDED` | No direct analog | NONE |

Channels line up: email/slack/pagerduty/microsoft_teams on both sides; Astro adds Opsgenie and DAG Trigger (fire a DAG via REST on alert), which can replace simple `@run_failure_sensor` remediation patterns.

## Observability: Insights and the asset catalog

- **Dagster+ Insights** (cost, credits, per-asset compute, freshness pass rate) → **Astro Observe** (GA): SLA dashboards for freshness/timeliness, data products (asset compositions with inferred dependencies), predictive alerting, pipeline health overview. Freshness/timeliness/health coverage is good. Cost accounting: Astro Observe ships Snowflake Cost Management (pipeline-level warehouse spend); there is no per-asset credit accounting like Insights' credits view. State the difference at that granularity in the report.
- **Asset catalog + column-level lineage** → Airflow 3 asset views + Astro's OpenLineage-based lineage (enable per Deployment). Column-level lineage parity is partial; this is a documented loss (map section 12).
- Run/materialization **history is not migrated**. Keep the Dagster instance readable during the grace period; export anything contractually needed (materialization metadata is also the parity-test fixture source, see `validation.md`).

## OSS `dagster.yaml` → Airflow/Astro settings

| `dagster.yaml` | Target | Class |
|---|---|---|
| `run_coordinator.QueuedRunCoordinator.max_concurrent_runs` | Deployment-level concurrency + per-DAG `max_active_runs` | JUDG |
| `tag_concurrency_limits` | Airflow Pools on the translated tasks | JUDG |
| `concurrency.pools` (`pool=` on ops/assets) | Airflow Pools (same name, set slot counts) | MECH |
| `run_retries {enabled, max_retries}` | `default_args={"retries": n}` in shared DAG defaults | MECH |
| `run_monitoring` | Astro Deployment health + alerts | JUDG |
| `compute_logs` (S3/GCS managers) | Astro task logs (managed) | MECH |
| `storage` (postgres/mysql) | Managed by Astro (metadata DB is Astro's) | MECH |
| `retention.*` | Airflow DB cleanup policies / Astro defaults | JUDG |

## Preflight for Dagster+ hybrid shops (do this before planning the platform layer)

These four items gate cutover for hybrid deployments and are invisible in the repo code; they were day-one blockers in the at-scale eval. Each is a written answer, not a mental note:

1. **Network reachability, per connection**: for every Connection in the secrets map, can Astro's workers reach it (VPN/Tailscale hostnames, VPC-internal DBs)? The answer decides hosted vs dedicated/VPC peering and gates execution for entire ingest domains.
2. **Export Dagster+ UI-only config**: alert policies, and any connections/variables configured in the UI, exist NOWHERE in the repo. Pull them via the Dagster+ UI/API now; map them with the alert table below.
3. **Verify every `dagster_cloud.yaml` code location's module actually exists** in the repo you were handed; mirrors and partial checkouts lie.
4. **Enumerate K8s secret KEYS**: `env_secrets` names secret objects, not env vars; `kubectl get secret <name> -o yaml` per secret to build the real naming map.

## Cutover: the 10-step methodology, adapted for a Dagster source

Astronomer's Airflow-migration methodology (Prepare → metadata → code → cutover) adapts, with one honest caveat: **Starship does not apply to the Dagster leg.** It moves Airflow-to-Airflow metadata; Dagster has no Airflow metadata to move. The translation work upstream of this checklist is the whole skill.

1. Freeze new pipeline development on Dagster (freeze-old/build-new).
2. Create Workspace + Deployments (per env, per region) on Astro.
3. `astro dev init` the project(s); wire CI/CD (`astro deploy`, preview Deployments).
4. Build the secrets/connection naming map; create Connections + env vars per Deployment.
5. Migrate code domain-by-domain per the skill workflow (SKILL.md), validating each unit through the ladder in `validation.md`.
6. Run side-by-side: Dagster remains authoritative; Airflow DAGs run paused-or-shadowed until parity per domain.
7. Configure Astro alerts (+ Observe SLAs) from the alert-policy map above.
8. Flip schedules per domain (order rehearsal-verified, testing): unpause the Airflow CONSUMERS first, then the producer, then pause the Dagster schedule/sensor. Missed asset events never replay, so a consumer unpaused after its producer already ran has permanently skipped that event. Unpausing fires immediately: cron DAGs run the last missed tick (usually wanted); partition timetables run the CURRENT partition, which on a live domain is the in-progress window and yields PARTIAL data: time the flip just after a window closes, or pause-and-clear and backfill the completed window (unpause before backfilling; a paused DAG queues backfill runs forever). NEVER let both orchestrators run a single-writer-store domain concurrently: file-lock exclusion does NOT propagate across a Docker bind mount (host Dagster and containerized Airflow both got RW on the same DuckDB in the rehearsal), so an overlap corrupts with zero warning; the 1-slot pool protects within Airflow only. One domain per change window; rollback is the reverse (re-pause Airflow, unpause Dagster). "Shadow" running requires a separate storage prefix; with shared storage there is no shadow mode, only paused-until-flip.
9. Decommission Dagster compute per domain once its parity window passes; keep the instance readable.
10. After the last domain: export residual Dagster metadata, archive the repo, end the grace period.

## Env var migration checklist

Grep targets before declaring the platform layer done: `DAGSTER_CLOUD_` (all of them, especially `IS_BRANCH_DEPLOYMENT`, `PULL_REQUEST_ID`, `DEPLOYMENT_NAME`), `DAGSTER_DEPLOYMENT` (the OSS env-switch convention), `EnvVar(`, `env_secrets`, `os.getenv` inside `defs/`, and the **Insights code-level symbols**: `with_insights`, `InsightsBigQueryResource`, `InsightsSnowflakeResource`, `dagster_insights`. Insights is not platform-only config: those calls live in asset code and will import-error on Astro; strip them (their replacement is Astro Observe / OpenLineage at the platform layer, not an in-code call). Each hit gets a row in the secrets/env map with its Astro replacement, or an explicit "dead after migration" mark.
