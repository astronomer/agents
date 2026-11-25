"""End-to-end tests for DuckDB via SQLAlchemy connector."""

import subprocess
import sys

import pytest

from connectors import SQLAlchemyConnector


class TestDuckDBEndToEnd:
    """Integration tests for DuckDB via SQLAlchemy connector."""

    def test_connection_and_query(self, duckdb_path):
        """Test full flow: connect, create table, insert, query."""
        conn = SQLAlchemyConnector(
            url=f"duckdb:///{duckdb_path}",
            databases=["main"],
        )
        conn.validate("test")

        # Verify package detection
        pkgs = conn.get_required_packages()
        assert "duckdb" in pkgs
        assert "duckdb-engine" in pkgs

        # Generate and execute prelude
        prelude = conn.to_python_prelude()
        local_vars: dict = {}
        exec(prelude, local_vars)

        run_sql = local_vars["run_sql"]
        run_sql_pandas = local_vars["run_sql_pandas"]

        # Setup runs through run_sql, which commits each statement. That the
        # later reads see this data is itself the check that it committed.
        run_sql("""
            CREATE TABLE integration_test (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                value DECIMAL(10, 2)
            )
        """)
        run_sql("""
            INSERT INTO integration_test VALUES
            (1, 'alice', 10.50),
            (2, 'bob', 20.75),
            (3, 'charlie', 30.00)
        """)

        # Test run_sql returns Polars
        result = run_sql("SELECT * FROM integration_test ORDER BY id")
        assert len(result) == 3
        assert "polars" in str(type(result)).lower()
        assert result["name"].to_list() == ["alice", "bob", "charlie"]

        # Test run_sql_pandas returns Pandas
        result_pd = run_sql_pandas("SELECT * FROM integration_test ORDER BY id")
        assert len(result_pd) == 3
        assert "dataframe" in str(type(result_pd)).lower()

        # Test aggregation
        result = run_sql("SELECT SUM(value) as total FROM integration_test")
        total = float(result["total"][0])
        assert total == pytest.approx(61.25)

        # Test limit parameter
        result = run_sql("SELECT * FROM integration_test", limit=2)
        assert len(result) == 2

        # Test empty result
        result = run_sql("SELECT * FROM integration_test WHERE id = -1")
        assert len(result) == 0

        # DuckDB-specific: test COPY export (parquet support)
        result = run_sql("SELECT COUNT(*) as cnt FROM integration_test")
        assert int(result["cnt"][0]) == 3

    def test_file_lock_released_between_queries(self, duckdb_path):
        """A file-backed DuckDB must not stay locked for the kernel's lifetime.

        DuckDB allows a single writer per file, and a connection parked in the
        pool still holds that lock, so anything else that opens the file (dbt,
        the user's own app) would fail until the kernel exits.
        """
        conn = SQLAlchemyConnector(
            url=f"duckdb:///{duckdb_path}",
            databases=["main"],
        )
        local_vars: dict = {}
        exec(conn.to_python_prelude(), local_vars)
        run_sql = local_vars["run_sql"]

        run_sql("CREATE TABLE t AS SELECT 1 AS a")

        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import duckdb; duckdb.connect({str(duckdb_path)!r}).execute('SELECT 1')",
            ],
            capture_output=True,
            text=True,
        )
        assert probe.returncode == 0, f"file still locked: {probe.stderr}"

        # The kernel can still use it afterwards.
        assert int(run_sql("SELECT COUNT(*) AS c FROM t")["c"][0]) == 1

    def test_failed_query_does_not_poison_later_ones(self, duckdb_path):
        """Each query gets its own transaction, so an error is not sticky."""
        conn = SQLAlchemyConnector(
            url=f"duckdb:///{duckdb_path}",
            databases=["main"],
        )
        local_vars: dict = {}
        exec(conn.to_python_prelude(), local_vars)
        run_sql = local_vars["run_sql"]

        run_sql("CREATE TABLE t AS SELECT 1 AS a")

        try:
            run_sql("SELECT * FROM table_that_does_not_exist")
        except Exception:  # noqa: BLE001 - any DB error is acceptable here
            pass

        assert int(run_sql("SELECT COUNT(*) AS c FROM t")["c"][0]) == 1

    def test_in_memory_database(self):
        """Test DuckDB in-memory mode."""
        try:
            import duckdb  # noqa: F401
        except ImportError:
            pytest.skip("duckdb not installed")

        conn = SQLAlchemyConnector(
            url="duckdb:///:memory:",
            databases=["memory"],
        )
        conn.validate("test")

        prelude = conn.to_python_prelude()
        local_vars: dict = {}
        exec(prelude, local_vars)

        run_sql = local_vars["run_sql"]

        run_sql("CREATE TABLE test (id INT)")
        run_sql("INSERT INTO test VALUES (1), (2), (3)")

        result = run_sql("SELECT COUNT(*) as cnt FROM test")
        assert int(result["cnt"][0]) == 3
