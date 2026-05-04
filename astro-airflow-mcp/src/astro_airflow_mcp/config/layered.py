"""Layered configuration: global + project-shared + project-local.

Three scopes co-located with astro-cli's config tree:

    GLOBAL          ~/.astro/config.yaml          per-user
    PROJECT_SHARED  <root>/.astro/config.yaml     committed; team-shared
    PROJECT_LOCAL   <root>/.astro/config.local.yaml  gitignored; per-user

``<root>`` is found by walking up from cwd looking for a ``.astro/``
directory (see ``discover_project_root``). When ``AF_CONFIG`` is set,
layering is skipped and behavior matches single-file mode (preserves
the ``astro otto`` wrapper's ``AF_CONFIG=/dev/null`` neutralize-config
sentinel and any other automation-set path).

Read precedence (most-specific wins): project-local → project-shared →
global. ``current-instance`` is sourced from project-local if set, else
global. Telemetry is global-only.

Write routing (when scope=AUTO):
- ``add_instance``: project-shared inside a project, else global
- ``use_instance``: project-local inside a project, else global
- ``delete_instance``: most-specific scope that has the named instance
  (so ``af instance delete prod`` peels scopes off one at a time if the
  same name is duplicated across them)

Explicit ``scope=PROJECT_*`` outside a project raises ``ConfigError`` —
there's no project root to write to. ``scope=GLOBAL`` always works.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from astro_airflow_mcp.config.loader import ConfigError, ConfigManager
from astro_airflow_mcp.config.models import AirflowCliConfig, Telemetry
from astro_airflow_mcp.config.scope import (
    PROJECT_MARKER_DIR,
    Scope,
    discover_project_root,
)

if TYPE_CHECKING:
    from pathlib import Path

    from astro_airflow_mcp.config.loader import ResolvedConfig
    from astro_airflow_mcp.config.models import AuthKind, Instance


class LayeredConfig:
    """Façade over per-scope :class:`ConfigManager` instances."""

    def __init__(self) -> None:
        """Discover the project root (or skip layering when ``AF_CONFIG``
        is set) and construct one :class:`ConfigManager` per active scope.

        Project managers are ``None`` when there is no project root —
        every read/write helper accounts for that.
        """
        self._global = ConfigManager()
        self._project_root = self._maybe_discover_project_root()
        self._project_shared: ConfigManager | None = None
        self._project_local: ConfigManager | None = None
        if self._project_root is not None:
            self._project_shared = ConfigManager(
                config_path=self._project_root / PROJECT_MARKER_DIR / "config.yaml"
            )
            self._project_local = ConfigManager(
                config_path=self._project_root / PROJECT_MARKER_DIR / "config.local.yaml"
            )

    @staticmethod
    def _maybe_discover_project_root() -> Path | None:
        # Single-file mode: AF_CONFIG explicitly points at one file, so
        # don't layer. Preserves the existing `astro otto` wrapper's
        # AF_CONFIG=/dev/null "neutralize global config" semantics.
        if os.environ.get(ConfigManager.CONFIG_ENV_VAR):
            return None
        return discover_project_root()

    # --- helpers -------------------------------------------------------

    def _scopes_in_priority_order(self) -> list[tuple[Scope, ConfigManager]]:
        """Most-specific first."""
        scopes: list[tuple[Scope, ConfigManager]] = []
        if self._project_local is not None:
            scopes.append((Scope.PROJECT_LOCAL, self._project_local))
        if self._project_shared is not None:
            scopes.append((Scope.PROJECT_SHARED, self._project_shared))
        scopes.append((Scope.GLOBAL, self._global))
        return scopes

    @staticmethod
    def _safe_load(manager: ConfigManager) -> AirflowCliConfig:
        """Read a scope's config without auto-creating defaults.

        A missing project file means "no project config", not "create
        a localhost instance for me." Errors degrade to an empty config
        rather than failing the whole layered read — a malformed project
        file shouldn't make the user's global config unreachable.
        """
        if not manager.config_path.exists():
            return AirflowCliConfig.model_validate({})
        try:
            return manager.load(create_default_if_missing=False)
        except ConfigError:
            return AirflowCliConfig.model_validate({})

    # --- read paths ----------------------------------------------------

    def list_instances(self) -> list[Instance]:
        return [inst for inst, _ in self.list_instances_with_scope()]

    def list_instances_with_scope(self) -> list[tuple[Instance, Scope]]:
        """Union of instances across scopes, narrower scope wins on name.

        Iteration is least-specific first so most-specific overwrites.
        """
        seen: dict[str, tuple[Instance, Scope]] = {}
        for scope, manager in reversed(self._scopes_in_priority_order()):
            for inst in self._safe_load(manager).instances:
                seen[inst.name] = (inst, scope)
        return list(seen.values())

    def get_instance(self, name: str) -> Instance | None:
        for _, manager in self._scopes_in_priority_order():
            inst = self._safe_load(manager).get_instance(name)
            if inst is not None:
                return inst
        return None

    def get_current_instance(self) -> str | None:
        if self._project_local is not None:
            local_current = self._safe_load(self._project_local).current_instance
            if local_current is not None:
                return local_current
        return self._safe_load(self._global).current_instance

    def load(self) -> AirflowCliConfig:
        """Merged view across scopes.

        Returned via ``model_construct`` so a stale project-local
        ``current-instance`` referring to a deleted instance doesn't
        raise — we silently clear it instead.
        """
        merged_instances = self.list_instances()
        current = self.get_current_instance()
        if current is not None and not any(i.name == current for i in merged_instances):
            current = None
        # Telemetry is global-only by design (it's a per-user
        # preference, not per-project).
        global_config = self._safe_load(self._global)
        telemetry = global_config.telemetry if global_config.telemetry else Telemetry()
        return AirflowCliConfig.model_construct(
            instances=merged_instances,
            current_instance=current,
            telemetry=telemetry,
        )

    def resolve_instance(self, instance_name: str | None = None) -> ResolvedConfig | None:
        name = instance_name or self.get_current_instance()
        if name is None:
            return None
        for _, manager in self._scopes_in_priority_order():
            if self._safe_load(manager).get_instance(name) is not None:
                return manager.resolve_instance(name)
        return None

    def find_instance(self, name: str) -> tuple[Instance, Scope, Path] | None:
        """Locate an instance and report which scope file it came from.

        Returns ``(instance, scope, file_path)`` for the most-specific
        scope containing ``name``, or ``None`` if not found anywhere.
        Used by ``af instance show`` to mirror ``git config --show-origin``.
        """
        for scope, manager in self._scopes_in_priority_order():
            inst = self._safe_load(manager).get_instance(name)
            if inst is not None:
                return inst, scope, manager.config_path
        return None

    # --- write paths ---------------------------------------------------

    def assert_writable(self, scope: Scope) -> None:
        """Raise ``ConfigError`` if ``scope`` can't be written from here.

        Used by ``af instance discover`` to fail fast — discovery does
        non-trivial work (Astro API calls, port scans) and we want the
        scope mismatch to surface before any of that happens, not at
        write time.
        """
        self._resolve_write_scope(scope)

    def _manager_for(self, scope: Scope) -> ConfigManager | None:
        """Return the manager for an explicit scope, or None if it's
        a project scope and we're not in a project."""
        if scope == Scope.GLOBAL:
            return self._global
        if scope == Scope.PROJECT_SHARED:
            return self._project_shared
        if scope == Scope.PROJECT_LOCAL:
            return self._project_local
        raise ValueError(f"Unsupported concrete scope: {scope}")

    def _resolve_write_scope(
        self, requested: Scope, *, prefer_local_in_project: bool = False
    ) -> tuple[Scope, ConfigManager]:
        """Pick a concrete (scope, manager) tuple for a write."""
        if requested != Scope.AUTO:
            manager = self._manager_for(requested)
            if manager is None:
                raise ConfigError(
                    f"Cannot write to {requested.value} scope: no project "
                    "root found. Run from inside an astro project (a "
                    "directory containing .astro/), or use --global."
                )
            return requested, manager
        # AUTO
        if self._project_root is not None:
            if prefer_local_in_project and self._project_local is not None:
                return Scope.PROJECT_LOCAL, self._project_local
            if self._project_shared is not None:
                return Scope.PROJECT_SHARED, self._project_shared
        return Scope.GLOBAL, self._global

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
        scope: Scope = Scope.AUTO,
    ) -> Scope:
        """Add or update an instance. Returns the scope it was written to.

        Bypasses ``ConfigManager.add_instance`` (which load()s with
        auto-create-localhost on missing files) — auto-create is
        appropriate only for the global file, never project files.
        """
        target_scope, manager = self._resolve_write_scope(scope)
        config = self._safe_load(manager)
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
        manager.save(config)
        return target_scope

    def delete_instance(self, name: str, scope: Scope = Scope.AUTO) -> Scope:
        """Delete an instance. Returns the scope it was deleted from.

        AUTO deletes from the most-specific scope that has the name.
        Same-named instances in other scopes are untouched (a second
        ``delete`` will pick them up).

        If no copy of ``name`` survives in any scope after the delete,
        also clears any sibling-scope ``current-instance`` pointer that
        referenced it. ``ConfigManager.delete_instance`` already does
        this within its own file; layered needs to scan siblings.
        """
        if scope == Scope.AUTO:
            target_scope: Scope | None = None
            for found_scope, manager in self._scopes_in_priority_order():
                config = self._safe_load(manager)
                if config.get_instance(name) is not None:
                    config.delete_instance(name)
                    manager.save(config)
                    target_scope = found_scope
                    break
            if target_scope is None:
                raise ValueError(f"Instance '{name}' does not exist")
        else:
            target_scope, manager = self._resolve_write_scope(scope)
            config = self._safe_load(manager)
            config.delete_instance(name)
            manager.save(config)

        self._clear_dangling_current_instance(name)
        return target_scope

    def _clear_dangling_current_instance(self, deleted_name: str) -> None:
        """Clear ``current-instance: <deleted_name>`` from any scope file
        if no copy of ``deleted_name`` survives anywhere.

        Skipped when a same-named instance still exists in another scope
        — the pointer is still valid via shadowing.
        """
        if self.get_instance(deleted_name) is not None:
            return
        for _, manager in self._scopes_in_priority_order():
            config = self._safe_load(manager)
            if config.current_instance == deleted_name:
                config.current_instance = None
                manager.save(config)

    def use_instance(self, name: str, scope: Scope = Scope.AUTO) -> Scope:
        """Set ``current-instance`` to ``name``. Returns the scope written.

        AUTO: project-local in a project, global otherwise. Validates
        against the merged view (so ``use`` can switch to an instance
        defined in any sibling scope).
        """
        if not self.get_instance(name):
            raise ValueError(f"Instance '{name}' does not exist")
        target_scope, manager = self._resolve_write_scope(scope, prefer_local_in_project=True)
        # No auto-create on miss; mutate current_instance directly
        # (ConfigManager.use_instance would re-validate against the
        # single file's instances).
        config = self._safe_load(manager)
        config.current_instance = name
        manager.save(config)
        return target_scope

    def set_telemetry_disabled(self, disabled: bool) -> None:
        # Telemetry is always global — never project-scoped.
        self._global.set_telemetry_disabled(disabled)
