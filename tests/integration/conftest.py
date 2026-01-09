"""Pytest fixtures for integration tests."""

import os
import time

import pytest

from astro_airflow_mcp.adapters import create_adapter

# Skip integration tests if AIRFLOW_URL is not set
pytestmark = pytest.mark.skipif(
    os.getenv("AIRFLOW_URL") is None,
    reason="Integration tests require AIRFLOW_URL environment variable",
)

# Test DAG that's mounted via docker-compose (fast, unpaused)
TEST_DAG_ID = "integration_test_dag"


@pytest.fixture
def airflow_url() -> str:
    """Get Airflow URL from environment."""
    return os.getenv("AIRFLOW_URL", "http://localhost:8080")


@pytest.fixture
def airflow_username() -> str:
    """Get Airflow username from environment."""
    return os.getenv("AIRFLOW_USERNAME", "admin")


@pytest.fixture
def airflow_password() -> str:
    """Get Airflow password from environment."""
    return os.getenv("AIRFLOW_PASSWORD", "admin")


@pytest.fixture
def airflow_version() -> str:
    """Get expected Airflow version from environment."""
    return os.getenv("AIRFLOW_VERSION", "")


@pytest.fixture
def airflow_api_path() -> str:
    """Get API path based on version."""
    return os.getenv("AIRFLOW_API_PATH", "/api/v1")


@pytest.fixture
def airflow_auth_method() -> str:
    """Get auth method (basic or oauth2)."""
    return os.getenv("AIRFLOW_AUTH_METHOD", "basic")


@pytest.fixture(scope="session")
def completed_dag_run():
    """Trigger test DAG and wait for completion (runs once per session).

    Returns tuple of (dag_id, dag_run_id) for use by task instance tests.
    """
    url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
    username = os.getenv("AIRFLOW_USERNAME", "admin")
    password = os.getenv("AIRFLOW_PASSWORD", "admin")

    adapter = create_adapter(url, basic_auth_getter=lambda: (username, password))

    # Check for existing completed run first
    existing = adapter.list_dag_runs(dag_id=TEST_DAG_ID, limit=5)
    for run in existing.get("dag_runs", []):
        if run.get("state") in ("success", "failed"):
            return TEST_DAG_ID, run["dag_run_id"]

    # Trigger and wait
    result = adapter.trigger_dag_run(dag_id=TEST_DAG_ID)
    dag_run_id = result["dag_run_id"]

    for _ in range(30):  # 60 second timeout
        run = adapter.get_dag_run(TEST_DAG_ID, dag_run_id)
        if run.get("state") in ("success", "failed"):
            return TEST_DAG_ID, dag_run_id
        time.sleep(2)

    pytest.skip("DAG run did not complete in time")
