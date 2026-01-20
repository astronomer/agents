"""Tests for config.py - path utilities."""

from pathlib import Path


class TestConfigPaths:
    """Tests for configuration path functions."""

    def test_get_kernel_venv_dir(self):
        from lib.config import get_kernel_venv_dir

        result = get_kernel_venv_dir()
        assert isinstance(result, Path)
        assert result.parts[-3:] == (".astro", "ai", "kernel_venv")

    def test_get_kernel_connection_file(self):
        from lib.config import get_kernel_connection_file

        result = get_kernel_connection_file()
        assert isinstance(result, Path)
        assert result.name == "kernel.json"
        assert ".astro" in result.parts

    def test_get_config_dir(self):
        from lib.config import get_config_dir

        result = get_config_dir()
        assert isinstance(result, Path)
        assert result.parts[-3:] == (".astro", "ai", "config")
