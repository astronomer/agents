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
    load_source,
    runs_command,
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
    if text.count(START) != text.count(END) or text.count(START) > 1:
        raise SystemExit(f"{skill_md}: fix the version block's markers by hand first")
    runs_cli = any(
        runs_command(classify(p.read_text(encoding="utf-8")))
        for p in skill_dir.rglob("*.md")
    )
    if START in text:
        begin, finish = text.index(START), text.index(END) + len(END)
        new = (
            text[:begin] + source.rstrip("\n") + text[finish:]
            if runs_cli
            else strip_block(text)
        )
    else:
        new = insert_block(text, source) if runs_cli else text
    if new != text:
        with open(skill_md, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
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
