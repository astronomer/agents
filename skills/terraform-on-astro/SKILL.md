---
name: terraform-on-astro
description: Provisions and manages Astro Hosted infrastructure as code with the astronomer/astro Terraform provider - workspaces, deployments, teams, custom roles and role bindings, SSO/SCIM-referenced teams, and API tokens. Use when the user wants to write or review Terraform/HCL for Astro, mentions the astro Terraform provider, astro_workspace, astro_deployment, astro_team, astro_team_roles, astro_custom_role, or astro_api_token, or asks to design a multi-team/multi-workspace ownership model, provision a CI/CD deploy token via Terraform, or automate Astro RBAC.
---

# Terraform on Astro

The `astronomer/astro` provider manages Astro Hosted through the Platform and IAM APIs: workspaces, deployments, teams, role bindings, custom roles, and API tokens. It is under active development — required attributes, replace-on-change behavior, and enum values move between releases. Do not write HCL from memory or from a prior conversation; verify resource and attribute names against the live schema first.

> **Cross-references**: `managing-astro-deployments` and `deploying-airflow` for Astro CLI-based deploys once infrastructure exists; `setting-up-astro-project` for scaffolding the Airflow project that runs inside a Deployment this provider creates.

---

## Step 1 — Provider setup

```hcl
terraform {
  required_providers {
    astro = {
      source  = "astronomer/astro"
      version = "~> X.Y" # check the current series before pinning - see Step 1 note below
    }
  }
}

provider "astro" {
  organization_id = var.organization_id
  # token falls back to the ASTRO_API_TOKEN environment variable if omitted here
}
```

- **Version**: do not assume a version number from memory or from an older example is still current — this provider has shipped multiple major-version bumps. Check the current series at the [Terraform Registry provider page](https://registry.terraform.io/providers/astronomer/astro/latest) or the [GitHub releases page](https://github.com/astronomer/terraform-provider-astro/releases) before writing a `version` constraint, then commit `.terraform.lock.hcl` after the first `terraform init` so the pin is reproducible.
- **Auth**: `ASTRO_API_TOKEN` environment variable (recommended — keeps the token out of committed HCL) or the `token` attribute in the provider block. Use an Organization-scoped API token for anything touching Organization-, Team-, or custom-role resources; a Workspace- or Deployment-scoped token can only manage resources inside its own scope (see the token-scope gotcha below).
- **`organization_id`**: required on every provider block.
- **`host`**: optional, defaults to the production API host; only override it for a non-production Astronomer control plane.

---

## Step 2 — Resource and data source map

This is the only place these names are hardcoded. Confirm each one still exists and check its current attributes with Step 3 before writing HCL — the provider adds and renames attributes across releases.

| Concern | Resource | Data source(s) |
|---|---|---|
| Organization metadata | — | `astro_organization` |
| Workspaces | `astro_workspace` | `astro_workspace`, `astro_workspaces` |
| Deployments | `astro_deployment` | `astro_deployment`, `astro_deployments`, `astro_deployment_options` (valid enums, Runtime versions) |
| Clusters (customer-hosted infra) | `astro_cluster` | `astro_cluster`, `astro_clusters`, `astro_cluster_options` |
| Hybrid cluster ↔ workspace authorization | `astro_hybrid_cluster_workspace_authorization` | — |
| Teams (Terraform-managed only) | `astro_team` | `astro_team`, `astro_teams` |
| Team membership (managed independently of `astro_team`) | `astro_team_membership` | — |
| Role bindings for a Team that exists outside Terraform | `astro_team_roles` | — |
| Individual (non-Team) user role bindings | `astro_user_roles` | `astro_user`, `astro_users` |
| User invitations (local/no-SSO mode only) | `astro_user_invite` | — |
| Custom roles (Deployment or DAG scope only) | `astro_custom_role` | `astro_custom_role` |
| API tokens (Organization/Workspace/Deployment scoped) | `astro_api_token` | `astro_api_token`, `astro_api_tokens` |
| Remote-execution agent tokens | `astro_agent_token` | — |
| Alerts | `astro_alert` | `astro_alert`, `astro_alerts` |
| Notification channels | `astro_notification_channel` | `astro_notification_channel`, `astro_notification_channels` |

Notable absence: there is no "SCIM" resource. SCIM-synced Teams are never created by Terraform — they are looked up with the `astro_teams`/`astro_team` data sources (the `is_idp_managed` attribute tells you which) and given access with `astro_team_roles`. See the identity-mode table in Step 4.

---

## Step 3 — Discover the live schema before writing HCL

Two live sources, both regenerated every provider release:

```bash
# 1. The schema of whatever version is actually pinned in this project
terraform init
terraform providers schema -json \
  | jq '.provider_schemas["registry.terraform.io/astronomer/astro"].resource_schemas.astro_deployment.block.attributes | keys'

# Full attribute detail (required/optional/computed, replace-on-change) for one resource
terraform providers schema -json \
  | jq '.provider_schemas["registry.terraform.io/astronomer/astro"].resource_schemas.astro_custom_role.block'
```

```text
# 2. Human-readable docs, versioned per release
https://registry.terraform.io/providers/astronomer/astro/latest/docs
```

Pick the exact provider version at the top of the Registry docs page before reading a resource page — the attribute list you see is pinned to that version, not to "latest" by default. Prefer `terraform providers schema -json` when in doubt: it reflects the version actually resolved in this project's lock file, not whatever the docs site currently shows.

---

## Step 4 — Ownership topology decision guide

### Workspace pattern

| Situation | Pattern |
|---|---|
| One team, still exploring, few pipelines | **Single workspace** — one `astro_workspace`, Deployments separated by environment, no Teams needed. |
| Environment isolation matters more than team separation | **Workspace per environment** — one `astro_workspace` per environment (dev/stage/prod), every team's Deployments inside it. |
| Multiple teams need their own access boundary | **Workspace per team** — one `astro_workspace` per team; role bindings scope to it. |
| Multiple teams and strict production boundaries | **Workspace per team and environment** — the cross product of the two previous patterns. |
| Many small teams, one platform-run Deployment, separated by DAG ownership rather than infrastructure | **Shared Deployment, DAG-scoped roles** — one `astro_deployment`, `dag_roles` bound by `dag_id` or `tag` per team. Every Deployment referenced in `dag_roles` still needs a matching entry in `deployment_roles` (for example `DEPLOYMENT_ACCESSOR`), and that Deployment's Workspace needs a `workspace_roles` entry — the hierarchy has to be declared at every parent scope, not just the leaf. |
| Platform team wants to standardize guardrails while letting domain teams run their own Deployment lifecycle | **Decentralized ownership (platform-bootstrap + team-owned)** — see below. |

These patterns compose rather than replace each other — decentralized ownership is commonly layered on top of workspace-per-team, not used alone.

**Decentralized ownership** splits into two Terraform roots by *token scope*, not just by folder:

- A **platform-bootstrap** root, run with an Organization-scoped token: creates each team's `astro_workspace`, all `astro_team_roles` bindings (including a Workspace-level role for the team so it covers Deployments the team creates later), and a Workspace-scoped `astro_api_token` handed off to the team.
- A **team-owned-deployments** root, run with that Workspace-scoped token: looks up its Workspace with `data "astro_workspace"`, then creates and manages its own `astro_deployment` and Deployment-scoped `astro_api_token` resources.

The split exists because a Workspace-scoped token cannot perform Organization-level operations (`astro_team_roles`, `data "astro_teams"`, custom-role management) — see the token-scope gotcha below. Hand off the Workspace token through a secrets manager or your CI/CD platform's secret store, not a committed file; the bootstrap root's output for it should be marked `sensitive = true`.

### Identity mode

| Mode | Team resource | Pattern |
|---|---|---|
| SSO with SCIM (recommended where available) | none — the IdP owns Teams | `data "astro_teams"` by name, access granted with `astro_team_roles` |
| SSO only, no SCIM | `astro_team` | Terraform owns Team creation and membership |
| No SSO (local users) | `astro_team` + `astro_user_invite` | rare, last resort |

Guard every SCIM name lookup with a `lifecycle.postcondition` on the data source (a plain `check` block only warns and lets a mismatched apply continue) — an IdP group name that doesn't match exactly should fail the plan, not silently bind the wrong Team or an empty result.

---

## Step 5 — Canonical example

Workspace, a SCIM-referenced Team bound to it, a Deployment-scoped custom role restricted to that Workspace, a Deployment, and a CI/CD API token that uses the custom role. Adapt attribute names per Step 3.

```hcl
data "astro_teams" "data_platform" {
  names = ["Data Platform Authors"]

  lifecycle {
    postcondition {
      condition     = length(self.teams) == 1 && self.teams[0].is_idp_managed
      error_message = "Expected exactly one IdP-managed Team named 'Data Platform Authors' - compare against the exact group name in your identity provider."
    }
  }
}

resource "astro_workspace" "data_platform" {
  name                  = "Data Platform"
  description           = "Workspace owned by the Data Platform team."
  cicd_enforced_default = true
}

resource "astro_custom_role" "deploy_editor" {
  name        = "Data Platform CICD Deployment Editor"
  description = "Minimum permissions for automated deploys."
  scope_type  = "DEPLOYMENT"
  permissions = [
    "deployment.get",
    "deployment.deploys.create",
  ]
  restricted_workspace_ids = [astro_workspace.data_platform.id]
}

resource "astro_team_roles" "data_platform_authors" {
  team_id           = data.astro_teams.data_platform.teams[0].id
  organization_role = "ORGANIZATION_MEMBER"

  workspace_roles = [{
    workspace_id = astro_workspace.data_platform.id
    role         = "WORKSPACE_AUTHOR"
  }]
}

resource "astro_deployment" "prod" {
  name           = "Data Platform Prod"
  description    = "Production Deployment for the Data Platform team."
  type           = "STANDARD"
  workspace_id   = astro_workspace.data_platform.id
  cloud_provider = "AWS"
  region         = "us-east-1"
  executor       = "ASTRO"

  is_development_mode   = false
  scheduler_size        = "MEDIUM"
  is_high_availability  = true
  is_cicd_enforced      = true
  is_dag_deploy_enabled = true

  default_task_pod_cpu    = "0.25"
  default_task_pod_memory = "0.5Gi"
  resource_quota_cpu      = "10"
  resource_quota_memory   = "20Gi"

  contact_emails        = ["data-platform@example.com"]
  environment_variables = []

  worker_queues = [{
    name               = "default"
    is_default         = true
    astro_machine      = "A5"
    max_worker_count   = 10
    min_worker_count   = 0
    worker_concurrency = 1
  }]
}

resource "astro_api_token" "deploy" {
  name        = "CICD Data Platform Prod"
  description = "Deployment-scoped token for CI/CD deploys."
  type        = "DEPLOYMENT"

  expiry_period_in_days = 90

  roles = [{
    role        = astro_custom_role.deploy_editor.name
    entity_id   = astro_deployment.prod.id
    entity_type = "DEPLOYMENT"
  }]

  # Custom roles bind by name string, not by resource reference, so Terraform
  # infers no dependency here - it must be declared explicitly.
  depends_on = [astro_custom_role.deploy_editor]
}

output "deploy_token" {
  value     = astro_api_token.deploy.token
  sensitive = true
}
```

---

## Step 6 — Gotchas (verified against provider source)

- **SCIM disables Team writes entirely.** Once SCIM is enabled on the Organization, `astro_team` create/update/delete fails outright with `Invalid Configuration: Cannot create, update or delete a Team resource when SCIM is enabled`. Reference SCIM-managed Teams with `data "astro_teams"`/`data "astro_team"` and grant access with `astro_team_roles` instead. Adopting SCIM on an Organization that previously had Terraform-managed Teams is a migration (rebuild bindings as `astro_team_roles`), not a toggle.
- **`astro_team.member_ids` and `astro_team_membership` conflict.** Both write the same underlying membership state; using both for the same Team causes conflicting applies. Pick one management style per Team and keep it there.
- **Custom roles are Deployment- or DAG-scoped only.** `astro_custom_role.scope_type` accepts only `DEPLOYMENT` or `DAG` and forces a resource replacement if changed. There is no custom-role scope for Organization or Workspace access — those always use the fixed built-in role enums (for example `WORKSPACE_AUTHOR`, `ORGANIZATION_MEMBER`) on `workspace_roles`/`organization_role`.
- **Role hierarchy must be declared at every parent scope.** A `deployment_id` in `deployment_roles` must belong to a Workspace that also has an entry in `workspace_roles`; a Deployment referenced in `dag_roles` must also appear in `deployment_roles`. This is enforced by the API, not just style — a binding that skips a parent scope fails, and the failure doesn't say "add the missing parent."
- **Roles bind by name string, not by ID.** `deployment_roles`, `dag_roles`, and API token `roles` all take the role as a plain string — either a built-in role name or a custom role's `name` attribute. Terraform therefore infers no implicit dependency between a custom role and whatever names it; add `depends_on` explicitly, and expect a short propagation delay before a freshly created role or binding is usable.
- **Never key `for_each` on display names.** Names (`astro_workspace.name`, `astro_team.name`, `astro_deployment.name`, `astro_custom_role.name`) can all be renamed in place with no `RequiresReplace` on the `name` attribute — but `for_each`/module keys are resource addresses, so keying on a name turns an in-place rename into a destroy-and-recreate. Key on a stable logical identifier (an environment key, a team key) and keep the display name as a value.
- **`ASTRO` executor requires a `default` worker queue unless remote execution is configured.** The schema's own description suggests `worker_queues` is only for `CELERY`, but the provider validates that any Deployment using the `ASTRO` executor without `remote_execution` set must include at least one worker queue named `default` — omitting it fails with `worker_queues is required for 'ASTRO' executor`.
- **`is_development_mode` is one-directional.** Turning it on after creation (`false` → `true`) replaces the Deployment; turning it off does not. It's required for `STANDARD`/`DEDICATED` Deployments and disallowed for `HYBRID`.
- **`workspace_id`, `type`, `cloud_provider`, `region`, `cluster_id`, and `original_astro_runtime_version` all force replacement if changed** on `astro_deployment`. Treat a Runtime-version pin as creation-time only — ship upgrades through an image deploy, not by editing the pin.
- **API tokens are computed, sensitive, and stored in Terraform state in plaintext.** `astro_api_token.token` has no ephemeral or write-only equivalent in this provider as of this writing — creating a token in Terraform means the secret lives in state, so use a remote, access-controlled backend, or create tokens out of band (Astro UI or API) and hand them to CI/CD directly, keeping them out of state entirely.
- **A token can only manage resources inside its own scope.** Organization-, Workspace-, and Deployment-scoped tokens (`astro_api_token.type`) are strictly nested: a Workspace-scoped token cannot create `astro_team_roles` or read `data "astro_teams"` (both Organization-level operations), even against its own Workspace. An authorization failure on `plan`/`apply` usually means the configured token (`ASTRO_API_TOKEN` or provider `token`) is missing, expired, or scoped narrower than the resource being managed — not a bug in the HCL. This is exactly why decentralized-ownership splits into a platform root (Organization token) and a team root (Workspace token).

---

## Step 7 — Safety checklist

- [ ] Provider version checked against the current Registry/GitHub release before pinning — not copied from an old example.
- [ ] `.terraform.lock.hcl` committed after the first `terraform init`.
- [ ] `ASTRO_API_TOKEN` (or the `token` attribute) scoped no wider than the resources this root manages; Organization-level resources (`astro_team_roles`, `astro_team`, `astro_custom_role`, `data.astro_teams`) need an Organization-scoped token.
- [ ] SCIM status checked before choosing `astro_team` vs. `data "astro_teams"` + `astro_team_roles`.
- [ ] No Team uses both `member_ids` and `astro_team_membership`.
- [ ] Every `deployment_roles`/`dag_roles` entry has its parent `workspace_roles`/`deployment_roles` entry.
- [ ] `for_each`/module keys are stable logical identifiers, never display names.
- [ ] `ASTRO`-executor Deployments have a `default` worker queue unless `remote_execution` is set.
- [ ] `restricted_workspace_ids` set on any custom role that isn't intentionally Organization-wide.
- [ ] API tokens created in Terraform: state is stored in a remote, access-controlled backend, and the token output is marked `sensitive = true`.
- [ ] `terraform plan` reviewed for unexpected replacements on `workspace_id`, `type`, `cloud_provider`, `region`, `cluster_id`, `original_astro_runtime_version`, or `scope_type` before applying.

---

## References

Live-fetched, not hardcoded:

```text
https://registry.terraform.io/providers/astronomer/astro/latest        # current version, changelog
https://registry.terraform.io/providers/astronomer/astro/latest/docs   # per-resource schema, versioned
https://github.com/astronomer/terraform-provider-astro                 # source, examples/, docs/guides/
```

```bash
terraform providers schema -json | jq '.provider_schemas["registry.terraform.io/astronomer/astro"]'
```

## Related skills

- **managing-astro-deployments** — Astro CLI operations (auth, workspace switching, deploys) once Terraform has provisioned the Workspace and Deployment.
- **deploying-airflow** — CI/CD deploy strategies that consume the API tokens this provider creates.
- **setting-up-astro-project** — scaffolding the Airflow project that runs inside a Terraform-created Deployment.
