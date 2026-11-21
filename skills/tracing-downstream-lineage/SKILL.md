---
name: tracing-downstream-lineage
description: Trace downstream data lineage and impact analysis. Use when the user asks what depends on this data, what breaks if something changes, downstream dependencies, or needs to assess change risk before modifying a table or DAG.
---

# Downstream Lineage: Impacts

Answer the critical question: "What breaks if I change this?"

Use this BEFORE making changes to understand the blast radius.

<!-- astro-cli-version:start -->
## Astro CLI version

Commands in this skill, including its reference files, are written for Astro CLI v2. Before anything else, run this as a command of its own, with nothing chained before or after it, and choose the dialect from what it prints: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`
On Windows `cmd.exe`, which has no `/dev/null`, run `astro local af --help >NUL 2>&1 && echo v2 || echo v1` instead.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI. Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` and `--output json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is the line under it, starting `# v1:`. Where something behaves differently on v1, a line starting **v1:** says how. If `af` is not on PATH, write `uvx --from astro-airflow-mcp af <args>` out in full in every command. Don't put it in a shell variable or alias: zsh won't split `$AF`, and shell state doesn't carry over between commands.
- v2 replaced `astro dev` with `astro local`; `astro dev <cmd>` on v2 fails and names its replacement.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project, although the probe printed v2. Switch to the v1 forms: the standalone `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.
- `-d` and `-o` mean deployment and output in v2, but DAG id and offset in v1, so never carry either into a v1 command. `--dag-id`, `--offset`, `--state`, `--limit`, `--try`, `--map-index`, and `--timeout` mean the same in both.
- If a command here, or in the project's `AGENTS.md`, disagrees with the installed CLI, trust the CLI: check `astro <cmd> --help` (v1: `af <cmd> --help` or `astro dev <cmd> --help`).
<!-- astro-cli-version:end -->

## Impact Analysis

### Step 1: Identify Direct Consumers

Find everything that reads from this target:

**For Tables:**

1. **Search DAG source code**: Look for DAGs that SELECT from this table
   - Use `astro local af dags list` to get all DAGs
   - Use `astro local af dags source <dag_id>` to search for table references
   - Look for: `FROM target_table`, `JOIN target_table`

2. **Check for dependent views**:
   ```sql
   -- Snowflake
   SELECT * FROM information_schema.view_table_usage
   WHERE table_name = '<target_table>'

   -- Or check SHOW VIEWS and search definitions
   ```

3. **Look for BI tool connections**:
   - Dashboards often query tables directly
   - Check for common BI patterns in table naming (rpt_, dashboard_)

### On Astro

If you're running on Astro, the **Lineage tab** in the Astro UI provides visual dependency graphs across DAGs and datasets, making downstream impact analysis faster. It shows which DAGs consume a given dataset and their current status, reducing the need for manual source code searches.

**For DAGs:**

1. **Check what the DAG produces**: Use `astro local af dags source <dag_id>` to find output tables
2. **Then trace those tables' consumers** (recursive)

### Step 2: Build Dependency Tree

Map the full downstream impact:

```
SOURCE: fct.orders
    |
    +-- TABLE: agg.daily_sales --> Dashboard: Executive KPIs
    |       |
    |       +-- TABLE: rpt.monthly_summary --> Email: Monthly Report
    |
    +-- TABLE: ml.order_features --> Model: Demand Forecasting
    |
    +-- DIRECT: Looker Dashboard "Sales Overview"
```

### Step 3: Categorize by Criticality

**Critical** (breaks production):
- Production dashboards
- Customer-facing applications
- Automated reports to executives
- ML models in production
- Regulatory/compliance reports

**High** (causes significant issues):
- Internal operational dashboards
- Analyst workflows
- Data science experiments
- Downstream ETL jobs

**Medium** (inconvenient):
- Ad-hoc analysis tables
- Development/staging copies
- Historical archives

**Low** (minimal impact):
- Deprecated tables
- Unused datasets
- Test data

### Step 4: Assess Change Risk

For the proposed change, evaluate:

**Schema Changes** (adding/removing/renaming columns):
- Which downstream queries will break?
- Are there SELECT * patterns that will pick up new columns?
- Which transformations reference the changing columns?

**Data Changes** (values, volumes, timing):
- Will downstream aggregations still be valid?
- Are there NULL handling assumptions that will break?
- Will timing changes affect SLAs?

**Deletion/Deprecation**:
- Full dependency tree must be migrated first
- Communication needed for all stakeholders

### Step 5: Find Stakeholders

Identify who owns downstream assets:

1. **DAG owners**: Check `owners` field in DAG definitions
2. **Dashboard owners**: Usually in BI tool metadata
3. **Team ownership**: Look for team naming patterns or documentation

## Output: Impact Report

### Summary
"Changing `fct.orders` will impact X tables, Y DAGs, and Z dashboards"

### Impact Diagram
```
                    +--> [agg.daily_sales] --> [Executive Dashboard]
                    |
[fct.orders] -------+--> [rpt.order_details] --> [Ops Team Email]
                    |
                    +--> [ml.features] --> [Demand Model]
```

### Detailed Impacts

| Downstream | Type | Criticality | Owner | Notes |
|------------|------|-------------|-------|-------|
| agg.daily_sales | Table | Critical | data-eng | Updated hourly |
| Executive Dashboard | Dashboard | Critical | analytics | CEO views daily |
| ml.order_features | Table | High | ml-team | Retraining weekly |

### Risk Assessment

| Change Type | Risk Level | Mitigation |
|-------------|------------|------------|
| Add column | Low | No action needed |
| Rename column | High | Update 3 DAGs, 2 dashboards |
| Delete column | Critical | Full migration plan required |
| Change data type | Medium | Test downstream aggregations |

### Recommended Actions

Before making changes:
1. [ ] Notify owners: @data-eng, @analytics, @ml-team
2. [ ] Update downstream DAG: `transform_daily_sales`
3. [ ] Test dashboard: Executive KPIs
4. [ ] Schedule change during low-impact window

### Related Skills
- Trace where data comes from: **tracing-upstream-lineage** skill
- Check downstream freshness: **checking-freshness** skill
- Debug any broken DAGs: **debugging-dags** skill
- Add manual lineage annotations: **annotating-task-lineage** skill
- Build custom lineage extractors: **creating-openlineage-extractors** skill
