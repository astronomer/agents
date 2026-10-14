"""End-to-end tests for SQLite via SQLAlchemy connector."""

from connectors import SQLAlchemyConnector


class TestSQLiteEndToEnd:
    """Integration tests for SQLite via SQLAlchemy connector."""

    def test_connection_and_query(self, sqlite_path):
        """Test full flow: connect, create table, insert, query."""
        conn = SQLAlchemyConnector(
            url=f"sqlite:///{sqlite_path}",
            databases=["main"],
        )
        conn.validate("test")

        # SQLite doesn't need extra packages
        pkgs = conn.get_required_packages()
        assert pkgs == ["sqlalchemy"]

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
                name TEXT,
                value REAL
            )
        """)
        run_sql("""
            INSERT INTO integration_test (name, value)
            VALUES ('alice', 10.50), ('bob', 20.75), ('charlie', 30.00)
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
        assert float(result["total"][0]) == 61.25

        # Test limit parameter
        result = run_sql("SELECT * FROM integration_test", limit=2)
        assert len(result) == 2

        # Test empty result
        result = run_sql("SELECT * FROM integration_test WHERE id = -1")
        assert len(result) == 0

    def test_failed_query_does_not_poison_later_ones(self, sqlite_path):
        """Each query gets its own transaction, so an error is not sticky."""
        conn = SQLAlchemyConnector(
            url=f"sqlite:///{sqlite_path}",
            databases=["main"],
        )
        local_vars: dict = {}
        exec(conn.to_python_prelude(), local_vars)
        run_sql = local_vars["run_sql"]

        run_sql("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        run_sql("INSERT INTO t (id) VALUES (1)")

        try:
            run_sql("SELECT * FROM table_that_does_not_exist")
        except Exception:  # noqa: BLE001 - any DB error is acceptable here
            pass

        assert int(run_sql("SELECT COUNT(*) AS c FROM t")["c"][0]) == 1

    def test_in_memory_database(self):
        """Test SQLite in-memory mode."""
        conn = SQLAlchemyConnector(
            url="sqlite:///:memory:",
            databases=["memory"],
        )
        conn.validate("test")

        prelude = conn.to_python_prelude()
        local_vars: dict = {}
        exec(prelude, local_vars)

        run_sql = local_vars["run_sql"]

        run_sql("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        run_sql("INSERT INTO test (name) VALUES ('a'), ('b'), ('c')")

        result = run_sql("SELECT COUNT(*) as cnt FROM test")
        assert int(result["cnt"][0]) == 3

    def test_data_types(self, sqlite_path):
        """Test various SQLite data types are handled correctly."""
        conn = SQLAlchemyConnector(
            url=f"sqlite:///{sqlite_path}",
            databases=["main"],
        )

        prelude = conn.to_python_prelude()
        local_vars: dict = {}
        exec(prelude, local_vars)

        run_sql = local_vars["run_sql"]

        run_sql("""
            CREATE TABLE types_test (
                int_col INTEGER,
                real_col REAL,
                text_col TEXT,
                blob_col BLOB
            )
        """)
        run_sql("""
            INSERT INTO types_test VALUES (42, 3.14, 'hello', X'DEADBEEF')
        """)

        result = run_sql("SELECT int_col, real_col, text_col FROM types_test")
        assert int(result["int_col"][0]) == 42
        assert float(result["real_col"][0]) == 3.14
        assert result["text_col"][0] == "hello"
