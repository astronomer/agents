"""Tests for af CLI config module."""

import os
from unittest.mock import patch

import pytest
import yaml

from astro_airflow_mcp.config import (
    AirflowCliConfig,
    Auth,
    ConfigError,
    ConfigManager,
    Instance,
    ResolvedConfig,
)
from astro_airflow_mcp.config.interpolation import interpolate_config_value, interpolate_env_vars


class TestAuth:
    """Tests for Auth model."""

    def test_auth_with_basic(self):
        """Test auth with username/password."""
        auth = Auth(username="admin", password="admin123")
        assert auth.username == "admin"
        assert auth.password == "admin123"
        assert auth.token is None

    def test_auth_with_token(self):
        """Test auth with token."""
        auth = Auth(token="my-token")
        assert auth.token == "my-token"
        assert auth.username is None
        assert auth.password is None

    def test_auth_requires_method(self):
        """Test that auth must have some method configured."""
        with pytest.raises(ValueError, match="must have either username/password or token"):
            Auth()

    def test_auth_cannot_have_both(self):
        """Test that auth cannot have both basic and token."""
        with pytest.raises(ValueError, match="cannot have both"):
            Auth(username="user", password="pass", token="token")

    def test_auth_partial_basic_invalid(self):
        """Test that partial basic auth is invalid."""
        with pytest.raises(ValueError, match="must have either"):
            Auth(username="user")  # no password

        with pytest.raises(ValueError, match="must have either"):
            Auth(password="pass")  # no username


class TestInstance:
    """Tests for Instance model."""

    def test_valid_instance(self):
        """Test creating a valid instance."""
        instance = Instance(
            name="local",
            url="http://localhost:8080",
            auth=Auth(username="admin", password="admin"),
        )
        assert instance.name == "local"
        assert instance.url == "http://localhost:8080"
        assert instance.auth.username == "admin"

    def test_instance_with_token_auth(self):
        """Test instance with token auth preserves interpolation syntax."""
        instance = Instance(
            name="staging",
            url="https://staging.example.com",
            auth=Auth(token="${STAGING_TOKEN}"),
        )
        # Verify interpolation syntax is stored as-is, not resolved at creation time
        # Interpolation should only happen at resolve_instance() time
        assert instance.auth.token == "${STAGING_TOKEN}"
        assert "${" in instance.auth.token, "Interpolation syntax should be preserved"

    def test_instance_forbids_extra_fields(self):
        """Test that extra fields are rejected."""
        with pytest.raises(ValueError):
            Instance(
                name="local",
                url="http://localhost:8080",
                auth=Auth(username="admin", password="admin"),
                extra="field",
            )


class TestAirflowCliConfig:
    """Tests for AirflowCliConfig model."""

    def test_empty_config(self):
        """Test empty config is valid."""
        config = AirflowCliConfig()
        assert config.instances == []
        assert config.current_instance is None

    def test_valid_config(self):
        """Test a valid config."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ],
            current_instance="local",
        )
        assert len(config.instances) == 1
        assert config.current_instance == "local"

    def test_current_instance_must_exist(self):
        """Test that current-instance must reference existing instance."""
        with pytest.raises(ValueError, match="does not exist"):
            AirflowCliConfig(
                instances=[],
                current_instance="nonexistent",
            )

    def test_get_instance(self):
        """Test get_instance helper."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                ),
                Instance(
                    name="staging",
                    url="https://staging.example.com",
                    auth=Auth(token="token"),
                ),
            ]
        )
        assert config.get_instance("local").url == "http://localhost:8080"
        assert config.get_instance("staging").url == "https://staging.example.com"
        assert config.get_instance("nonexistent") is None

    def test_add_instance_creates_new(self):
        """Test add_instance creates new instance."""
        config = AirflowCliConfig()
        config.add_instance("local", "http://localhost:8080", username="admin", password="admin")
        assert len(config.instances) == 1
        assert config.get_instance("local").url == "http://localhost:8080"
        assert config.get_instance("local").auth.username == "admin"

    def test_add_instance_updates_existing(self):
        """Test add_instance updates existing instance."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ]
        )
        config.add_instance("local", "http://localhost:9090", token="new-token")
        assert len(config.instances) == 1
        assert config.get_instance("local").url == "http://localhost:9090"
        assert config.get_instance("local").auth.token == "new-token"
        assert config.get_instance("local").auth.username is None

    def test_delete_instance(self):
        """Test delete_instance."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ]
        )
        config.delete_instance("local")
        assert len(config.instances) == 0

    def test_delete_instance_clears_current(self):
        """Test delete_instance clears current-instance if deleted."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ],
            current_instance="local",
        )
        config.delete_instance("local")
        assert config.current_instance is None

    def test_delete_instance_nonexistent_fails(self):
        """Test delete_instance fails for nonexistent instance."""
        config = AirflowCliConfig()
        with pytest.raises(ValueError, match="does not exist"):
            config.delete_instance("nonexistent")

    def test_use_instance(self):
        """Test use_instance."""
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ]
        )
        config.use_instance("local")
        assert config.current_instance == "local"

    def test_use_instance_nonexistent_fails(self):
        """Test use_instance fails for nonexistent instance."""
        config = AirflowCliConfig()
        with pytest.raises(ValueError, match="does not exist"):
            config.use_instance("nonexistent")


class TestInterpolation:
    """Tests for environment variable interpolation."""

    def test_interpolate_simple_var(self):
        """Test simple env var interpolation."""
        with patch.dict(os.environ, {"MY_TOKEN": "secret123"}):
            result = interpolate_env_vars("${MY_TOKEN}")
            assert result == "secret123"

    def test_interpolate_var_in_string(self):
        """Test env var in middle of string."""
        with patch.dict(os.environ, {"USER": "admin"}):
            result = interpolate_env_vars("hello ${USER} world")
            assert result == "hello admin world"

    def test_interpolate_multiple_vars(self):
        """Test multiple env vars."""
        with patch.dict(os.environ, {"HOST": "localhost", "PORT": "8080"}):
            result = interpolate_env_vars("http://${HOST}:${PORT}")
            assert result == "http://localhost:8080"

    def test_interpolate_missing_var_raises(self):
        """Test missing env var raises error."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MISSING_VAR", None)
            with pytest.raises(ValueError, match="not set"):
                interpolate_env_vars("${MISSING_VAR}")

    def test_interpolate_no_vars(self):
        """Test string without vars unchanged."""
        result = interpolate_env_vars("plain string")
        assert result == "plain string"

    def test_interpolate_config_value_none(self):
        """Test interpolate_config_value handles None."""
        result = interpolate_config_value(None)
        assert result is None

    def test_interpolate_config_value_with_var(self):
        """Test interpolate_config_value with env var."""
        with patch.dict(os.environ, {"TOKEN": "abc"}):
            result = interpolate_config_value("${TOKEN}")
            assert result == "abc"


class TestConfigManager:
    """Tests for ConfigManager."""

    def test_load_nonexistent_file(self, tmp_path):
        """Test loading creates default localhost:8080 config when file doesn't exist."""
        config_path = tmp_path / "nonexistent.yaml"
        manager = ConfigManager(config_path=config_path)
        config = manager.load()

        # Should create default localhost:8080 instance
        assert len(config.instances) == 1
        assert config.get_instance("localhost:8080") is not None
        assert config.get_instance("localhost:8080").url == "http://localhost:8080"
        assert config.current_instance == "localhost:8080"

        # Should save the config file
        assert config_path.exists()

    def test_save_and_load(self, tmp_path):
        """Test saving and loading config."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                )
            ],
            current_instance="local",
        )
        manager.save(config)

        loaded = manager.load()
        assert len(loaded.instances) == 1
        assert loaded.get_instance("local").url == "http://localhost:8080"
        assert loaded.current_instance == "local"

    def test_save_creates_directory(self, tmp_path):
        """Test save creates parent directories."""
        config_path = tmp_path / "nested" / "dir" / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig()
        manager.save(config)

        assert config_path.exists()

    def test_load_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML raises ConfigError."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("invalid: yaml: :")

        manager = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Invalid YAML"):
            manager.load()

    def test_load_invalid_config(self, tmp_path):
        """Test loading invalid config raises ConfigError."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "instances": [],
                    "current-instance": "nonexistent",
                }
            )
        )

        manager = ConfigManager(config_path=config_path)
        with pytest.raises(ConfigError, match="Invalid config"):
            manager.load()

    def test_resolve_instance(self, tmp_path):
        """Test resolving an instance."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="secret"),
                )
            ],
            current_instance="local",
        )
        manager.save(config)

        resolved = manager.resolve_instance()
        assert resolved.url == "http://localhost:8080"
        assert resolved.username == "admin"
        assert resolved.password == "secret"
        assert resolved.instance_name == "local"

    def test_resolve_instance_with_name(self, tmp_path):
        """Test resolving a specific instance by name."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(username="admin", password="admin"),
                ),
                Instance(
                    name="staging",
                    url="https://staging.example.com",
                    auth=Auth(token="staging-token"),
                ),
            ],
            current_instance="local",
        )
        manager.save(config)

        resolved = manager.resolve_instance("staging")
        assert resolved.url == "https://staging.example.com"
        assert resolved.token == "staging-token"
        assert resolved.instance_name == "staging"

    def test_resolve_instance_none_when_no_current(self, tmp_path):
        """Test resolve_instance returns None when no current instance."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)
        manager.save(AirflowCliConfig())

        resolved = manager.resolve_instance()
        assert resolved is None

    def test_resolve_instance_nonexistent_raises(self, tmp_path):
        """Test resolve_instance raises for nonexistent instance."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)
        manager.save(AirflowCliConfig())

        with pytest.raises(ConfigError, match="not found"):
            manager.resolve_instance("nonexistent")

    def test_resolve_instance_with_env_var(self, tmp_path):
        """Test resolve_instance interpolates env vars."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(token="${MY_TOKEN}"),
                )
            ],
            current_instance="local",
        )
        manager.save(config)

        with patch.dict(os.environ, {"MY_TOKEN": "real-token"}):
            resolved = manager.resolve_instance()
            assert resolved.token == "real-token"

    def test_resolve_instance_missing_env_var_raises(self, tmp_path):
        """Test resolve_instance raises for missing env var."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="local",
                    url="http://localhost:8080",
                    auth=Auth(token="${MISSING_TOKEN}"),
                )
            ],
            current_instance="local",
        )
        manager.save(config)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MISSING_TOKEN", None)
            with pytest.raises(ConfigError, match="Error resolving instance"):
                manager.resolve_instance()

    def test_crud_operations(self, tmp_path):
        """Test CRUD operations through ConfigManager."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        # Default localhost:8080 instance is created on first load
        config = manager.load()
        assert config.get_instance("localhost:8080") is not None
        assert config.current_instance == "localhost:8080"

        # Add another instance
        manager.add_instance("staging", "https://staging.example.com", token="token")

        # Verify
        config = manager.load()
        assert len(config.instances) == 2
        assert config.get_instance("staging").url == "https://staging.example.com"

        # Use instance
        manager.use_instance("staging")
        assert manager.get_current_instance() == "staging"

        # Delete instance
        manager.delete_instance("staging")
        config = manager.load()
        assert len(config.instances) == 1
        assert config.current_instance is None  # staging was current, now cleared

    def test_list_instances(self, tmp_path):
        """Test list_instances through ConfigManager."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        # Default localhost:8080 is created, add more instances
        manager.add_instance("staging", "https://staging.example.com", token="token")

        instances = manager.list_instances()
        assert len(instances) == 2  # localhost:8080 + staging
        assert manager.get_current_instance() == "localhost:8080"  # default is set

        manager.use_instance("staging")
        assert manager.get_current_instance() == "staging"


class TestResolvedConfig:
    """Tests for ResolvedConfig dataclass."""

    def test_resolved_config_basic(self):
        """Test ResolvedConfig with basic auth."""
        resolved = ResolvedConfig(
            url="http://localhost:8080",
            username="admin",
            password="secret",
            instance_name="local",
        )
        assert resolved.url == "http://localhost:8080"
        assert resolved.username == "admin"
        assert resolved.password == "secret"
        assert resolved.token is None

    def test_resolved_config_token(self):
        """Test ResolvedConfig with token auth."""
        resolved = ResolvedConfig(
            url="http://localhost:8080",
            token="my-token",
            instance_name="local",
        )
        assert resolved.token == "my-token"
        assert resolved.username is None

    def test_resolved_config_sources(self):
        """Test ResolvedConfig tracks sources."""
        resolved = ResolvedConfig(
            url="http://localhost:8080",
            username="admin",
            password="secret",
            instance_name="local",
            sources={
                "url": "instance:local",
                "auth": "instance:local",
            },
        )
        assert "instance:local" in resolved.sources["url"]

    def test_resolved_config_ssl_defaults(self):
        """Test ResolvedConfig has SSL defaults."""
        resolved = ResolvedConfig(url="http://localhost:8080")
        assert resolved.verify_ssl is True
        assert resolved.ca_cert is None

    def test_resolved_config_ssl_disabled(self):
        """Test ResolvedConfig with SSL verification disabled."""
        resolved = ResolvedConfig(
            url="https://self-signed.example.com",
            verify_ssl=False,
        )
        assert resolved.verify_ssl is False

    def test_resolved_config_ca_cert(self):
        """Test ResolvedConfig with custom CA cert."""
        resolved = ResolvedConfig(
            url="https://corporate.example.com",
            ca_cert="/etc/ssl/certs/corporate-ca.pem",
        )
        assert resolved.ca_cert == "/etc/ssl/certs/corporate-ca.pem"


class TestInstanceSSL:
    """Tests for Instance model SSL fields."""

    def test_instance_ssl_defaults(self):
        """Test Instance has SSL defaults."""
        instance = Instance(
            name="local",
            url="http://localhost:8080",
        )
        assert instance.verify_ssl is True
        assert instance.ca_cert is None

    def test_instance_verify_ssl_false(self):
        """Test Instance with SSL verification disabled."""
        instance = Instance(
            name="self-signed",
            url="https://self-signed.example.com",
            verify_ssl=False,
        )
        assert instance.verify_ssl is False

    def test_instance_ca_cert(self):
        """Test Instance with custom CA cert."""
        instance = Instance(
            name="corporate",
            url="https://corporate.example.com",
            ca_cert="/path/to/ca.pem",
        )
        assert instance.ca_cert == "/path/to/ca.pem"

    def test_instance_ssl_serialization(self):
        """Test Instance SSL fields serialize with aliases."""
        instance = Instance(
            name="test",
            url="https://example.com",
            verify_ssl=False,
            ca_cert="/path/to/ca.pem",
        )
        data = instance.model_dump(by_alias=True)
        assert data["verify-ssl"] is False
        assert data["ca-cert"] == "/path/to/ca.pem"

    def test_instance_ssl_from_alias(self):
        """Test Instance can be created from aliased field names (YAML loading)."""
        instance = Instance.model_validate(
            {
                "name": "test",
                "url": "https://example.com",
                "verify-ssl": False,
                "ca-cert": "/path/to/ca.pem",
            }
        )
        assert instance.verify_ssl is False
        assert instance.ca_cert == "/path/to/ca.pem"

    def test_add_instance_with_ssl(self):
        """Test add_instance stores SSL fields."""
        config = AirflowCliConfig()
        config.add_instance(
            "self-signed",
            "https://self-signed.example.com",
            username="admin",
            password="admin",
            verify_ssl=False,
        )
        instance = config.get_instance("self-signed")
        assert instance.verify_ssl is False
        assert instance.ca_cert is None

    def test_add_instance_with_ca_cert(self):
        """Test add_instance stores CA cert."""
        config = AirflowCliConfig()
        config.add_instance(
            "corporate",
            "https://corporate.example.com",
            token="token",
            ca_cert="/path/to/ca.pem",
        )
        instance = config.get_instance("corporate")
        assert instance.verify_ssl is True
        assert instance.ca_cert == "/path/to/ca.pem"


class TestConfigManagerSSL:
    """Tests for ConfigManager SSL field handling."""

    def test_resolve_instance_carries_ssl_fields(self, tmp_path):
        """Test resolve_instance passes SSL fields to ResolvedConfig."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="self-signed",
                    url="https://self-signed.example.com",
                    auth=Auth(username="admin", password="admin"),
                    verify_ssl=False,
                )
            ],
            current_instance="self-signed",
        )
        manager.save(config)

        resolved = manager.resolve_instance()
        assert resolved.verify_ssl is False
        assert resolved.ca_cert is None

    def test_resolve_instance_with_ca_cert(self, tmp_path):
        """Test resolve_instance interpolates and passes CA cert."""
        config_path = tmp_path / "config.yaml"
        ca_file = tmp_path / "corporate-ca.pem"
        ca_file.write_text("fake cert")

        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="corporate",
                    url="https://corporate.example.com",
                    auth=Auth(token="token"),
                    ca_cert=str(ca_file),
                )
            ],
            current_instance="corporate",
        )
        manager.save(config)

        resolved = manager.resolve_instance()
        assert resolved.ca_cert == str(ca_file)
        assert resolved.verify_ssl is True

    def test_resolve_instance_ca_cert_interpolation(self, tmp_path):
        """Test ca_cert supports env var interpolation."""
        config_path = tmp_path / "config.yaml"
        ca_file = tmp_path / "resolved-ca.pem"
        ca_file.write_text("fake cert")

        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="test",
                    url="https://example.com",
                    auth=Auth(token="token"),
                    ca_cert="${CA_CERT_PATH}",
                )
            ],
            current_instance="test",
        )
        manager.save(config)

        with patch.dict(os.environ, {"CA_CERT_PATH": str(ca_file)}):
            resolved = manager.resolve_instance()
            assert resolved.ca_cert == str(ca_file)

    def test_save_omits_default_ssl_values(self, tmp_path):
        """Test save omits default SSL values for clean YAML."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="default-ssl",
                    url="http://localhost:8080",
                )
            ],
        )
        manager.save(config)

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        inst = raw["instances"][0]
        assert "verify-ssl" not in inst
        assert "ca-cert" not in inst

    def test_save_persists_non_default_ssl(self, tmp_path):
        """Test save persists non-default SSL values."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="custom-ssl",
                    url="https://example.com",
                    verify_ssl=False,
                    ca_cert="/path/to/ca.pem",
                )
            ],
        )
        manager.save(config)

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        inst = raw["instances"][0]
        assert inst["verify-ssl"] is False
        assert inst["ca-cert"] == "/path/to/ca.pem"

    def test_add_instance_with_ssl_persists(self, tmp_path):
        """Test ConfigManager.add_instance persists SSL fields."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        manager.add_instance(
            "test",
            "https://example.com",
            token="tok",
            verify_ssl=False,
            ca_cert="/ca.pem",
        )

        config = manager.load()
        instance = config.get_instance("test")
        assert instance.verify_ssl is False
        assert instance.ca_cert == "/ca.pem"

    def test_resolve_instance_ca_cert_not_found_raises(self, tmp_path):
        """Test resolve_instance raises when ca_cert file doesn't exist."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path=config_path)

        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="test",
                    url="https://example.com",
                    auth=Auth(token="token"),
                    ca_cert="/nonexistent/ca.pem",
                )
            ],
            current_instance="test",
        )
        manager.save(config)

        with pytest.raises(ConfigError, match="CA certificate file not found"):
            manager.resolve_instance()

    def test_resolve_instance_ca_cert_valid_file(self, tmp_path):
        """Test resolve_instance succeeds when ca_cert file exists."""
        config_path = tmp_path / "config.yaml"
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text("fake cert")

        manager = ConfigManager(config_path=config_path)
        config = AirflowCliConfig(
            instances=[
                Instance(
                    name="test",
                    url="https://example.com",
                    auth=Auth(token="token"),
                    ca_cert=str(ca_file),
                )
            ],
            current_instance="test",
        )
        manager.save(config)

        resolved = manager.resolve_instance()
        assert resolved.ca_cert == str(ca_file)


class TestCLIContextSSL:
    """Tests for CLIContext SSL env var override logic."""

    def _make_context(self):
        """Create a fresh CLIContext (bypass singleton)."""
        from astro_airflow_mcp.cli.context import CLIContext

        ctx = CLIContext.__new__(CLIContext)
        ctx._manager = __import__(
            "astro_airflow_mcp.adapter_manager", fromlist=["AdapterManager"]
        ).AdapterManager()
        ctx._initialized = False
        return ctx

    def test_env_var_disables_ssl(self):
        """Test AIRFLOW_VERIFY_SSL=false disables SSL verification."""
        ctx = self._make_context()
        env = {
            "AIRFLOW_VERIFY_SSL": "false",
            "AIRFLOW_API_URL": "http://localhost:8080",
        }
        with patch.dict(os.environ, env, clear=False):
            ctx.init()
        assert ctx._manager._verify is False

    def test_env_var_true_overrides_config_false(self, tmp_path):
        """Test AIRFLOW_VERIFY_SSL=true overrides config verify_ssl=False."""
        ctx = self._make_context()
        env = {
            "AIRFLOW_VERIFY_SSL": "true",
            "AIRFLOW_API_URL": "http://localhost:8080",
        }
        # Mock _load_from_config to return verify_ssl=False
        mock_config = ResolvedConfig(
            url="http://localhost:8080",
            verify_ssl=False,
            instance_name="test",
        )
        with (
            patch.object(ctx, "_load_from_config", return_value=mock_config),
            patch.dict(os.environ, env, clear=False),
        ):
            ctx.init()
        assert ctx._manager._verify is True

    def test_env_ca_cert_overrides_config(self, tmp_path):
        """Test AIRFLOW_CA_CERT env var overrides config ca_cert."""
        ctx = self._make_context()
        env = {
            "AIRFLOW_CA_CERT": "/env/ca.pem",
            "AIRFLOW_API_URL": "http://localhost:8080",
        }
        mock_config = ResolvedConfig(
            url="http://localhost:8080",
            ca_cert="/config/ca.pem",
            instance_name="test",
        )
        with (
            patch.object(ctx, "_load_from_config", return_value=mock_config),
            patch.dict(os.environ, env, clear=False),
        ):
            ctx.init()
        assert ctx._manager._verify == "/env/ca.pem"

    def test_config_verify_ssl_false_no_env(self):
        """Test config verify_ssl=False is used when no env var set."""
        ctx = self._make_context()
        mock_config = ResolvedConfig(
            url="http://localhost:8080",
            verify_ssl=False,
            instance_name="test",
        )
        with patch.object(ctx, "_load_from_config", return_value=mock_config):
            # Ensure no SSL env vars are set
            env_clear = {
                k: v
                for k, v in os.environ.items()
                if k not in ("AIRFLOW_VERIFY_SSL", "AIRFLOW_CA_CERT")
            }
            with patch.dict(os.environ, env_clear, clear=True):
                ctx.init()
        assert ctx._manager._verify is False

    def test_config_ca_cert_used_no_env(self):
        """Test config ca_cert is used when no env var set."""
        ctx = self._make_context()
        mock_config = ResolvedConfig(
            url="http://localhost:8080",
            ca_cert="/config/ca.pem",
            instance_name="test",
        )
        with patch.object(ctx, "_load_from_config", return_value=mock_config):
            env_clear = {
                k: v
                for k, v in os.environ.items()
                if k not in ("AIRFLOW_VERIFY_SSL", "AIRFLOW_CA_CERT")
            }
            with patch.dict(os.environ, env_clear, clear=True):
                ctx.init()
        assert ctx._manager._verify == "/config/ca.pem"

    def test_default_verify_true(self):
        """Test default verify is True when no config or env vars."""
        ctx = self._make_context()
        with patch.object(ctx, "_load_from_config", return_value=None):
            env_clear = {
                k: v
                for k, v in os.environ.items()
                if k not in ("AIRFLOW_VERIFY_SSL", "AIRFLOW_CA_CERT")
            }
            with patch.dict(os.environ, env_clear, clear=True):
                ctx.init()
        assert ctx._manager._verify is True
