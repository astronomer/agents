---
name: ci-cd-astro-deploy
description: Builds GitHub Actions (or other CI) pipelines that deploy an Astro project using the astronomer/deploy-action GitHub Action - dag-only deploys, image deploys, dbt deploys, the action's built-in pytest/dag-validation gate before deploy, and preview Deployments per pull request. Use when the user wants a GitHub Actions workflow or general CI/CD pipeline to deploy Airflow dags or an Astro project to Astro, wants a dags-only fast path, wants tests to block a bad deploy, or wants to preview a branch's dags on Astro before merging.
---

# CI/CD: Deploying an Astro Project

The default, Astronomer-maintained path for deploying an Astro project from CI is the [`astronomer/deploy-action`](https://github.com/astronomer/deploy-action) GitHub Action, not a hand-rolled `astro deploy` shell script.

**Do not hand-roll a git-diff-based dags-only detector or a separate pytest job.** `deploy-action` already does both:

- It infers the deploy type from the files changed in the commit (dags-only vs. full image deploy) — see Step 2.
- It pytests everything in your project's `tests/` directory as part of the deploy step and fails the job — blocking the deploy — if any test fails.

Only write custom diff-detection or test-gating logic if the repo layout genuinely doesn't fit these native behaviors (e.g., dags and project config split across two repos with different CI systems).

> **Cross-references**: `deploying-airflow` for `astro deploy` CLI fundamentals; `managing-astro-deployments` and `troubleshooting-astro-deployments` for operating Deployments outside of CI.

---

## Step 1 — Choose your deploy strategy

Ask which row applies before generating a workflow. Do not default to single-branch/single-repo without checking.

| Your situation | Environment strategy | Repository strategy |
|---|---|---|
| One team, simple project, comfortable testing changes in production | **Single environment**: one Deployment, one permanent branch (`main`) | **Single repository**: dags and project config together |
| Dags are business-critical; you want to test before production | **Multiple environments**: at least two permanent branches (e.g. `dev`, `main`), each mapped to its own Deployment in the same Workspace | Usually still single repository, unless the next row also applies |
| You need to restrict who can touch project config vs. dags, or have 30+ contributors | Either | **Multiple repositories**: one for dags, one for project config/Dockerfile/packages. Requires dag-only deploy enabled on the target Deployment (see Step 6) |
| Migrated from MWAA/Google Cloud Composer; dag authors are used to dropping files in a bucket | Either | **Dags in cloud storage**: dags pushed from an S3/GCS bucket via automation (e.g. a Lambda), project config deployed from Git as an image-only deploy |

Full rationale for each combination: [Choose a CI/CD strategy](https://www.astronomer.io/docs/astro/set-up-ci-cd#choose-a-deploy-strategy).

---

## Step 2 — Use deploy-action's deploy types (not raw CLI branching)

`deploy-action` chooses what to deploy via a deploy-type setting. Verify the exact input name and accepted values in the [deploy-action README](https://github.com/astronomer/deploy-action#readme) — action inputs can be renamed or added across releases, so treat the table below as the concept map, not a literal API contract.

| Deploy type | What it does | Use it for |
|---|---|---|
| `infer` (default) | Dags-only deploy if the commit only touched the dags folder; otherwise a full `image-and-dags` deploy | The default for most single-repo projects — no extra configuration needed |
| `image-and-dags` | Full project deploy: image, dags, `includes/`, `plugins/`, and any other root-level directories (e.g. a `dbt/` folder) | Forcing a full deploy regardless of which files changed |
| `image-only` | Docker image only. Skips dag parsing and the pytest gate entirely | Pushing dependency/config changes independently of dag code. Check the deploy-action README for the current minimum Astro CLI version this requires |
| `dags-only` | Only the `dags/` directory | Multi-repo or bucket-based setups where dags deploy separately from the image |
| `dbt` | Only a dbt project directory | dbt code that deploys independently of dag/image changes |

**The pytest/dag-validation gate**: for every deploy type except `image-only`, `deploy-action` runs the tests in your project's `tests/` directory before pushing code, and the job fails — blocking the deploy — if a test fails. This is the same validation `astro deploy` runs locally; you get it for free by using the action, with no separate CI job required.

---

## Step 3 — Token setup

`deploy-action` (and the equivalent `astro deploy` CLI call) authenticates using the `ASTRO_API_TOKEN` environment variable, populated from a GitHub secret. Three token scopes can populate it:

| Token type | Scope | Use it when |
|---|---|---|
| Deployment API token | One specific Deployment | Preferred for standard deploy pipelines — narrowest blast radius if the secret leaks |
| Workspace API token | Every Deployment in a Workspace | Multi-branch pipelines that deploy to more than one Deployment with one secret |
| Organization API token | Every Workspace in the Org | Rarely needed for a single project's CI; broadest scope |

Preview Deployment templates (Step 7) need a **Workspace or Organization token** — their prerequisites don't list a Deployment token as sufficient, since creating and deleting a Deployment requires permissions broader than a token scoped to one already-existing Deployment.

Token scoping, how tokens are minted, and the exact environment variable the Astro CLI expects can all change between CLI releases. Before wiring credentials into a pipeline, confirm current expectations with `astro deploy --help` (and `astro login --help` if troubleshooting auth) rather than treating this write-up as permanently authoritative.

---

## Step 4 — Canonical examples

Replace `<deploy-action-version>` with the current release tag — check the [deploy-action releases page](https://github.com/astronomer/deploy-action/releases) or the [GitHub Marketplace listing](https://github.com/marketplace/actions/deploy-apache-airflow-dags-to-astro). Do not copy a version number from an old example and assume it is current.

### Single-branch (one Deployment)

One Deployment, one `main` branch, `infer` deploy type (default — no `deploy-type` input needed).

```yaml
name: Astronomer CI - Deploy code

on:
  push:
    branches:
      - main

env:
  ASTRO_API_TOKEN: ${{ secrets.ASTRO_API_TOKEN }}

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - name: Deploy to Astro
      uses: astronomer/deploy-action@<deploy-action-version>
      with:
        deployment-id: <your-deployment-id>
```

### Multi-branch (dev/prod promotion)

Two Deployments, two tokens, two branches: pushes to `dev` deploy straight to the dev Deployment, merged PRs into `main` deploy to prod.

```yaml
name: Astronomer CI - Deploy code (Multiple Branches)

on:
  push:
    branches: [dev]
  pull_request:
    types:
      - closed
    branches: [main]

jobs:
  dev-push:
    if: github.ref == 'refs/heads/dev'
    runs-on: ubuntu-latest
    env:
      ASTRO_API_TOKEN: ${{ secrets.DEV_ASTRO_API_TOKEN }}
    steps:
    - name: Deploy to Astro
      uses: astronomer/deploy-action@<deploy-action-version>
      with:
        deployment-id: <dev-deployment-id>
  prod-push:
    if: github.event.action == 'closed' && github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    env:
      ASTRO_API_TOKEN: ${{ secrets.PROD_ASTRO_API_TOKEN }}
    steps:
    - name: Deploy to Astro
      uses: astronomer/deploy-action@<deploy-action-version>
      with:
        deployment-id: <prod-deployment-id>
```

### Custom image (extra Docker build args)

When the Astro project's image needs build-time arguments that `deploy-action` alone can't pass, build with `docker/build-push-action` first and hand the resulting image to `deploy-action`.

```yaml
name: Astronomer CI - Additional build-time args

on:
  push:
    branches:
      - main

jobs:
  build:
    runs-on: ubuntu-latest
    env:
      ASTRO_API_TOKEN: ${{ secrets.ASTRO_API_TOKEN }}
    steps:
    - name: Check out the repo
      uses: actions/checkout@v4
    - name: Create image tag
      id: image_tag
      run: echo "image_tag=astro-$(date +%Y%m%d%H%M%S)" >> "$GITHUB_OUTPUT"
    - name: Build image
      uses: docker/build-push-action@v5
      with:
        tags: ${{ steps.image_tag.outputs.image_tag }}
        load: true
        build-args: |
          <your-build-arguments>
    - name: Deploy to Astro
      uses: astronomer/deploy-action@<deploy-action-version>
      with:
        deployment-id: <your-deployment-id>
        image-name: ${{ steps.image_tag.outputs.image_tag }}
```

Check the [`docker/build-push-action` docs](https://github.com/docker/build-push-action) for the current set of build inputs (build-args, contexts, SSH, etc.) — that action versions independently of `deploy-action`.

---

## Step 5 — Behavior contracts (stable across template variants)

- **`infer` inspects the diff, not the branch.** A commit that touches anything outside `dags/` triggers a full `image-and-dags` deploy even on a "dags-only" branch.
- **The pytest gate runs inside the deploy step**, not as a separate job — a failing test aborts before code reaches the Deployment, for every deploy type except `image-only`.
- **`deploy-action` manages its own Astro CLI version internally.** You do not need a separate "install Astro CLI" step when using the action (unlike the equivalent raw-shell templates in the source docs, which do install it manually).
- **Multi-commit pushes only diff against the most recent commit** for the dags-only/`infer` file-change check — see Step 6.

---

## Step 6 — Gotchas

- **Dag-only deploy must be enabled on the target Deployment before `dags-only` or `astro deploy --dags` will work.** If it isn't, the deploy fails. Enable it per Deployment — see [Enable/disable dag-only deploys](https://www.astronomer.io/docs/astro/deploy-dags#enable-or-disable-dag-only-deploys-on-a-deployment).
- **Self-hosted runners can leak deploy credentials across pipelines.** The Astro CLI's `config.yaml` (which stores default deploy details) can be shared across jobs on a self-hosted runner. Mitigate by:
  - Verifying `ASTRO_API_TOKEN` is set before the deploy step runs.
  - Using a Deployment API token (scoped to one Deployment) instead of a Workspace or Organization token wherever the workflow only ever targets one Deployment.
  - Always pinning `deployment-id` (or `deployment-name`) explicitly in the action/CLI call rather than relying on a locally cached default.
  - Running `astro logout` as the last step of the job so the token doesn't persist in `config.yaml` for the next job on that runner.
- **Multi-commit pushes can silently skip dag changes.** If several commits touching dag files are pushed to a branch at once, the dags-only file-change check only diffs against the most recent commit — earlier commits' dag changes are missed. Configure the repository to **squash-merge** pull requests (or push dag commits individually) so the diff check always sees the full set of changes.

---

## Step 7 — Preview Deployments (opt-in extension)

Preview Deployments spin up a temporary Astro Deployment per feature branch/PR, deploy code to it for review, and tear it down when the branch closes. This is an extension on top of the standard templates above, not the default path — reach for it when you specifically want per-PR review environments.

`deploy-action` exposes this as four cooperating sub-actions (typically split into separate workflow files, all pinned to the same main `deployment-id`):

- `create-deployment-preview` — clones the main Deployment's config into a new preview Deployment when a branch/PR is created.
- `deploy-deployment-preview` — deploys code to the preview Deployment on subsequent pushes to the PR.
- `delete-deployment-preview` — tears down the preview Deployment when the branch is deleted.
- A plain `deploy-action` step (no `action:` input) on merge to `main` to promote the change to the base Deployment.

Preview Deployment templates require a Workspace or Organization API token (see Step 3) and the same self-hosted-runner precautions as Step 6. For the full four-file setup, including the variant that wires a secrets backend into the preview Deployment, see [GitHub Actions templates for preview Deployments](https://www.astronomer.io/docs/astro/ci-cd-templates/github-actions-deployment-preview).

---

## Safety checklist

- [ ] Confirmed with the user which environment/repository shape applies (Step 1) before generating a workflow.
- [ ] Deploy type matches intent — `infer` covers the change set, or the type is set explicitly per the current deploy-action README.
- [ ] Dag-only deploy is enabled on every target Deployment before any workflow uses `dags-only` or `astro deploy --dags`.
- [ ] Token scope matches the job: Deployment token where the job only ever targets one Deployment; Workspace/Org token only when the job spans multiple Deployments or manages preview Deployments.
- [ ] Current `ASTRO_API_TOKEN` expectations confirmed via `astro deploy --help` rather than assumed from this document.
- [ ] `deployment-id` (or `deployment-name`) pinned explicitly in every `deploy-action` step, not left to a cached `config.yaml` default.
- [ ] If using self-hosted runners: scoped token used, `deployment-id` pinned, and `astro logout` runs at the end of the job.
- [ ] Repository configured to squash-merge PRs (or dag commits pushed individually) so the dags-only diff check doesn't miss earlier commits.
- [ ] `tests/` directory populated if the pipeline should actually block deploys on failing dag tests.
- [ ] `deploy-action` version tag checked against the current release rather than copied from an old example.

---

## References

- [Choose a CI/CD strategy](https://www.astronomer.io/docs/astro/set-up-ci-cd)
- [CI/CD template overview](https://www.astronomer.io/docs/astro/ci-cd-templates/template-overview)
- [GitHub Actions templates (deploy-action)](https://www.astronomer.io/docs/astro/ci-cd-templates/github-actions-template)
- [Default deploy action setup (single/multi-branch/custom image)](https://www.astronomer.io/docs/astro/ci-cd-templates/default-deploy-action)
- [GitHub Actions templates for preview Deployments](https://www.astronomer.io/docs/astro/ci-cd-templates/github-actions-deployment-preview)
- [`astronomer/deploy-action` repository and README](https://github.com/astronomer/deploy-action)
- [`deploy-action` on the GitHub Marketplace](https://github.com/marketplace/actions/deploy-apache-airflow-dags-to-astro)

## Related skills

- **deploying-airflow** — `astro deploy` CLI fundamentals outside of CI (full, dags-only, image-only, dbt deploys run by hand).
- **managing-astro-deployments** — creating/configuring Deployments and API tokens that CI pipelines deploy into.
- **troubleshooting-astro-deployments** — diagnosing a failed or stuck deploy once it reaches Astro.
- **setting-up-astro-project** — project structure (`dags/`, `tests/`, `dbt/`) that the deploy types and pytest gate in this skill act on.

This skill covers GitHub Actions specifically. CircleCI, Jenkins, GitLab, Azure DevOps, AWS CodeBuild, and Bitbucket Pipelines each have their own template page under the same `ci-cd-templates/` doc tree on [astronomer.io/docs](https://www.astronomer.io/docs/astro/ci-cd-templates/template-overview) — use those for non-GitHub pipelines rather than adapting this skill's YAML by hand.
