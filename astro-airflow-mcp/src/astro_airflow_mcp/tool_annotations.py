"""MCP tool safety annotations (read-only / destructive hints).

These map onto the MCP ``ToolAnnotations`` spec so a client can decide, *before*
invoking a tool, whether it is safe to auto-approve (reads) or must be gated
behind user confirmation (writes / destructive operations). This complements the
server-side ``AF_READ_ONLY`` guard, which only refuses a write *after* the model
has already decided to call it.

Defaults are cautious: a tool is only advertised as safe when it explicitly opts
in via :func:`read_only`. Writes default to destructive + non-idempotent and are
narrowed by the caller when a weaker hint is accurate (e.g. ``pause_dag`` is a
non-destructive, idempotent write).

``openWorldHint`` is True for every tool here: they all talk to an external
Airflow instance whose state is outside this process.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations


def read_only(title: str | None = None) -> ToolAnnotations:
    """Annotations for a tool that only reads Airflow state.

    Safe for clients to auto-approve. Reads are idempotent by definition.
    """
    return ToolAnnotations(
        title=title,
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


def write(
    title: str | None = None,
    *,
    destructive: bool = True,
    idempotent: bool = False,
) -> ToolAnnotations:
    """Annotations for a tool that modifies Airflow state.

    Defaults are deliberately cautious (destructive, non-idempotent). Callers
    narrow them for safer writes:

    - ``write(destructive=False, idempotent=True)`` — pause/unpause (reversible,
      re-applying reaches the same state).
    - ``write(destructive=False)`` — trigger (creates a new run; not destructive,
      but each call has an additional effect so it is not idempotent).
    - ``write(destructive=True, idempotent=True)`` — clear (discards run/task
      state, but re-clearing reaches the same end state).
    - ``write()`` — delete (destructive and not safely repeatable).
    """
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=True,
    )
