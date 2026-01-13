"""Session prelude template for Python kernel initialization.

This module provides the prelude code that is executed when a new session starts,
setting up the session directory and helper functions for safe file operations.

Mirrors the functionality from ai-cli's session_prelude.py.
"""

from pathlib import Path
from string import Template

# Session prelude template
# This is executed in the kernel when a session starts
SESSION_PRELUDE_TEMPLATE = Template('''
# Session directory for file outputs (charts, exports, etc.)
from pathlib import Path

session_dir = Path("$session_dir")
session_dir.mkdir(parents=True, exist_ok=True)


def build_save_path(filename, subdir=""):
    """Build the full path for saving a file in the session directory.

    Uses pathlib's path resolution to prevent all traversal attacks including
    symbolic links, relative paths, and absolute paths.

    Args:
        filename: Name of file to save
        subdir: Optional subdirectory for organization (e.g., "charts", "exports", "analysis")

    Returns:
        Full path where the file should be saved (Path object)

    Raises:
        ValueError: If resolved path escapes session directory

    Example:
        plt.savefig(build_save_path("chart.png", "charts"))
        df.to_csv(build_save_path("results.csv", "exports"))
    """
    # Validate inputs BEFORE building path to prevent absolute path attacks
    if Path(filename).is_absolute():
        raise ValueError(f"Absolute paths not allowed: {filename}")
    if subdir and Path(subdir).is_absolute():
        raise ValueError(f"Absolute paths not allowed in subdir: {subdir}")
    if ".." in Path(filename).parts:
        raise ValueError(f"Parent directory references not allowed: {filename}")
    if subdir and ".." in Path(subdir).parts:
        raise ValueError(f"Parent directory references not allowed in subdir: {subdir}")

    # Now safe to build path
    if subdir:
        candidate = session_dir / subdir / filename
    else:
        candidate = session_dir / filename

    # Resolve to absolute path (handles symlinks, etc.)
    try:
        resolved_candidate = candidate.resolve()
        resolved_session = session_dir.resolve()

        # Final verification: ensure resolved path is still under session directory
        if not resolved_candidate.is_relative_to(resolved_session):
            raise ValueError(f"Path escapes session directory: {filename}")

        # Create subdirectory if needed
        if subdir:
            resolved_candidate.parent.mkdir(parents=True, exist_ok=True)

        return resolved_candidate
    except (ValueError, OSError) as e:
        raise ValueError(f"Invalid path: {e}")


def open_file(path, mode='rb'):
    """Open a file for reading or writing.

    This is a compatibility wrapper to match the kepler remote storage API.
    For local storage, this just calls the built-in open() function.

    Args:
        path: File path (Path object or string)
        mode: File mode ('r', 'w', 'rb', 'wb', etc.)

    Returns:
        File-like object that can be used with context manager

    Example:
        # For matplotlib
        path = build_save_path("chart.png", "charts")
        with open_file(path, 'wb') as f:
            plt.savefig(f, bbox_inches='tight', dpi=100)

        # For reading
        with open_file("data.csv", 'r') as f:
            data = f.read()
    """
    return open(path, mode)


# Configure matplotlib for non-interactive backend (saves to files only)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

print("Session directory:", session_dir)
print("Use build_save_path('filename.png', 'charts') to save files")
''')


def render_session_prelude(session_dir: Path) -> str:
    """Render the session prelude code with the given session directory.

    Args:
        session_dir: Path to the session directory

    Returns:
        Python code string to execute in the kernel
    """
    # Escape backslashes for Windows paths
    escaped_dir = str(session_dir).replace("\\", "\\\\")
    return SESSION_PRELUDE_TEMPLATE.substitute(session_dir=escaped_dir)

