"""CLI coverage for explicit config writes that must not silently no-op."""

from pathlib import Path

from typer.testing import CliRunner

from astro_airflow_mcp.cli.main import app


def test_telemetry_write_fails_when_af_config_is_non_regular(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    neutralized_config = tmp_path / "neutralized-config"
    neutralized_config.mkdir()
    monkeypatch.setenv("AF_CONFIG", str(neutralized_config))

    result = CliRunner().invoke(app, ["telemetry", "disable"])

    assert result.exit_code == 2
    assert "af telemetry disable cannot persist" in result.output
    assert "AF_CONFIG points to a non-regular path" in result.output
    assert str(neutralized_config) in result.output
    assert list(neutralized_config.iterdir()) == []
