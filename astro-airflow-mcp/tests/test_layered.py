"""Tests for LayeredConfig: layered reads, write routing, validation gate."""

from pathlib import Path

import pytest

from astro_airflow_mcp.config import ConfigError, LayeredConfig, Scope


@pytest.fixture
def layered_env(tmp_path, monkeypatch):
    """Set up an isolated home + project root for layered-config tests.

    Returns the project root path. Three writable scope files:
        global:        <home>/.astro/config.yaml
        project shared: <project>/.astro/config.yaml
        project local:  <project>/.astro/config.local.yaml
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("AF_CONFIG", raising=False)

    project = tmp_path / "code" / "proj"
    project.mkdir(parents=True)
    (project / ".astro").mkdir()
    monkeypatch.chdir(project)
    return project


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestLayeredReads:
    def test_layering_skipped_when_af_config_set(self, tmp_path, monkeypatch):
        """AF_CONFIG=<path> means single-file mode; project files ignored.

        Preserves the ``astro otto`` wrapper's AF_CONFIG=/dev/null
        neutralize-config sentinel and any other automation-set path.
        """
        # Set up a project with a file that WOULD be picked up if layering
        # were active. AF_CONFIG steers to a different file entirely.
        af_path = tmp_path / "explicit.yaml"
        af_path.write_text(
            "instances:\n  - {name: explicit, url: http://x, auth: {kind: token, token: t}}\n"
        )

        project = tmp_path / "proj"
        (project / ".astro").mkdir(parents=True)
        (project / ".astro" / "config.yaml").write_text(
            "instances:\n  - {name: project, url: http://p, auth: {kind: token, token: t}}\n"
        )
        monkeypatch.chdir(project)
        monkeypatch.setenv("AF_CONFIG", str(af_path))

        layered = LayeredConfig()
        names = [i.name for i in layered.list_instances()]
        assert names == ["explicit"]
        assert "project" not in names

    def test_no_project_root_returns_only_global(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("AF_CONFIG", raising=False)

        # cwd has no .astro/ ancestor.
        not_a_project = tmp_path / "loose"
        not_a_project.mkdir()
        monkeypatch.chdir(not_a_project)

        # Global has a single instance.
        _write_yaml(
            fake_home / ".astro" / "config.yaml",
            "instances:\n  - {name: g, url: http://g, auth: {kind: token, token: t}}\n",
        )

        layered = LayeredConfig()
        rows = layered.list_instances_with_scope()
        assert [(i.name, s) for i, s in rows] == [("g", Scope.GLOBAL)]

    def test_union_across_scopes_with_no_collision(self, layered_env):
        project = layered_env
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n  - {name: g, url: http://g, auth: {kind: token, token: t}}\n",
        )
        _write_yaml(
            project / ".astro" / "config.yaml",
            "instances:\n  - {name: s, url: http://s, auth: {kind: token, token: t}}\n",
        )
        _write_yaml(
            project / ".astro" / "config.local.yaml",
            "instances:\n  - {name: l, url: http://l, auth: {kind: token, token: t}}\n",
        )

        rows = LayeredConfig().list_instances_with_scope()
        by_name = {i.name: s for i, s in rows}
        assert by_name == {
            "g": Scope.GLOBAL,
            "s": Scope.PROJECT_SHARED,
            "l": Scope.PROJECT_LOCAL,
        }

    def test_project_local_shadows_shared_shadows_global(self, layered_env):
        project = layered_env
        home = Path.home()
        for path, url in (
            (home / ".astro" / "config.yaml", "http://from-global"),
            (project / ".astro" / "config.yaml", "http://from-shared"),
            (project / ".astro" / "config.local.yaml", "http://from-local"),
        ):
            _write_yaml(
                path,
                f"instances:\n  - {{name: prod, url: {url}, auth: {{kind: token, token: t}}}}\n",
            )

        rows = LayeredConfig().list_instances_with_scope()
        assert len(rows) == 1
        inst, scope = rows[0]
        assert inst.url == "http://from-local"
        assert scope == Scope.PROJECT_LOCAL

    def test_resolve_uses_most_specific_scope(self, layered_env):
        project = layered_env
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n  - {name: prod, url: http://global, auth: {kind: token, token: g}}\n",
        )
        _write_yaml(
            project / ".astro" / "config.yaml",
            "instances:\n  - {name: prod, url: http://shared, auth: {kind: token, token: s}}\n",
        )

        resolved = LayeredConfig().resolve_instance("prod")
        assert resolved is not None
        assert resolved.url == "http://shared"
        assert resolved.token == "s"

    def test_current_instance_local_takes_precedence(self, layered_env):
        project = layered_env
        home = Path.home()
        # Both files set current-instance to a name they each own.
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n"
            "  - {name: glob, url: http://g, auth: {kind: token, token: t}}\n"
            "current-instance: glob\n",
        )
        _write_yaml(
            project / ".astro" / "config.local.yaml",
            "instances:\n"
            "  - {name: loc, url: http://l, auth: {kind: token, token: t}}\n"
            "current-instance: loc\n",
        )

        layered = LayeredConfig()
        assert layered.get_current_instance() == "loc"
        # And resolve() honors it.
        resolved = layered.resolve_instance()
        assert resolved is not None
        assert resolved.url == "http://l"

    def test_stale_local_current_instance_is_silently_cleared(self, layered_env):
        """A project-local current-instance pointing to a deleted instance
        shouldn't make load() raise — we want graceful degradation."""
        project = layered_env
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n  - {name: g, url: http://g, auth: {kind: token, token: t}}\n",
        )
        _write_yaml(
            project / ".astro" / "config.local.yaml",
            "current-instance: removed-long-ago\n",
        )

        merged = LayeredConfig().load()
        assert merged.current_instance is None
        # Instance from global is still visible.
        assert [i.name for i in merged.instances] == ["g"]

    def test_missing_project_files_dont_auto_create_localhost(self, layered_env):
        """LayeredConfig must not call ConfigManager.load() with default
        auto-create on project files — otherwise probing for project
        config writes a localhost stub into the project."""
        project = layered_env
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n  - {name: g, url: http://g, auth: {kind: token, token: t}}\n",
        )
        # Project files don't exist.

        rows = LayeredConfig().list_instances_with_scope()
        assert [(i.name, s) for i, s in rows] == [("g", Scope.GLOBAL)]
        assert not (project / ".astro" / "config.yaml").exists()
        assert not (project / ".astro" / "config.local.yaml").exists()

    def test_resolve_returns_none_when_instance_not_found(self, layered_env):
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "instances:\n  - {name: g, url: http://g, auth: {kind: token, token: t}}\n",
        )
        assert LayeredConfig().resolve_instance("nonexistent") is None

    def test_telemetry_is_global_only(self, layered_env):
        project = layered_env
        home = Path.home()
        _write_yaml(
            home / ".astro" / "config.yaml",
            "telemetry:\n  enabled: false\n  anonymous_id: g-id\n",
        )
        # A project-local telemetry block must NOT override.
        _write_yaml(
            project / ".astro" / "config.local.yaml",
            "telemetry:\n  enabled: true\n  anonymous_id: bogus-id\n",
        )

        merged = LayeredConfig().load()
        assert merged.telemetry.enabled is False
        assert merged.telemetry.anonymous_id == "g-id"


class TestLayeredWrites:
    """Scope-aware writes: AUTO routing, explicit scope, secret gates."""

    def test_add_auto_in_project_writes_to_shared(self, layered_env):
        layered = LayeredConfig()
        # astro_pat carries no secret, so it passes the shared-write gate.
        target = layered.add_instance(
            "prod",
            "https://prod.example.com",
            kind="astro_pat",
            context="astronomer.io",
            deployment_id="dep_123",
        )
        assert target == Scope.PROJECT_SHARED

        shared_path = layered_env / ".astro" / "config.yaml"
        assert "name: prod" in shared_path.read_text()
        # Not in global.
        global_path = Path.home() / ".astro" / "config.yaml"
        assert not global_path.exists() or "name: prod" not in global_path.read_text()

    def test_add_auto_outside_project_writes_to_global(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("AF_CONFIG", raising=False)
        not_a_project = tmp_path / "loose"
        not_a_project.mkdir()
        monkeypatch.chdir(not_a_project)

        layered = LayeredConfig()
        target = layered.add_instance("x", "http://x", token="${T}")
        assert target == Scope.GLOBAL
        assert (fake_home / ".astro" / "config.yaml").is_file()

    def test_add_explicit_global_in_project(self, layered_env):
        layered = LayeredConfig()
        target = layered.add_instance("g", "http://g", token="${T}", scope=Scope.GLOBAL)
        assert target == Scope.GLOBAL
        global_path = Path.home() / ".astro" / "config.yaml"
        assert "name: g" in global_path.read_text()

    def test_assert_writable_validates_scope_upfront(self, tmp_path, monkeypatch):
        """Used by `af instance discover` to fail before doing scan/API work."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("AF_CONFIG", raising=False)
        loose = tmp_path / "loose"
        loose.mkdir()
        monkeypatch.chdir(loose)

        layered = LayeredConfig()
        # GLOBAL is always writable
        layered.assert_writable(Scope.GLOBAL)
        # AUTO never raises
        layered.assert_writable(Scope.AUTO)
        # PROJECT_SHARED outside project: raises
        with pytest.raises(ConfigError, match="no project root"):
            layered.assert_writable(Scope.PROJECT_SHARED)

    def test_add_explicit_project_outside_project_raises(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)
        monkeypatch.delenv("AF_CONFIG", raising=False)
        loose = tmp_path / "loose"
        loose.mkdir()
        monkeypatch.chdir(loose)

        with pytest.raises(ConfigError, match="no project root"):
            LayeredConfig().add_instance("p", "http://p", token="${T}", scope=Scope.PROJECT_SHARED)

    def test_add_shared_accepts_any_credentials(self, layered_env):
        """No upfront gate — users opt into commits via gitignore choice."""
        target = LayeredConfig().add_instance(
            "p", "http://p", token="raw-token", scope=Scope.PROJECT_SHARED
        )
        assert target == Scope.PROJECT_SHARED

    def test_use_auto_in_project_writes_local(self, layered_env):
        # Add an instance to shared so use can find it.
        LayeredConfig().add_instance(
            "prod",
            "http://prod",
            kind="astro_pat",
            context="astronomer.io",
            scope=Scope.PROJECT_SHARED,
        )

        target = LayeredConfig().use_instance("prod")
        assert target == Scope.PROJECT_LOCAL

        local_path = layered_env / ".astro" / "config.local.yaml"
        assert local_path.is_file()
        assert "current-instance: prod" in local_path.read_text()
        # Shared file unaffected by the `use` (it doesn't write
        # current-instance there).
        shared_path = layered_env / ".astro" / "config.yaml"
        assert "current-instance" not in shared_path.read_text()

    def test_use_works_for_cross_scope_instance(self, layered_env):
        """`use prod` works when prod lives in shared but local has no
        instances of its own — the validator runs against the merged view."""
        # Put prod in shared; nothing in local; nothing in global.
        LayeredConfig().add_instance(
            "prod",
            "http://prod",
            kind="astro_pat",
            context="astronomer.io",
            scope=Scope.PROJECT_SHARED,
        )

        layered = LayeredConfig()
        layered.use_instance("prod")
        assert layered.get_current_instance() == "prod"

    def test_use_unknown_instance_raises(self, layered_env):
        with pytest.raises(ValueError, match="does not exist"):
            LayeredConfig().use_instance("nonexistent")

    def test_delete_auto_picks_most_specific_scope(self, layered_env):
        # Same name in shared AND global.
        layered = LayeredConfig()
        layered.add_instance(
            "dup", "http://shared", kind="astro_pat", context="x", scope=Scope.PROJECT_SHARED
        )
        layered.add_instance("dup", "http://global", token="${T}", scope=Scope.GLOBAL)

        target = LayeredConfig().delete_instance("dup")
        assert target == Scope.PROJECT_SHARED  # most-specific wins

        # Global copy still alive.
        rows = LayeredConfig().list_instances_with_scope()
        by_name = {i.name: s for i, s in rows}
        assert by_name == {"dup": Scope.GLOBAL}

    def test_delete_clears_dangling_current_instance_across_scopes(self, layered_env):
        """`use prod` writes current-instance to project-local; `delete prod`
        removes prod from project-shared. The local file's current-instance
        pointer is now dangling — must be cleared."""
        layered = LayeredConfig()
        layered.add_instance(
            "prod",
            "http://prod",
            kind="astro_pat",
            context="x",
            scope=Scope.PROJECT_SHARED,
        )
        layered.use_instance("prod")  # writes current-instance to local

        layered.delete_instance("prod")

        # Local file's current-instance must be cleared.
        local_path = layered_env / ".astro" / "config.local.yaml"
        if local_path.exists():
            assert "current-instance: prod" not in local_path.read_text()
        # And the merged view agrees.
        assert LayeredConfig().get_current_instance() is None

    def test_delete_keeps_current_instance_when_shadow_remains(self, layered_env):
        """Same name in two scopes: deleting the most-specific one leaves the
        pointer valid (it now resolves to the surviving copy)."""
        layered = LayeredConfig()
        layered.add_instance(
            "dup", "http://shared", kind="astro_pat", context="x", scope=Scope.PROJECT_SHARED
        )
        layered.add_instance("dup", "http://global", token="${T}", scope=Scope.GLOBAL)
        layered.use_instance("dup")  # writes current-instance to local

        layered.delete_instance("dup")  # removes shared copy; global remains

        assert LayeredConfig().get_current_instance() == "dup"
        assert LayeredConfig().get_instance("dup") is not None

    def test_delete_explicit_scope(self, layered_env):
        layered = LayeredConfig()
        layered.add_instance(
            "dup", "http://shared", kind="astro_pat", context="x", scope=Scope.PROJECT_SHARED
        )
        layered.add_instance("dup", "http://global", token="${T}", scope=Scope.GLOBAL)

        # Explicit --global skips shared even though shared is more specific.
        LayeredConfig().delete_instance("dup", scope=Scope.GLOBAL)
        rows = LayeredConfig().list_instances_with_scope()
        assert [(i.name, s) for i, s in rows] == [("dup", Scope.PROJECT_SHARED)]
