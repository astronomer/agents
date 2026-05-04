"""Tests for config scope discovery."""

from pathlib import Path

from astro_airflow_mcp.config.scope import Scope, discover_project_root


class TestScopeEnum:
    def test_values(self):
        assert Scope.GLOBAL.value == "global"
        assert Scope.PROJECT_SHARED.value == "project"
        assert Scope.PROJECT_LOCAL.value == "local"
        assert Scope.AUTO.value == "auto"


class TestDiscoverProjectRoot:
    """``discover_project_root`` walks up from a path looking for ``.astro/``."""

    def test_returns_none_when_no_marker(self, tmp_path, monkeypatch):
        # Pin $HOME outside the search path so the walk doesn't terminate
        # early on the test runner's real home dir (which has ~/.astro/).
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        assert discover_project_root(tmp_path) is None

    def test_returns_cwd_when_marker_in_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        (tmp_path / ".astro").mkdir()

        assert discover_project_root(tmp_path) == tmp_path.resolve()

    def test_walks_up_from_subdir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        project = tmp_path / "proj"
        project.mkdir()
        (project / ".astro").mkdir()
        nested = project / "dags" / "domain"
        nested.mkdir(parents=True)

        assert discover_project_root(nested) == project.resolve()

    def test_stops_at_home_dir(self, tmp_path, monkeypatch):
        """``$HOME/.astro`` is the global astro-cli dir, not a project root."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".astro").mkdir()  # global astro config, not a project
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        # cwd is below $HOME, search must stop there and return None.
        nested = fake_home / "work" / "thing"
        nested.mkdir(parents=True)
        assert discover_project_root(nested) is None

    def test_finds_project_above_home(self, tmp_path, monkeypatch):
        """A project marker outside $HOME is still discoverable."""
        fake_home = tmp_path / "home" / "user"
        fake_home.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        project = tmp_path / "code" / "proj"
        project.mkdir(parents=True)
        (project / ".astro").mkdir()
        nested = project / "deeply" / "nested"
        nested.mkdir(parents=True)

        assert discover_project_root(nested) == project.resolve()

    def test_marker_must_be_a_directory(self, tmp_path, monkeypatch):
        """A file named ``.astro`` does not count as a project marker."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        (tmp_path / ".astro").write_text("not a dir")

        assert discover_project_root(tmp_path) is None

    def test_default_start_is_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        (tmp_path / ".astro").mkdir()
        monkeypatch.chdir(tmp_path)

        assert discover_project_root() == tmp_path.resolve()

    def test_unresolvable_start_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
        # A path that can't be resolved (e.g. doesn't exist with strict
        # resolution) — Path.resolve() with no strict flag actually still
        # works on missing paths, so this exercises the "no marker found"
        # case from a non-existent start.
        ghost = tmp_path / "does-not-exist"
        assert discover_project_root(ghost) is None
