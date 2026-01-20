"""Configuration utilities for the analyzing-data skill."""

from pathlib import Path


def get_kernel_venv_dir() -> Path:
    """Get the path to the kernel virtual environment directory."""
    return Path.home() / ".astro" / "ai" / "kernel_venv"


def get_kernel_connection_file() -> Path:
    """Get the path to the kernel connection file."""
    return Path.home() / ".astro" / "ai" / "kernel.json"


def get_config_dir() -> Path:
    """Get the path to the config directory."""
    return Path.home() / ".astro" / "ai" / "config"
