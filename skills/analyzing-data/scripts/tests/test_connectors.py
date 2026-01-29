"""Tests for database connectors."""

import tempfile
from pathlib import Path

import pytest

from lib.connectors import (
    BigQueryConnector,
    PostgresConnector,
    SnowflakeConnector,
    SQLAlchemyConnector,
    create_connector,
    get_connector_class,
    list_connector_types,
)


class TestRegistry:
    def test_list_connector_types(self):
        types = list_connector_types()
        assert "snowflake" in types
        assert "postgres" in types
        assert "bigquery" in types
        assert "sqlalchemy" in types

    def test_get_connector_class(self):
        assert get_connector_class("snowflake") == SnowflakeConnector
        assert get_connector_class("postgres") == PostgresConnector
        assert get_connector_class("bigquery") == BigQueryConnector
        assert get_connector_class("sqlalchemy") == SQLAlchemyConnector

    def test_get_connector_class_unknown(self):
        with pytest.raises(ValueError, match="Unknown connector type"):
            get_connector_class("unknown")

    def test_create_connector_default_type(self):
        # Default type is snowflake
        conn = create_connector({"account": "test", "user": "u", "password": "p"})
        assert isinstance(conn, SnowflakeConnector)

    def test_create_connector_explicit_type(self):
        conn = create_connector(
            {"type": "postgres", "host": "h", "user": "u", "database": "d"}
        )
        assert isinstance(conn, PostgresConnector)


class TestSnowflakeConnector:
    def test_connector_type(self):
        assert SnowflakeConnector.connector_type() == "snowflake"

    def test_from_dict_password_auth(self):
        data = {
            "type": "snowflake",
            "account": "my-account",
            "user": "my-user",
            "password": "my-password",
            "warehouse": "COMPUTE_WH",
            "databases": ["DB1"],
        }
        conn = SnowflakeConnector.from_dict(data)
        assert conn.account == "my-account"
        assert conn.user == "my-user"
        assert conn.password == "my-password"
        assert conn.warehouse == "COMPUTE_WH"
        assert conn.databases == ["DB1"]
        assert conn.auth_type == "password"

    def test_validate_missing_account(self):
        conn = SnowflakeConnector(account="", user="u", password="p", databases=[])
        with pytest.raises(ValueError, match="account required"):
            conn.validate("test")

    def test_validate_missing_password(self):
        conn = SnowflakeConnector(account="a", user="u", password="", databases=[])
        with pytest.raises(ValueError, match="password required"):
            conn.validate("test")

    def test_validate_private_key_auth(self):
        conn = SnowflakeConnector(
            account="a",
            user="u",
            auth_type="private_key",
            private_key="key",
            databases=[],
        )
        conn.validate("test")  # Should pass

    def test_get_required_packages_password(self):
        conn = SnowflakeConnector(account="a", user="u", password="p", databases=[])
        assert conn.get_required_packages() == ["snowflake-connector-python[pandas]"]

    def test_get_required_packages_private_key(self):
        conn = SnowflakeConnector(
            account="a",
            user="u",
            auth_type="private_key",
            private_key="k",
            databases=[],
        )
        pkgs = conn.get_required_packages()
        assert "cryptography" in pkgs

    def test_to_python_prelude_contains_connection(self):
        conn = SnowflakeConnector(
            account="test-account",
            user="test-user",
            password="test-pass",
            warehouse="WH",
            databases=["DB"],
        )
        prelude = conn.to_python_prelude()
        assert "import snowflake.connector" in prelude
        assert "snowflake.connector.connect" in prelude
        assert "account='test-account'" in prelude
        assert "def run_sql" in prelude


class TestPostgresConnector:
    def test_connector_type(self):
        assert PostgresConnector.connector_type() == "postgres"

    def test_from_dict(self):
        data = {
            "type": "postgres",
            "host": "db.example.com",
            "port": 5432,
            "user": "analyst",
            "password": "secret",
            "database": "analytics",
            "sslmode": "require",
        }
        conn = PostgresConnector.from_dict(data)
        assert conn.host == "db.example.com"
        assert conn.port == 5432
        assert conn.user == "analyst"
        assert conn.database == "analytics"
        assert conn.sslmode == "require"
        assert conn.databases == ["analytics"]

    def test_validate_missing_host(self):
        conn = PostgresConnector(host="", user="u", database="d", databases=[])
        with pytest.raises(ValueError, match="host required"):
            conn.validate("test")

    def test_validate_missing_database(self):
        conn = PostgresConnector(host="h", user="u", database="", databases=[])
        with pytest.raises(ValueError, match="database required"):
            conn.validate("test")

    def test_get_required_packages(self):
        conn = PostgresConnector(host="h", user="u", database="d", databases=[])
        assert conn.get_required_packages() == ["psycopg[binary,pool]"]

    def test_to_python_prelude_contains_connection(self):
        conn = PostgresConnector(
            host="localhost",
            port=5432,
            user="user",
            database="mydb",
            databases=["mydb"],
        )
        prelude = conn.to_python_prelude()
        assert "import psycopg" in prelude
        assert "psycopg.connect" in prelude
        assert "host='localhost'" in prelude
        assert "def run_sql" in prelude


class TestBigQueryConnector:
    def test_connector_type(self):
        assert BigQueryConnector.connector_type() == "bigquery"

    def test_from_dict(self):
        data = {
            "type": "bigquery",
            "project": "my-gcp-project",
            "location": "US",
        }
        conn = BigQueryConnector.from_dict(data)
        assert conn.project == "my-gcp-project"
        assert conn.location == "US"
        assert conn.databases == ["my-gcp-project"]

    def test_validate_missing_project(self):
        conn = BigQueryConnector(project="", databases=[])
        with pytest.raises(ValueError, match="project required"):
            conn.validate("test")

    def test_get_required_packages(self):
        conn = BigQueryConnector(project="p", databases=[])
        pkgs = conn.get_required_packages()
        assert "google-cloud-bigquery[pandas,pyarrow]" in pkgs
        assert "db-dtypes" in pkgs

    def test_to_python_prelude_contains_client(self):
        conn = BigQueryConnector(project="my-project", databases=["my-project"])
        prelude = conn.to_python_prelude()
        assert "from google.cloud import bigquery" in prelude
        assert "bigquery.Client" in prelude
        assert "def run_sql" in prelude

    def test_to_python_prelude_with_credentials(self):
        conn = BigQueryConnector(
            project="my-project",
            credentials_path="/path/to/creds.json",
            databases=["my-project"],
        )
        prelude = conn.to_python_prelude()
        assert "service_account" in prelude
        assert "from_service_account_file" in prelude


class TestSQLAlchemyConnector:
    def test_connector_type(self):
        assert SQLAlchemyConnector.connector_type() == "sqlalchemy"

    def test_from_dict(self):
        data = {
            "type": "sqlalchemy",
            "url": "sqlite:///test.db",
            "databases": ["test"],
        }
        conn = SQLAlchemyConnector.from_dict(data)
        assert conn.url == "sqlite:///test.db"
        assert conn.databases == ["test"]

    def test_validate_missing_url(self):
        conn = SQLAlchemyConnector(url="", databases=["d"])
        with pytest.raises(ValueError, match="url required"):
            conn.validate("test")

    def test_validate_missing_databases(self):
        conn = SQLAlchemyConnector(url="sqlite:///t.db", databases=[])
        with pytest.raises(ValueError, match="databases list required"):
            conn.validate("test")

    def test_get_required_packages_sqlite(self):
        conn = SQLAlchemyConnector(url="sqlite:///t.db", databases=["t"])
        pkgs = conn.get_required_packages()
        assert "sqlalchemy" in pkgs
        assert len(pkgs) == 1  # sqlite is built-in

    def test_get_required_packages_postgres(self):
        conn = SQLAlchemyConnector(url="postgresql://u:p@h/d", databases=["d"])
        pkgs = conn.get_required_packages()
        assert "sqlalchemy" in pkgs
        assert "psycopg[binary]" in pkgs

    def test_get_required_packages_mysql(self):
        conn = SQLAlchemyConnector(url="mysql+pymysql://u:p@h/d", databases=["d"])
        pkgs = conn.get_required_packages()
        assert "sqlalchemy" in pkgs
        assert "pymysql" in pkgs

    def test_get_required_packages_duckdb(self):
        conn = SQLAlchemyConnector(url="duckdb:///data.duckdb", databases=["main"])
        pkgs = conn.get_required_packages()
        assert "duckdb" in pkgs
        assert "duckdb-engine" in pkgs

    def test_to_python_prelude_contains_engine(self):
        conn = SQLAlchemyConnector(url="sqlite:///test.db", databases=["test"])
        prelude = conn.to_python_prelude()
        assert "from sqlalchemy import create_engine" in prelude
        assert "create_engine" in prelude
        assert "def run_sql" in prelude


class TestEnvVarSubstitution:
    def test_env_var_substitution(self, monkeypatch):
        monkeypatch.setenv("TEST_PASSWORD", "secret123")
        data = {
            "type": "postgres",
            "host": "localhost",
            "user": "user",
            "password": "${TEST_PASSWORD}",
            "database": "db",
        }
        conn = PostgresConnector.from_dict(data)
        assert conn.password == "secret123"
        assert conn.password_env_var == "TEST_PASSWORD"

    def test_env_var_injected_to_kernel(self, monkeypatch):
        monkeypatch.setenv("TEST_PW", "secret")
        data = {
            "type": "postgres",
            "host": "h",
            "user": "u",
            "password": "${TEST_PW}",
            "database": "d",
        }
        conn = PostgresConnector.from_dict(data)
        env_vars = conn.get_env_vars_for_kernel()
        assert env_vars.get("TEST_PW") == "secret"


class TestPreludeCompilation:
    """Test that generated prelude code compiles without syntax errors."""

    def test_snowflake_prelude_compiles(self):
        conn = SnowflakeConnector(
            account="test", user="u", password="p", warehouse="WH", databases=["DB"]
        )
        prelude = conn.to_python_prelude()
        compile(prelude, "<string>", "exec")

    def test_postgres_prelude_compiles(self):
        conn = PostgresConnector(
            host="localhost", port=5432, user="u", database="db", databases=["db"]
        )
        prelude = conn.to_python_prelude()
        compile(prelude, "<string>", "exec")

    def test_bigquery_prelude_compiles(self):
        conn = BigQueryConnector(project="my-project", databases=["my-project"])
        prelude = conn.to_python_prelude()
        compile(prelude, "<string>", "exec")

    def test_bigquery_prelude_with_location_compiles(self):
        conn = BigQueryConnector(
            project="my-project", location="US", databases=["my-project"]
        )
        prelude = conn.to_python_prelude()
        compile(prelude, "<string>", "exec")

    def test_sqlalchemy_prelude_compiles(self):
        conn = SQLAlchemyConnector(url="sqlite:///test.db", databases=["test"])
        prelude = conn.to_python_prelude()
        compile(prelude, "<string>", "exec")


class TestSQLiteEndToEnd:
    """Integration test using SQLite to verify generated code works."""

    def test_sqlite_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            conn = SQLAlchemyConnector(
                url=f"sqlite:///{db_path}",
                databases=["test"],
            )
            conn.validate("test")

            prelude = conn.to_python_prelude()

            # Execute the prelude and test helpers
            local_vars: dict = {}
            exec(prelude, local_vars)

            # Create test table and data
            local_vars["_conn"].execute(
                local_vars["text"](
                    "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
                )
            )
            local_vars["_conn"].execute(
                local_vars["text"]("INSERT INTO users (name) VALUES ('Alice'), ('Bob')")
            )
            local_vars["_conn"].commit()

            # Test run_sql returns Polars
            result = local_vars["run_sql"]("SELECT * FROM users")
            assert len(result) == 2
            assert "polars" in str(type(result)).lower()

            # Test run_sql_pandas returns Pandas
            result_pd = local_vars["run_sql_pandas"]("SELECT * FROM users")
            assert len(result_pd) == 2
            assert "dataframe" in str(type(result_pd)).lower()
