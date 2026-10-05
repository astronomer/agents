#!/usr/bin/env python3
"""Copy shared/astro-cli-version.md into every skill that runs Astro CLI commands.

Each skill ships as a self-contained archive, so the block is copied, not
linked. An existing copy (between its start and end markers) is replaced in
place; a skill without one gets it right before its first `##` section. A
skill that runs no Astro CLI commands has any copy removed.

    scripts/sync_cli_version_block.py                  # every skill
    scripts/sync_cli_version_block.py skills/airflow   # named skills only

scripts/check_cli_forms.py fails when a copy has drifted.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_cli_forms import (  # noqa: E402
    END,
    H2_RE,
    START,
    classify,
    file_runs_cli,
    load_source,
    skill_dirs,
)


def strip_block(text: str) -> str:
    begin = text.index(START)
    finish = text.index(END) + len(END)
    before = text[:begin].rstrip("\n")
    after = text[finish:].lstrip("\n")
    return before + "\n\n" + after


def insert_block(text: str, source: str) -> str:
    offset = 0
    for ln in classify(text):
        if not ln.in_frontmatter and not ln.in_code and H2_RE.match(ln.text):
            before = text[:offset].rstrip("\n")
            return before + "\n\n" + source + "\n" + text[offset:]
        offset += len(ln.text) + 1
    return text.rstrip("\n") + "\n\n" + source


def sync(skill_dir: Path, source: str) -> bool:
    """Bring one skill's block in line with the source. True if it changed."""
    skill_md = skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    runs_cli = any(
        file_runs_cli(classify(p.read_text(encoding="utf-8"))) for p in skill_dir.rglob("*.md")
    )
    new = text
    if START in new and END in new:
        new = strip_block(new)
    if runs_cli:
        new = insert_block(new, source) if START not in text else (
            text[: text.index(START)] + source.rstrip("\n") + text[text.index(END) + len(END) :]
        )
    if new != text:
        skill_md.write_text(new, encoding="utf-8")
        return True
    return False


def main(argv: list[str]) -> int:
    source = load_source()
    for d in skill_dirs(argv):
        if sync(d, source):
            print(f"updated {d / 'SKILL.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
