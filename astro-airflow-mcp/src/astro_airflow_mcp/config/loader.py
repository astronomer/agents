"""Configuration loading and management for af CLI."""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from filelock import FileLock

from astro_airflow_mcp.config.interpolation import interpolate_config_value
from astro_airflow_mcp.config.models import AirflowCliConfig

if TYPE_CHECKING:
    from astro_airflow_mcp.config.models import AuthKind, Instance


# Top-level YAML keys that af owns and rewrites wholesale. Anything else in
# the file is preserved untouched on round-trip so we can share the file
# with astro-cli (which writes keys like `project:`, `cloud:`, `contexts:`
# to the same file). ``telemetry`` is intentionally *not* in this set —
# it's shared with astro-cli (both tools write
# ``telemetry.enabled``/``anonymous_id``; astro-cli also writes
# ``telemetry.notice_shown``). save() merges sub-keys for telemetry
# instead of replacing the whole block.
_KNOWN_TOP_LEVEL_KEYS = frozenset({"instances", "current-instance"})


class ConfigError(Exception):
    """Error raised for configuration issues."""


@dataclass
class ResolvedConfig:
    """Resolved configuration ready for use."""

    url: str
    username: str | None = None
    password: str | None = None
    token: str | None = None
    auth_kind: AuthKind | None = None
    astro_context: str | None = None  # only set when auth_kind == "astro_pat"
    instance_name: str | None = None
    sources: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    ca_cert: str | None = None


_legacy_warning_emitted = False


def legacy_default_path() -> Path:
    """Path to the pre-existing global config (``~/.af/config.yaml``).

    af shipped with this path before adopting astro-cli's ``~/.astro/``
    home in 2026. Read-only fallback for one release; the ``af migrate``
    command provides explicit migration with backup.
    """
    return Path.home() / ".af" / "config.yaml"


def _emit_legacy_deprecation_once() -> None:
    """Emit a one-time stderr deprecation note when reading from ~/.af/."""
    global _legacy_warning_emitted
    if _legacy_warning_emitted:
        return
    _legacy_warning_emitted = True
    print(
        "Note: af is reading from the legacy ~/.af/config.yaml. The new "
        "global location is ~/.astro/config.yaml (shared with astro-cli). "
        "Run 'af migrate' to move your config; the old file will be kept "
        "as ~/.af/config.yaml.bak.",
        file=sys.stderr,
    )


class ConfigManager:
    """Manages af CLI configuration file."""

    CONFIG_ENV_VAR = "AF_CONFIG"

    def __init__(self, config_path: Path | None = None):
        """Initialize the config manager.

        Args:
            config_path: Optional custom path to config file.
                         Falls back to AF_CONFIG env var,
                         then ~/.astro/config.yaml (legacy ~/.af/config.yaml
                         is honored as a read-only fallback when the new
                         path has no af keys yet).
        """
        if config_path:
            self.config_path = config_path
            self._using_default_path = False
        elif os.environ.get(self.CONFIG_ENV_VAR):
            self.config_path = Path(os.environ[self.CONFIG_ENV_VAR])
            self._using_default_path = False
        else:
            # Resolve at __init__ time so tests can monkeypatch Path.home().
            self.config_path = Path.home() / ".astro" / "config.yaml"
            self._using_default_path = True
        self.lock_path = self.config_path.with_suffix(".lock")

        # AF_CONFIG=/dev/null (or any non-regular file: directory, fifo,
        # socket, device node) is sometimes used by wrappers as a
        # "neutralize global config" sentinel. We can't read, write, or
        # FileLock such a path — on macOS, opening /dev/null.lock with
        # O_CREAT raises EPERM. Treat it as "no config": load() returns
        # an empty config, save() is a no-op.
        self._null_path = self.config_path.exists() and not self.config_path.is_file()

    def _ensure_dir(self) -> None:
        """Ensure the config directory exists."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _create_default_config(self) -> AirflowCliConfig:
        """Create default config with localhost:8080 instance."""
        config = AirflowCliConfig.model_validate({})
        config.add_instance("localhost:8080", "http://localhost:8080", source="local")
        config.use_instance("localhost:8080")
        return config

    def load(self, create_default_if_missing: bool = True) -> AirflowCliConfig:
        """Load configuration from file.

        Args:
            create_default_if_missing: When True (default), a missing file
                triggers creation of a default config containing a
                localhost:8080 instance — appropriate for a brand-new
                user's global config. When False, a missing file simply
                yields an empty config and no file is written; this is
                the right behavior for project-scope files where "no
                file" means "no project config", not "set up defaults".

        Returns:
            AirflowCliConfig instance (default localhost if file doesn't
            exist and ``create_default_if_missing`` is True; empty config
            otherwise).

        Raises:
            ConfigError: If config file is invalid
        """
        if self._null_path:
            return AirflowCliConfig.model_validate({})

        # Read the configured path's raw dict (or empty if missing). We
        # check it before the legacy fallback so a freshly-installed
        # astro-cli that already wrote ``~/.astro/config.yaml`` (with
        # ``contexts:``, ``project:``, etc., but no ``instances:``) doesn't
        # block us from migrating someone's existing ``~/.af/config.yaml``.
        new_data: dict | None = None
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    new_data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ConfigError(f"Invalid YAML in config file: {e}") from e
            if new_data is not None and not isinstance(new_data, dict):
                raise ConfigError(
                    f"Invalid config: top-level YAML must be a mapping, got {type(new_data).__name__}"
                )

        # Legacy fallback: when using the default ~/.astro/config.yaml and
        # we haven't yet written our keys there, prefer the user's existing
        # ~/.af/config.yaml (read-only). The next save() will land in the
        # new path, effectively migrating on first write.
        new_has_af_keys = isinstance(new_data, dict) and "instances" in new_data
        if self._using_default_path and not new_has_af_keys and legacy_default_path().is_file():
            _emit_legacy_deprecation_once()
            return self._load_validated(legacy_default_path())

        if not self.config_path.exists():
            if create_default_if_missing:
                config = self._create_default_config()
                self.save(config)
                return config
            return AirflowCliConfig.model_validate({})

        with FileLock(self.lock_path):
            if new_data is None:
                return AirflowCliConfig.model_validate({})
            try:
                return AirflowCliConfig.model_validate(new_data)
            except ValueError as e:
                raise ConfigError(f"Invalid config: {e}") from e

    def _load_validated(self, path: Path) -> AirflowCliConfig:
        """Read+validate a YAML config file unconditionally (no fallback)."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data is None:
                return AirflowCliConfig.model_validate({})
            return AirflowCliConfig.model_validate(data)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e
        except ValueError as e:
            raise ConfigError(f"Invalid config in {path}: {e}") from e

    def save(self, config: AirflowCliConfig) -> None:
        """Save configuration to file.

        Reads the existing file (if any) and merges af-owned top-level keys
        from ``config`` over it, preserving any other top-level keys. This
        lets af coexist with astro-cli, which writes other keys (``project``,
        ``cloud``, ``contexts``, etc.) to the same file when we point at
        ``~/.astro/config.yaml`` or a project's ``.astro/config.yaml``.

        Args:
            config: Configuration to save
        """
        if self._null_path:
            return

        self._ensure_dir()

        with FileLock(self.lock_path):
            # Load existing raw dict so we can preserve foreign top-level
            # keys. Any parse error or non-mapping content is treated as
            # "no existing data" — we won't blindly overwrite a corrupt
            # file, so callers wanting that can delete and retry.
            raw: dict = {}
            existing_mode: int | None = None
            if self.config_path.exists() and self.config_path.is_file():
                try:
                    with open(self.config_path) as f:
                        existing = yaml.safe_load(f)
                    if isinstance(existing, dict):
                        raw = existing
                except yaml.YAMLError:
                    raw = {}
                # Capture mode (e.g. 0o600 for ~/.astro/config.yaml which
                # holds astro-cli auth tokens) so writes don't widen perms.
                existing_mode = stat.S_IMODE(self.config_path.stat().st_mode)

            data = config.model_dump(by_alias=True, exclude_none=False)
            # Clean up default values at top level for cleaner YAML
            if data.get("current-instance") is None:
                del data["current-instance"]

            # Clean up telemetry section: drop the block when af has nothing
            # to contribute. Otherwise, drop None sub-fields (so we don't
            # blank out astro-cli's anonymous_id with af's None).
            telemetry_data = data.get("telemetry", {})
            has_id = telemetry_data.get("anonymous_id") is not None
            is_disabled = telemetry_data.get("enabled") is False
            if has_id or is_disabled:
                if telemetry_data.get("anonymous_id") is None:
                    telemetry_data.pop("anonymous_id", None)
            else:
                data.pop("telemetry", None)

            # Clean up default SSL values per instance for cleaner YAML
            for inst in data.get("instances", []):
                if inst.get("verify-ssl") is True:
                    del inst["verify-ssl"]
                if inst.get("ca-cert") is None:
                    del inst["ca-cert"]
                # Drop null auth fields so PAT instances don't carry empty
                # username/password/token/context lines that imply config.
                auth = inst.get("auth")
                if isinstance(auth, dict):
                    for key in list(auth.keys()):
                        if auth[key] is None:
                            del auth[key]

            # Telemetry is shared with astro-cli — both tools write
            # telemetry.enabled and telemetry.anonymous_id, and astro-cli
            # additionally writes telemetry.notice_shown. Sub-key merge
            # instead of wholesale replace so astro-cli's keys survive.
            af_tel = data.pop("telemetry", None)
            if af_tel is not None:
                disk_tel = raw.get("telemetry")
                if not isinstance(disk_tel, dict):
                    disk_tel = {}
                disk_tel.update(af_tel)
                raw["telemetry"] = disk_tel
            # If af has nothing to write for telemetry, leave whatever
            # astro-cli wrote on disk untouched. Notably, do NOT delete
            # raw["telemetry"] here.

            # Merge af-owned keys (instances, current-instance) into raw.
            # Absent keys are removed from raw so e.g. clearing
            # current-instance actually removes the line from disk.
            for key in _KNOWN_TOP_LEVEL_KEYS:
                if key in data:
                    raw[key] = data[key]
                else:
                    raw.pop(key, None)

            # sort_keys=True so the file converges on a canonical form
            # regardless of which tool wrote it (astro-cli's Viper also
            # alphabetizes). Without this, every cross-tool write churns
            # the diff.
            with open(self.config_path, "w") as f:
                yaml.safe_dump(raw, f, default_flow_style=False, sort_keys=True)

            if existing_mode is not None:
                os.chmod(self.config_path, existing_mode)
            else:
                # Fresh file: tighten to 0600 since the file is shared with
                # astro-cli at ~/.astro/config.yaml and may sit alongside
                # auth tokens. Don't trust umask to do the right thing.
                os.chmod(self.config_path, 0o600)

    def resolve_instance(self, instance_name: str | None = None) -> ResolvedConfig | None:
        """Resolve an instance to usable configuration.

        Args:
            instance_name: Name of instance to resolve, or None for current instance

        Returns:
            ResolvedConfig with interpolated values, or None if no instance

        Raises:
            ConfigError: If instance not found
        """
        config = self.load()

        # Determine which instance to use
        name = instance_name or config.current_instance
        if name is None:
            return None

        instance = config.get_instance(name)
        if instance is None:
            raise ConfigError(f"Instance '{name}' not found")

        # Interpolate environment variables in sensitive fields
        try:
            resolved_ca_cert = interpolate_config_value(instance.ca_cert)
            if resolved_ca_cert and not Path(resolved_ca_cert).is_file():
                raise ConfigError(
                    f"CA certificate file not found: {resolved_ca_cert} "
                    f"(configured in instance '{name}')"
                )
            if instance.auth:
                return ResolvedConfig(
                    url=instance.url,
                    username=interpolate_config_value(instance.auth.username),
                    password=interpolate_config_value(instance.auth.password),
                    token=interpolate_config_value(instance.auth.token),
                    auth_kind=instance.auth.kind,
                    astro_context=instance.auth.context,
                    instance_name=name,
                    sources={
                        "url": f"instance:{name}",
                        "auth": f"instance:{name}",
                    },
                    verify_ssl=instance.verify_ssl,
                    ca_cert=resolved_ca_cert,
                )
            return ResolvedConfig(
                url=instance.url,
                instance_name=name,
                sources={"url": f"instance:{name}"},
                verify_ssl=instance.verify_ssl,
                ca_cert=resolved_ca_cert,
            )
        except ValueError as e:
            raise ConfigError(f"Error resolving instance '{name}': {e}") from e

    # CRUD operations that delegate to config model

    def add_instance(
        self,
        name: str,
        url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        kind: AuthKind | None = None,
        context: str | None = None,
        deployment_id: str | None = None,
        source: str | None = None,
        verify_ssl: bool = True,
        ca_cert: str | None = None,
    ) -> None:
        """Add or update an instance."""
        config = self.load()
        config.add_instance(
            name,
            url,
            username=username,
            password=password,
            token=token,
            kind=kind,
            context=context,
            deployment_id=deployment_id,
            source=source,
            verify_ssl=verify_ssl,
            ca_cert=ca_cert,
        )
        self.save(config)

    def delete_instance(self, name: str) -> None:
        """Delete an instance."""
        config = self.load()
        config.delete_instance(name)
        self.save(config)

    def use_instance(self, name: str) -> None:
        """Set the current instance."""
        config = self.load()
        config.use_instance(name)
        self.save(config)

    def get_current_instance(self) -> str | None:
        """Get the current instance name."""
        config = self.load()
        return config.current_instance

    def set_telemetry_disabled(self, disabled: bool) -> None:
        """Enable or disable anonymous usage telemetry."""
        config = self.load()
        config.telemetry.enabled = not disabled
        self.save(config)

    def list_instances(self) -> list[Instance]:
        """List all instances."""
        config = self.load()
        return config.instances
