"""Session prelude template for Python kernel initialization.

This module provides the prelude code that is executed when a new session starts,
setting up the session directory and helper functions for safe file operations.

Mirrors the functionality from ai-cli's session_prelude.py.
"""

from pathlib import Path
from string import Template

# Directory containing the script templates
SCRIPTS_DIR = Path(__file__).parent / "scripts"


def _load_template(name: str) -> Template:
    """Load a script template from the scripts directory.

    Args:
        name: Name of the script file (without .py extension)

    Returns:
        Template object for string substitution
    """
    script_path = SCRIPTS_DIR / f"{name}.py"
    return Template(script_path.read_text())


# Session prelude template - loaded from scripts/session_prelude.py
SESSION_PRELUDE_TEMPLATE = _load_template("session_prelude")


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
