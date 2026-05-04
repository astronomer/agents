"""CLI tests for `af instance` commands with scope flags.

These exercise the wiring between Typer flags and LayeredConfig — not
the underlying merge/validation logic, which lives in test_layered.py.
"""

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from astro_airflow_mcp.cli.instances import app


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Isolated home + project root, plus a CliRunner."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("AF_CONFIG", raising=False)

    project = tmp_path / "proj"
    project.mkdir()
    (project / ".astro").mkdir()
    monkeypatch.chdir(project)

    return project, CliRunner()


class TestAddCommandScopes:
    def test_default_in_project_writes_shared(self, cli_env):
        project, runner = cli_env
        result = runner.invoke(
            app,
            [
                "add",
                "prod",
                "--url",
                "https://prod.example.com",
                "--token",
                "${PROD_TOKEN}",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "(project)" in result.output

        shared = yaml.safe_load((project / ".astro" / "config.yaml").read_text())
        assert any(i["name"] == "prod" for i in shared["instances"])

    def test_global_flag_routes_to_global(self, cli_env):
        _project, runner = cli_env
        result = runner.invoke(
            app,
            [
                "add",
                "g",
                "--url",
                "http://g",
                "--token",
                "${T}",
                "--global",
            ],
        )
        assert result.exit_code == 0
        assert "(global)" in result.output

        home = Path.home()
        global_data = yaml.safe_load((home / ".astro" / "config.yaml").read_text())
        assert any(i["name"] == "g" for i in global_data["instances"])

    def test_local_flag_routes_to_local(self, cli_env):
        project, runner = cli_env
        result = runner.invoke(
            app,
            [
                "add",
                "l",
                "--url",
                "http://l",
                "--token",
                "literal-but-ok-here",
                "--local",
            ],
        )
        assert result.exit_code == 0
        assert "(local)" in result.output
        local_data = yaml.safe_load((project / ".astro" / "config.local.yaml").read_text())
        assert any(i["name"] == "l" for i in local_data["instances"])

    def test_mutually_exclusive_scope_flags_rejected(self, cli_env):
        _project, runner = cli_env
        result = runner.invoke(
            app,
            ["add", "x", "--url", "http://x", "--token", "${T}", "--global", "--local"],
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestUseCommand:
    def test_use_writes_to_local_in_project(self, cli_env):
        project, runner = cli_env
        runner.invoke(
            app,
            ["add", "prod", "--url", "https://p", "--token", "${T}"],
        )
        result = runner.invoke(app, ["use", "prod"])
        assert result.exit_code == 0
        assert "Switched to instance prod (local)" in result.output

        local_path = project / ".astro" / "config.local.yaml"
        assert "current-instance: prod" in local_path.read_text()


class TestDeleteCommand:
    def test_delete_default_picks_most_specific(self, cli_env):
        _project, runner = cli_env
        # Add same name to both global and project-shared.
        runner.invoke(
            app,
            ["add", "dup", "--url", "https://x", "--token", "${T}", "--global"],
        )
        runner.invoke(
            app,
            ["add", "dup", "--url", "https://y", "--token", "${T}"],  # default project
        )
        # Default delete: peels off project first.
        result = runner.invoke(app, ["delete", "dup"])
        assert result.exit_code == 0
        assert "(project)" in result.output

        # Second delete picks up the global copy.
        result = runner.invoke(app, ["delete", "dup"])
        assert result.exit_code == 0
        assert "(global)" in result.output


class TestShowCommand:
    def test_show_includes_scope_and_path(self, cli_env):
        project, runner = cli_env
        runner.invoke(
            app,
            ["add", "prod", "--url", "https://prod.example.com", "--token", "${T}"],
        )
        result = runner.invoke(app, ["show", "prod"])
        assert result.exit_code == 0
        assert "Instance: prod" in result.output
        assert "project" in result.output  # scope label
        # Path appears (rich may line-wrap, so check by collapsing whitespace).
        flat = result.output.replace("\n", "").replace(" ", "")
        assert str(project / ".astro" / "config.yaml").replace(" ", "") in flat

    def test_show_reports_missing_instance(self, cli_env):
        _project, runner = cli_env
        result = runner.invoke(app, ["show", "ghost"])
        assert "not found" in result.output


class TestListCommand:
    def test_scope_column_present(self, cli_env):
        _project, runner = cli_env
        runner.invoke(
            app,
            ["add", "p", "--url", "https://p", "--token", "${T}", "--global"],
        )
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "SCOPE" in result.output
        assert "global" in result.output
