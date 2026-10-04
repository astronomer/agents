"""Tests for warehouse configuration."""

import pytest

from connectors import PostgresConnector, SnowflakeConnector
from warehouse import WarehouseConfig


class TestWarehouseConfigLoad:
    """Tests for WarehouseConfig.load()."""

    def test_load_valid_single_connector(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("""
my_postgres:
  type: postgres
  host: localhost
  user: testuser
  password: testpass
  database: testdb
""")
        config = WarehouseConfig.load(config_file)
        assert "my_postgres" in config.connectors
        assert isinstance(config.connectors["my_postgres"], PostgresConnector)
        assert config.connectors["my_postgres"].host == "localhost"

    def test_load_valid_multiple_connectors(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("""
snowflake_prod:
  type: snowflake
  account: myaccount
  user: myuser
  password: mypass

postgres_analytics:
  type: postgres
  host: db.example.com
  user: analyst
  password: secret
  database: analytics
""")
        config = WarehouseConfig.load(config_file)
        assert len(config.connectors) == 2
        assert "snowflake_prod" in config.connectors
        assert "postgres_analytics" in config.connectors
        assert isinstance(config.connectors["snowflake_prod"], SnowflakeConnector)
        assert isinstance(config.connectors["postgres_analytics"], PostgresConnector)

    def test_load_file_not_found(self, tmp_path):
        config_file = tmp_path / "nonexistent.yml"
        with pytest.raises(FileNotFoundError, match="Config not found"):
            WarehouseConfig.load(config_file)

    def test_load_empty_yaml(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("")
        with pytest.raises(ValueError, match="No configs"):
            WarehouseConfig.load(config_file)

    def test_load_yaml_with_only_comments(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("# Just a comment\n# Another comment")
        with pytest.raises(ValueError, match="No configs"):
            WarehouseConfig.load(config_file)

    def test_load_validates_each_connector(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        # Missing required 'host' for postgres
        config_file.write_text("""
bad_postgres:
  type: postgres
  user: testuser
  password: testpass
  database: testdb
""")
        with pytest.raises(ValueError, match="host required"):
            WarehouseConfig.load(config_file)

    def test_load_unknown_connector_type(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("""
unknown:
  type: mongodb
  host: localhost
""")
        with pytest.raises(ValueError, match="Unknown connector type"):
            WarehouseConfig.load(config_file)

    def test_load_with_env_var_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_DB_PASSWORD", "secretpassword")
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("""
my_postgres:
  type: postgres
  host: localhost
  user: testuser
  password: ${TEST_DB_PASSWORD}
  database: testdb
""")
        config = WarehouseConfig.load(config_file)
        connector = config.connectors["my_postgres"]
        assert isinstance(connector, PostgresConnector)
        assert connector.password == "secretpassword"


class TestWarehouseConfigGetDefault:
    """Tests for WarehouseConfig.get_default()."""

    def test_get_default_returns_first(self, tmp_path):
        config_file = tmp_path / "warehouse.yml"
        config_file.write_text("""
first_connector:
  type: postgres
  host: first.example.com
  user: u
  password: p
  database: d

second_connector:
  type: postgres
  host: second.example.com
  user: u
  password: p
  database: d
""")
        config = WarehouseConfig.load(config_file)
        name, connector = config.get_default()
        assert name == "first_connector"
        assert isinstance(connector, PostgresConnector)
        assert connector.host == "first.example.com"

    def test_get_default_empty_raises(self):
        config = WarehouseConfig(connectors={})
        with pytest.raises(ValueError, match="No warehouse configs"):
            config.get_default()


class TestEnvFileLoading:
    """Which .env files _load_env_file reads, and which value wins."""

    KEY = "AGENTS_TEST_WAREHOUSE_PASSWORD"

    @pytest.fixture
    def dirs(self, tmp_path, monkeypatch):
        import config

        default = tmp_path / "default"
        default.mkdir()
        monkeypatch.setattr(config, "_NEW_CONFIG_DIR", default)
        monkeypatch.setattr(config, "_LEGACY_CONFIG_DIR", tmp_path / "no-legacy")
        work = tmp_path / "work"
        work.mkdir()
        monkeypatch.chdir(work)
        monkeypatch.delenv(self.KEY, raising=False)
        return default, tmp_path / "session"

    def _env(self, directory, value):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".env").write_text(f"{self.KEY}={value}\n")

    def _load(self):
        import os

        from warehouse import _load_env_file

        _load_env_file()
        return os.environ.get(self.KEY)

    def test_unset_reads_the_default_dir(self, dirs, monkeypatch):
        default, _ = dirs
        self._env(default, "from-default")
        assert self._load() == "from-default"
        monkeypatch.delenv(self.KEY)

    def test_override_env_wins_over_the_default_dir(self, dirs, monkeypatch):
        default, session = dirs
        self._env(default, "from-default")
        self._env(session, "from-session")
        monkeypatch.setenv("ASTRO_AGENTS_CONFIG_DIR", str(session))
        assert self._load() == "from-session"
        monkeypatch.delenv(self.KEY)

    def test_override_falls_back_to_the_default_dir(self, dirs, monkeypatch):
        default, session = dirs
        self._env(default, "from-default")
        monkeypatch.setenv("ASTRO_AGENTS_CONFIG_DIR", str(session))
        assert self._load() == "from-default"
        monkeypatch.delenv(self.KEY)

    def test_process_env_wins_over_both(self, dirs, monkeypatch):
        default, session = dirs
        self._env(default, "from-default")
        self._env(session, "from-session")
        monkeypatch.setenv("ASTRO_AGENTS_CONFIG_DIR", str(session))
        monkeypatch.setenv(self.KEY, "from-process")
        assert self._load() == "from-process"
