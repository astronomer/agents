"""Configuration scopes and project-root discovery.

af supports three config scopes (in increasing specificity):

    GLOBAL          ~/.astro/config.yaml          per-user
    PROJECT_SHARED  <root>/.astro/config.yaml     committed; team-shared
    PROJECT_LOCAL   <root>/.astro/config.local.yaml  gitignored; per-user

``<root>`` is the nearest ancestor of the current working directory
containing a ``.astro/`` directory, found by walking up. The marker
matches astro-cli's project root, so the same boundary applies to both
tools. AUTO defers the choice to the layered config (project-shared
when in a project, global otherwise; ``af instance use`` prefers
project-local instead).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

PROJECT_MARKER_DIR = ".astro"


class Scope(Enum):
    """Where a config read or write applies."""

    GLOBAL = "global"
    PROJECT_SHARED = "project"
    PROJECT_LOCAL = "local"
    # AUTO resolves at call time: project-shared in a project, global
    # outside one (with `use` preferring project-local). Use a concrete
    # scope to override.
    AUTO = "auto"


def discover_project_root(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for a directory containing ``.astro/``.

    Stops at the user's home directory (so ``$HOME/.astro`` does not make
    every shell session look like an astro project) and at the filesystem
    root. Returns the first ancestor that contains a ``.astro/`` directory,
    or ``None`` if no such ancestor exists.
    """
    if start is None:
        try:
            start = Path.cwd()
        except (FileNotFoundError, OSError):
            # cwd was deleted or otherwise unreadable — there's no
            # filesystem position to walk up from. Skip layering.
            return None

    try:
        start = start.resolve()
    except OSError:
        return None

    home = Path.home().resolve()

    # Walk up. Path.parents stops at the filesystem root, then yields the
    # root itself; combined with the explicit `start` check below, every
    # ancestor is visited exactly once.
    for candidate in (start, *start.parents):
        # Don't treat $HOME as a project root: ~/.astro/ is the user's
        # global astro-cli config dir, not a project marker.
        if candidate == home:
            return None
        marker = candidate / PROJECT_MARKER_DIR
        if marker.is_dir():
            return candidate

    return None
