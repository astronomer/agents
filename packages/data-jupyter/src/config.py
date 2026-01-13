"""Configuration utilities for the data-jupyter package."""

from pathlib import Path


def get_kernel_venv_dir() -> Path:
    """Get the path to the kernel virtual environment directory.

    Returns:
        Path to ~/.astro/ai/kernel_venv
    """
    return Path.home() / ".astro" / "ai" / "kernel_venv"


def ensure_session_dir(session_id: str) -> Path:
    """Ensure a session directory exists and return its path.

    Args:
        session_id: The session identifier

    Returns:
        Path to the session directory
    """
    base_dir = Path.home() / ".astro" / "ai" / "sessions"
    session_dir = base_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir

