"""Tests for the top-level ``af migrate`` command.

Migration moves config from the legacy ``~/.af/config.yaml`` (af's
original location) to ``~/.astro/config.yaml`` (shared with astro-cli).
"""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from astro_airflow_mcp.cli.main import app


@pytest.fixture
def home_env(tmp_path, monkeypatch):
    """Pin Path.home() to an isolated tmp dir."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.delenv("AF_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)  # not in a project
    return fake_home, CliRunner()


def _legacy_config_text() -> str:
    return (
        "instances:\n"
        "  - name: legacy\n"
        "    url: http://legacy.example.com\n"
        "    auth:\n"
        "      kind: token\n"
        "      token: ${LEGACY_TOKEN}\n"
        "current-instance: legacy\n"
    )


class TestMigrate:
    def test_migrate_with_legacy_only(self, home_env):
        home, runner = home_env
        legacy = home / ".af" / "config.yaml"
        legacy.parent.mkdir()
        legacy.write_text(_legacy_config_text())

        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "migrated"

        # New file has the legacy content.
        new = home / ".astro" / "config.yaml"
        assert new.is_file()
        new_data = yaml.safe_load(new.read_text())
        names = [i["name"] for i in new_data["instances"]]
        assert names == ["legacy"]
        assert new_data["current-instance"] == "legacy"

        # Old file renamed to .bak.
        assert not legacy.exists()
        backup = legacy.parent / (legacy.name + ".bak")
        assert backup.is_file()
        assert "legacy" in backup.read_text()

    def test_migrate_preserves_existing_astro_cli_content(self, home_env):
        """If ~/.astro/config.yaml already has astro-cli content
        (project, contexts, etc.), migrate must preserve it via save's
        merge logic."""
        home, runner = home_env
        legacy = home / ".af" / "config.yaml"
        legacy.parent.mkdir()
        legacy.write_text(_legacy_config_text())

        new = home / ".astro" / "config.yaml"
        new.parent.mkdir()
        new.write_text(
            "contexts:\n  astronomer.io:\n    organization: org_x\n    workspace: ws_y\n"
            "project:\n  name: my-pipelines\n"
        )

        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0, result.output

        new_data = yaml.safe_load(new.read_text())
        assert new_data["contexts"]["astronomer.io"]["organization"] == "org_x"
        assert new_data["project"]["name"] == "my-pipelines"
        assert [i["name"] for i in new_data["instances"]] == ["legacy"]
        assert new_data["current-instance"] == "legacy"

    def test_migrate_idempotent_when_already_migrated(self, home_env):
        home, runner = home_env
        # No legacy file; new file exists with content (post-migrate state).
        new = home / ".astro" / "config.yaml"
        new.parent.mkdir()
        new.write_text("instances: []\n")

        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "already-migrated"

    def test_migrate_nothing_to_migrate(self, home_env):
        _home, runner = home_env
        # Neither file exists.
        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0
        assert json.loads(result.output)["status"] == "nothing-to-migrate"

    def test_migrate_uniques_backup_when_bak_exists(self, home_env):
        """A pre-existing .bak isn't clobbered — second migration uses
        .bak.1, .bak.2, etc."""
        home, runner = home_env
        legacy_dir = home / ".af"
        legacy_dir.mkdir()
        (legacy_dir / "config.yaml").write_text(_legacy_config_text())
        (legacy_dir / "config.yaml.bak").write_text("# leftover from a prior run")

        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["backup"].endswith(".bak.1")
        assert (legacy_dir / "config.yaml.bak").is_file()  # untouched
        assert (legacy_dir / "config.yaml.bak.1").is_file()

    def test_migrate_runs_after_implicit_migration_does_nothing_extra(self, home_env):
        """If the user did `af instance add` first (which triggers the
        implicit fallback + lazy save to new path), then runs `af
        migrate` later, migrate should still do the polish step (rename
        old → .bak)."""
        home, runner = home_env
        legacy = home / ".af" / "config.yaml"
        legacy.parent.mkdir()
        legacy.write_text(_legacy_config_text())

        # Simulate the implicit-fallback + first-save outcome: new file
        # exists with the legacy content already, but legacy still on
        # disk.
        new = home / ".astro" / "config.yaml"
        new.parent.mkdir()
        new.write_text(_legacy_config_text())

        result = runner.invoke(app, ["migrate"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "migrated"
        # Legacy renamed.
        assert not legacy.exists()
        assert (legacy.parent / (legacy.name + ".bak")).is_file()
        # New still has the content (save merged onto itself).
        new_data = yaml.safe_load(new.read_text())
        assert [i["name"] for i in new_data["instances"]] == ["legacy"]
