"""Configuration utilities for the data-warehouse package."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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


def get_session_data_dir(session_id: str) -> Path:
    """Get the data directory for a session (for query results, etc.).

    Args:
        session_id: The session identifier

    Returns:
        Path to the session data directory
    """
    session_dir = ensure_session_dir(session_id)
    data_dir = session_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
