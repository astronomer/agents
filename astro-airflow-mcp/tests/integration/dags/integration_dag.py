"""Simple test DAG that completes quickly for integration testing."""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

# This DAG is NOT paused by default and runs a simple task
with DAG(
    dag_id="integration_test_dag",
    start_date=datetime(2024, 1, 1),
    schedule=None,  # Only triggered manually
    catchup=False,
    is_paused_upon_creation=False,  # Important: start unpaused
    tags=["test"],
) as dag:
    task = BashOperator(
        task_id="quick_task",
        bash_command="echo 'Integration test task completed!'",
    )
