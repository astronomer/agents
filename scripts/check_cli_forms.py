#!/usr/bin/env python3
"""Check that skills write Astro CLI commands in the one v1/v2 format.

Every skill that runs Astro CLI or `af` commands follows the same pattern:

1. Its SKILL.md carries the shared "Astro CLI version" block, byte-identical to
   shared/astro-cli-version.md, before its first `##` section and before any
   command. scripts/sync_cli_version_block.py copies it in.
2. Commands are written in their Astro CLI v2 form.
3. A v1 form that the block's rewrite rule doesn't give sits on its own line
   directly under the v2 command, in the same code block: `# v1: <cmd>`, or
   `# v1: none` when v1 has no equivalent. Every `astro local ...` (other than
   `astro local af` / `astro local api`) and `astro init` command needs one.
   A v1-only command with no v2 counterpart hangs off a `# v2: none` line.
4. A behavior difference that isn't a command sits on its own line starting
   `**v1:**` (or `**v2:**`), or under a heading that starts `v1:`.

So outside the block, a v1-only command (`astro dev ...`, the standalone
`af ...`) may appear only on a `# v1:` line or a `**v1:**` line, and "v1" (or
"1.x") only in those markers. `astro otto` and `af registry` are the same on
both versions.

    scripts/check_cli_forms.py                  # every skill under skills/
    scripts/check_cli_forms.py skills/airflow   # named skills only

Exits 1 and prints one line per problem if anything is off. The same file
ships in astronomer/agents and astronomer/hosted-skills.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "shared" / "astro-cli-version.md"
START = "<!-- astro-cli-version:start -->"
END = "<!-- astro-cli-version:end -->"
PROBE = "astro local af --help"

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
SPAN_RE = re.compile(r"`([^`\n]+)`")
H2_RE = re.compile(r"^##\s")
# A shell command at the start of a line or inline code span, after any
# leading `$ ` prompt or `NAME=value` environment assignments.
LEAD_RE = re.compile(r"^\s*(?:\$\s+)?(?:[A-Z_][A-Z0-9_]*=\S*\s+)*")
CMD_START_RE = re.compile(r"(?:astro\s+[a-z][\w-]*|af\s+[a-z<\[][\w<>\[\]-]*)")
# Commands spelled the same on both versions; a skill that runs only these
# needs no version block.
NEUTRAL_RE = re.compile(r"(?:astro\s+otto|af\s+registry)\b")
ASTRO_DEV_RE = re.compile(r"\bastro\s+dev\b")
# `af registry` reads the public provider registry and is the standalone `af`
# on both versions, so it is not a v1 form.
AF_RE = re.compile(r"(?<![\w./-])af\s+(?!registry\b)(?=[a-z<\[$-])")
V2_AF_PREFIX_RE = re.compile(r"\bastro(?:\s+local)?\s+$")
V1_WORD_RE = re.compile(r"(?<![\w/.-])v1(?![\w/.-])")
V1_PROSE_RE = re.compile(r"(?<![\w/.-])v1(?![\w/.-])|\b1\.x\b")
# v2 commands the rewrite rule doesn't cover, so each needs a `# v1:` line
# (`# v1: none` when v1 has no equivalent).
NEEDS_V1_RE = re.compile(r"astro\s+(?:local\s+(?!af\b|api\b)[a-z]|init\b)")
V1_LINE_RE = re.compile(r"^\s*# v1:")
# A v1-only command, with no v2 counterpart, hangs off a `# v2: none` line.
V2_NONE_RE = re.compile(r"^\s*# v2: none\b")
V2_LINE_RE = re.compile(r"^\s*# v2:")
# Code blocks in these languages (or none) hold shell commands; the rest
# (Python, YAML, ...) are not checked.
SHELL_LANGS = {
    "",
    "bash",
    "sh",
    "shell",
    "zsh",
    "console",
    "text",
    "cmd",
    "bat",
    "powershell",
    "pwsh",
}
# A `**v1:**` line (in a list or blockquote too), or a heading that starts `v1:`.
MARKER_LINE_RE = re.compile(
    r"^\s*(?:(?:>\s*)*(?:[-*+]\s+|\d+\.\s+)?\*\*v[12]:\*\*\s|#{1,6}\s+v[12]:\s)"
)
TABLE_V1_HEADER_RE = re.compile(r"^\s*\|.*\|\s*v1\s*\|")


@dataclass
class Line:
    """One line of a markdown file, classified."""

    number: int
    text: str
    in_code: bool
    in_block: bool
    in_frontmatter: bool
    shell: bool = True


def classify(text: str) -> list[Line]:
    """Split a markdown file into lines tagged with where each one sits."""
    lines: list[Line] = []
    fence: str | None = None
    shell = True
    in_block = False
    in_frontmatter = False
    raw = text.split("\n")
    for i, line in enumerate(raw):
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            lines.append(Line(i + 1, line, False, False, True))
            continue
        if in_frontmatter:
            lines.append(Line(i + 1, line, False, False, True))
            if line.strip() == "---":
                in_frontmatter = False
            continue
        if fence is None and line.strip() == START:
            in_block = True
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if fence is None:
                fence = marker
                info = line.strip()[len(marker) :].strip().split()
                shell = (info[0].lower() if info else "") in SHELL_LANGS
                lines.append(Line(i + 1, line, True, in_block, False, shell))
                continue
            if (
                marker[0] == fence[0]
                and len(marker) >= len(fence)
                and line.strip() == marker
            ):
                fence = None
                lines.append(Line(i + 1, line, True, in_block, False, shell))
                shell = True
                continue
        lines.append(
            Line(
                i + 1,
                line,
                fence is not None,
                in_block,
                False,
                shell if fence else True,
            )
        )
        if fence is None and line.strip() == END:
            in_block = False
    return lines


def has_v1_command(s: str) -> bool:
    """True if s contains an `astro dev` command or a standalone `af` command."""
    if ASTRO_DEV_RE.search(s):
        return True
    for m in AF_RE.finditer(s):
        if not V2_AF_PREFIX_RE.search(s[: m.start()]):
            return True
    return False


def starts_with_command(s: str) -> bool:
    """True if s begins with an `astro ...` or `af ...` invocation that differs by version."""
    rest = s[LEAD_RE.match(s).end() :]
    return bool(CMD_START_RE.match(rest)) and not NEUTRAL_RE.match(rest)


def is_command_line(text: str) -> bool:
    """A line in a code block that is not blank and not a comment."""
    stripped = text.strip()
    return (
        bool(stripped) and not stripped.startswith("#") and FENCE_RE.match(text) is None
    )


def mechanical_v1(cmd: str) -> str:
    """The v1 form the block's rewrite rule gives for a v2 command."""
    s = re.sub(r"\s+#\s.*$", "", cmd)
    s = s.replace("astro local af", "af").replace("astro local api", "af api")
    s = re.sub(r"\s+(?:-o\s*=?\s*|--output(?:\s+|=))json\b", "", s)
    return " ".join(s.split())


def file_runs_cli(lines: list[Line]) -> bool:
    """True if a code line or inline code span outside the block runs a command."""
    return runs_command(lines)


def runs_command(lines: list[Line]) -> bool:
    """True if any of these lines, outside the block, runs a version-dependent command."""
    for ln in lines:
        if ln.in_frontmatter or ln.in_block:
            continue
        if ln.in_code:
            if (
                FENCE_RE.match(ln.text)
                or not ln.shell
                or ln.text.strip().startswith("#")
            ):
                continue
            segments = re.split(r"\|\||&&|[|;]|\$\(", ln.text)
            if any(starts_with_command(seg) for seg in segments) or has_v1_command(
                ln.text
            ):
                return True
        else:
            spans = SPAN_RE.findall(ln.text)
            if any(starts_with_command(span) or has_v1_command(span) for span in spans):
                return True
    return False


def command_text(text: str) -> str:
    """A code line with any `$ ` prompt and leading environment assignments removed."""
    return text[LEAD_RE.match(text).end() :]


def check_body(rel: str, lines: list[Line]) -> list[str]:
    """Problems with the v1/v2 format in one file, outside the block."""
    problems: list[str] = []

    def bad(ln: Line, msg: str) -> None:
        problems.append(f"{rel}:{ln.number}: {msg}")

    prev: Line | None = None
    # The v2 command that still owes a `# v1:` line, if any.
    owed: Line | None = None
    for ln in lines:
        text = ln.text
        boundary = (
            ln.in_frontmatter
            or ln.in_block
            or (ln.in_code and (FENCE_RE.match(text) or not ln.shell))
            or not ln.in_code
        )
        continues = (
            prev is not None and prev.in_code and prev.text.rstrip().endswith("\\")
        )
        if (
            prev is not None
            and V2_LINE_RE.match(prev.text)
            and (boundary or not V1_LINE_RE.match(text))
        ):
            bad(
                prev,
                "a `# v2: none` line must be followed by the `# v1:` line it stands in for",
            )
        if owed is not None and not (
            ln.in_code and not boundary and (V1_LINE_RE.match(text) or continues)
        ):
            bad(
                owed,
                "this v2 command has no v1 form under the block's rewrite rule: add a `# v1:` line under it (`# v1: none` if v1 has no equivalent)",
            )
            owed = None
        if owed is not None and V1_LINE_RE.match(text):
            owed = None
        if (
            ln.in_frontmatter
            or ln.in_block
            or (ln.in_code and (FENCE_RE.match(text) or not ln.shell))
        ):
            prev = None
            continue
        if PROBE in text:
            bad(
                ln,
                "the version probe belongs only in the shared Astro CLI version block",
            )
        if ln.in_code:
            if V1_LINE_RE.match(text):
                v1 = " ".join(text.split("# v1:", 1)[1].split())
                anchors = prev is not None and (
                    is_command_line(prev.text)
                    or V1_LINE_RE.match(prev.text)
                    or V2_NONE_RE.match(prev.text)
                )
                if not v1:
                    bad(ln, "empty `# v1:` line")
                elif not anchors:
                    bad(
                        ln,
                        "a `# v1:` line must sit directly under the v2 command it replaces (or a `# v2: none` line)",
                    )
                elif (
                    is_command_line(prev.text)
                    and not prev.text.rstrip().endswith("\\")
                    and v1 == mechanical_v1(prev.text)
                ):
                    bad(
                        ln,
                        "redundant `# v1:` line: the block's rewrite rule already gives it",
                    )
            elif V2_LINE_RE.match(text):
                if not V2_NONE_RE.match(text):
                    bad(
                        ln,
                        "the only `# v2:` line is `# v2: none`, standing in for a v1-only command",
                    )
            else:
                comment = text.strip().startswith("#")
                if not comment and has_v1_command(text):
                    bad(
                        ln,
                        "v1-only command outside a `# v1:` line; write the v2 form and put the v1 form on a `# v1:` line under it",
                    )
                if V1_WORD_RE.search(text):
                    bad(
                        ln,
                        '"v1" in a code line; a v1 form goes on its own `# v1:` line',
                    )
                if (
                    not comment
                    and not continues
                    and NEEDS_V1_RE.match(command_text(text))
                ):
                    owed = ln
        else:
            if V1_LINE_RE.match(text):
                bad(
                    ln,
                    "a `# v1:` line must be inside a code block, under its v2 command",
                )
            marker = MARKER_LINE_RE.match(text)
            if re.match(r"^(?: {4}|\t)", text) and has_v1_command(
                SPAN_RE.sub("", text)
            ):
                bad(
                    ln,
                    "v1-only command in an indented code block; use a fenced block with a `# v1:` line",
                )
            if not marker:
                for span in SPAN_RE.findall(text):
                    if has_v1_command(span):
                        bad(
                            ln,
                            f"v1-only command in prose or a table (`{span}`); move it to a `# v1:` line in a code block, or a `**v1:**` line",
                        )
            if TABLE_V1_HEADER_RE.match(text):
                bad(
                    ln,
                    "table with a v1 column; keep v2 commands in the table and v1 forms on `# v1:` lines",
                )
            elif V1_PROSE_RE.search(SPAN_RE.sub("", text)) and not marker:
                bad(
                    ln,
                    "v1 mentioned in prose; state a v1 difference on its own line starting `**v1:**`",
                )
        prev = ln
    if owed is not None:
        bad(
            owed,
            "this v2 command has no v1 form under the block's rewrite rule: add a `# v1:` line under it (`# v1: none` if v1 has no equivalent)",
        )
    return problems


def check_skill(skill_dir: Path, source: str) -> list[str]:
    """Problems with one skill directory."""
    problems: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    files = sorted(p for p in skill_dir.rglob("*.md") if p.is_file())
    parsed = {p: classify(p.read_text(encoding="utf-8")) for p in files}
    runs_cli = any(file_runs_cli(lines) for lines in parsed.values())

    for path, lines in parsed.items():
        rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        text = path.read_text(encoding="utf-8")
        if path != skill_md and (START in text or END in text):
            problems.append(
                f"{rel}: the Astro CLI version block belongs only in SKILL.md"
            )
        if runs_cli:
            problems.extend(check_body(rel, lines))

    if not skill_md.is_file():
        return problems
    rel = (
        str(skill_md.relative_to(ROOT))
        if skill_md.is_relative_to(ROOT)
        else str(skill_md)
    )
    text = skill_md.read_text(encoding="utf-8")
    starts, ends = text.count(START), text.count(END)
    if not runs_cli:
        if starts or ends:
            problems.append(
                f"{rel}: runs no Astro CLI commands, so it should not carry the version block"
            )
        return problems
    if starts != 1 or ends != 1:
        problems.append(
            f"{rel}: runs Astro CLI commands, so it needs exactly one Astro CLI version block (run scripts/sync_cli_version_block.py)"
        )
        return problems
    begin = text.index(START)
    finish = text.index(END) + len(END)
    if finish < begin or text[begin:finish] + "\n" != source:
        problems.append(
            f"{rel}: the Astro CLI version block differs from shared/astro-cli-version.md (run scripts/sync_cli_version_block.py)"
        )
    for ln in parsed[skill_md]:
        if ln.in_frontmatter:
            continue
        if not ln.in_code and ln.text.strip() == START:
            break
        if runs_command([ln]):
            problems.append(
                f"{rel}:{ln.number}: a command before the Astro CLI version block; the probe has to run first"
            )
        if ln.in_code:
            continue
        if H2_RE.match(ln.text):
            problems.append(
                f"{rel}:{ln.number}: the Astro CLI version block must come before the first `##` section"
            )
            break
    return problems


def load_source() -> str:
    source = SOURCE.read_text(encoding="utf-8")
    if not source.startswith(START + "\n") or not source.endswith(END + "\n"):
        raise SystemExit(f"{SOURCE}: must start with {START} and end with {END}")
    return source


def skill_dirs(args: list[str]) -> list[Path]:
    if args:
        return [Path(a).resolve() for a in args]
    return sorted(p for p in (ROOT / "skills").iterdir() if (p / "SKILL.md").is_file())


def main(argv: list[str]) -> int:
    source = load_source()
    problems: list[str] = []
    for d in skill_dirs(argv):
        problems.extend(check_skill(d, source))
    for p in problems:
        print(p)
    if problems:
        print(
            f"\n{len(problems)} problem(s). The format is described in shared/astro-cli-version.md and scripts/check_cli_forms.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
