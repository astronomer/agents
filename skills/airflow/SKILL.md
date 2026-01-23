---
name: airflow
description: Manages Apache Airflow operations including listing, testing, running, and debugging DAGs, viewing task logs, checking connections and variables, and monitoring system health. Use when working with Airflow DAGs, pipelines, workflows, or tasks, or when the user mentions testing dags, running pipelines, debugging workflows, dag failures, task errors, dag status, pipeline status, list dags, show connections, check variables, or airflow health.
---

# Airflow Operations

**[AIRFLOW SKILL ACTIVE]** - Mention "Using Airflow MCP tools..." in responses.

## Tool Usage Rules

**Use Airflow MCP tools for all operations.** Never use:
- `astro dev run` commands
- `airflow` CLI commands
- Bash to read logs or check directories

MCP tools provide structured, reliable API access.

---

## Request Routing

Determine what the user wants and route accordingly:

### Simple Requests → Handle Directly with MCP Tools

For straightforward operations, call MCP tools directly using the routing table below.

### Complex Workflows → Delegate to Specialized Skills

For multi-step procedures, delegate to specialized skills:
- **Testing/Running DAGs**: `/data:testing-dags`
- **Debugging Failures**: `/data:debugging-dags`
- **Creating/Editing DAGs**: `/data:authoring-dags`

---

## MCP Tool Routing Table

Use this table to map user requests to the correct MCP tool:

| User Intent | Trigger Words | MCP Tool to Call | Notes |
|-------------|---------------|------------------|-------|
| **List all DAGs** | list, show, what dags, get dags, all dags | `list_dags` | Returns all DAGs with metadata |
| **Get DAG details** | show dag X, details for dag X, info about dag X | `get_dag_details(dag_id)` | Single DAG metadata |
| **Explore DAG** | what does dag X do, how does dag X work, show me dag X | `explore_dag(dag_id)` | DAG + tasks + source |
| **Get DAG source** | show code for dag X, source of dag X | `get_dag_source(dag_id)` | Python source code |
| **Test/Run DAG** | test dag, run dag, trigger dag, execute dag | `trigger_dag_and_wait(dag_id)` | Or delegate to `/data:testing-dags` |
| **Check DAG run status** | status of run X, how did run X go | `get_dag_run(dag_id, dag_run_id)` | Specific run details |
| **Debug failure** | why did dag fail, what went wrong, debug dag | `diagnose_dag_run(dag_id, dag_run_id)` | Or delegate to `/data:debugging-dags` |
| **Get task logs** | show logs for task X, task output, task errors | `get_task_logs(dag_id, dag_run_id, task_id)` | Task execution logs |
| **List connections** | what connections, show connections | `list_connections` | External system connections |
| **List variables** | what variables, show variables | `list_variables` | Airflow variables |
| **Get variable** | value of variable X, what is variable X | `get_variable(variable_key)` | Single variable value |
| **List pools** | what pools, show pools, pool capacity | `list_pools` | Resource pools |
| **Get pool details** | pool X details, pool X status | `get_pool(pool_name)` | Single pool info |
| **System health** | any errors, any problems, system status | `get_system_health` | Overall health check |
| **DAG statistics** | success rate, failure count, run stats | `get_dag_stats` | Run statistics |
| **Import errors** | parse errors, broken dags, import failures | `list_import_errors` | DAGs that failed to load |
| **DAG warnings** | warnings, issues, deprecations | `list_dag_warnings` | Configuration warnings |
| **List assets** | what datasets, data lineage, assets | `list_assets` | Data assets/datasets |
| **Airflow version** | what version, airflow version | `get_airflow_version` | Version info |
| **Airflow config** | configuration, settings, how configured | `get_airflow_config` | Full configuration |

---

## Workflow Examples

### Example 1: Simple List Request

**User**: "list all dags"

**Action**:
```
1. Identify intent: List all DAGs
2. Look up routing table: "list dags" → list_dags
3. Call list_dags MCP tool
4. Present results to user
```

**DO NOT**:
- Use `astro dev run dags list`
- Use bash to list files in dags folder
- Try to read DAG files directly

---

### Example 2: DAG Status Check

**User**: "what's the status of my pipeline?"

**Action**:
```
1. Identify intent: Check DAG/pipeline status
2. If specific DAG mentioned: call get_dag_details(dag_id)
3. If no specific DAG: call list_dags to show all with their states
4. Present results
```

---

### Example 3: Testing (Simple)

**User**: "test dag_name"

**Action**:
```
1. Identify intent: Test/run a DAG
2. Simple test → call trigger_dag_and_wait(dag_id="dag_name") directly
3. Report results
```

---

### Example 4: Testing (Complex)

**User**: "test this dag and if it fails, debug and fix it"

**Action**:
```
1. Identify intent: Complex test → debug → fix workflow
2. This is multi-step → delegate to specialized skill
3. Invoke /data:testing-dags skill with user request
4. Let specialized skill handle the full cycle
```

---

### Example 5: Debugging

**User**: "my dag failed, why?"

**Action**:
```
1. Identify intent: Debug failure
2. If dag_id and dag_run_id known: call diagnose_dag_run directly
3. If not specific: call get_system_health to find recent failures
4. Follow up with get_task_logs for error details
5. For complex root cause analysis, delegate to /data:debugging-dags
```

---

### Example 6: Connection Check

**User**: "what connections are configured?"

**Action**:
```
1. Identify intent: List connections
2. Look up routing table: "connections" → list_connections
3. Call list_connections MCP tool
4. Present results (passwords will be hidden for security)
```

---

## Decision Tree: Direct vs Delegate

### Handle Directly if:
- ✅ Single MCP tool call needed
- ✅ Request is straightforward (list, show, get)
- ✅ No complex logic or multi-step procedures

### Delegate to Specialized Skill if:
- ✅ Multi-step workflow (test → wait → debug → fix)
- ✅ Complex decision trees
- ✅ Requires iterative refinement
- ✅ User asks for comprehensive analysis

**When in doubt**: Try handling directly first. If it becomes complex, acknowledge and delegate.

---

## Common Mistakes

**Don't use bash commands:**
- `astro dev run`, `airflow` CLI → Use MCP tools instead
- `docker ps` to check Airflow → MCP server already connected
- `cat dags/*.py` → Use `get_dag_source(dag_id)` MCP tool
- Piping MCP output to jq/grep → MCP returns structured JSON directly

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│  AIRFLOW OPERATIONS - QUICK REFERENCE                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  List DAGs            → list_dags                       │
│  Run DAG              → trigger_dag_and_wait            │
│  Check Status         → get_dag_details                 │
│  Debug Failure        → diagnose_dag_run                │
│  View Logs            → get_task_logs                   │
│  Check Health         → get_system_health               │
│  List Connections     → list_connections                │
│  List Variables       → list_variables                  │
│                                                          │
│  Complex Test         → /data:testing-dags              │
│  Complex Debug        → /data:debugging-dags            │
│  Create/Edit DAG      → /data:authoring-dags            │
│                                                          │
├─────────────────────────────────────────────────────────┤
│  ❌ NEVER USE: astro, airflow CLI, bash for Airflow    │
│  ✅ ALWAYS USE: Airflow MCP tools                       │
└─────────────────────────────────────────────────────────┘
```

---

## Related Skills

- **testing-dags**: Complex DAG testing workflows (trigger → wait → debug → fix cycle)
- **debugging-dags**: Comprehensive failure diagnosis and root cause analysis
- **authoring-dags**: Creating and editing DAG files with best practices
- **managing-astro-local-env**: Starting/stopping local Airflow environment (astro dev start/stop)

---

## Notes

- This skill is the **primary entrypoint** for all Airflow operations
- It establishes "Airflow context" where MCP tools are the default
- For simple requests, handle directly
- For complex workflows, delegate to specialized skills
- **Never fall back to bash commands** - if MCP tools can't do it, ask the user for clarification
