"""MCP prompts - guided workflows for common tasks."""

from astro_airflow_mcp.server import mcp


@mcp.prompt()
def troubleshoot_failed_dag(dag_id: str) -> str:
    """Step-by-step guide to troubleshoot a failed DAG.

    Args:
        dag_id: The DAG ID to troubleshoot
    """
    return f"""You are helping troubleshoot failures for DAG '{dag_id}'. Follow these steps:

1. First, use `explore_dag` to understand the DAG structure and check for any import errors.

2. Use `list_dag_runs` (filter by dag_id if possible) to find recent failed runs.

3. For each failed run, use `diagnose_dag_run` to get detailed information about:
   - Which tasks failed
   - The state of upstream tasks
   - Start/end times to understand duration

4. Based on the failed tasks, investigate:
   - Check task logs if available
   - Look at task dependencies (upstream_task_ids)
   - Check if any pools are at capacity using `list_pools`

5. Check system-wide issues using `get_system_health` to see if there are
   import errors or warnings that might be related.

6. Summarize your findings and provide recommendations for fixing the issues.

Start by running `explore_dag("{dag_id}")` to understand the DAG.
"""


@mcp.prompt()
def daily_health_check() -> str:
    """Morning health check workflow for Airflow."""
    return """You are performing a daily health check on the Airflow system. Follow these steps:

1. Start with `get_system_health` to get an overview of:
   - Import errors (broken DAG files)
   - DAG warnings
   - Overall system status

2. If there are import errors, prioritize investigating those first as they prevent DAGs from running.

3. Use `list_dag_runs` to see recent DAG run activity and identify any failures.

4. Check resource utilization with `list_pools` to see if any pools are at capacity.

5. Review `list_connections` to ensure all expected connections are configured.

6. Summarize the health status with:
   - Number of healthy vs problematic DAGs
   - Any blocking issues
   - Recommended actions

Start by running `get_system_health()` to assess the overall system state.
"""


@mcp.prompt()
def onboard_new_dag(dag_id: str) -> str:
    """Guide to understanding a new DAG.

    Args:
        dag_id: The DAG ID to learn about
    """
    return f"""You are helping someone understand the DAG '{dag_id}'. Provide a thorough overview:

1. Use `explore_dag` to get comprehensive DAG information including:
   - Schedule and timing
   - Owner and tags
   - All tasks and their relationships
   - Source code

2. Explain the DAG's purpose based on its description and task structure.

3. Walk through the task dependencies - what runs first, what runs in parallel,
   what are the critical path tasks.

4. Identify any external dependencies:
   - Check what connections the DAG might use with `list_connections`
   - Check for any assets/datasets it produces or consumes with `list_assets`

5. Show recent execution history with `list_dag_runs` filtered to this DAG.

6. Highlight any potential issues:
   - Is the DAG paused?
   - Are there any warnings?
   - What's the recent success/failure rate?

Start by running `explore_dag("{dag_id}")` to get the full picture.
"""
