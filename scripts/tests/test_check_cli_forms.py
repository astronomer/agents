"""Tests for scripts/check_cli_forms.py and scripts/sync_cli_version_block.py.

python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import check_cli_forms as lint  # noqa: E402
import sync_cli_version_block as sync  # noqa: E402

SOURCE = lint.load_source()
FRONT = "---\nname: demo\ndescription: Demo skill. Mentions v1 and `af dags list` freely.\n---\n\n# Demo\n\nIntro.\n\n"


def md(body: str) -> str:
    return textwrap.dedent(body).lstrip("\n")


class SkillCase(unittest.TestCase):
    """Builds a throwaway skill directory per test."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "demo"
        self.dir.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, body: str, name: str = "SKILL.md", block: bool = True) -> None:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        head = FRONT + (SOURCE + "\n" if block and name == "SKILL.md" else "")
        path.write_text(
            head + md(body) if name == "SKILL.md" else md(body), encoding="utf-8"
        )

    def problems(self) -> list[str]:
        return lint.check_skill(self.dir, SOURCE)

    def assertClean(self) -> None:
        self.assertEqual(self.problems(), [])

    def assertFlags(self, fragment: str) -> None:
        found = self.problems()
        self.assertTrue(
            any(fragment in p for p in found), f"expected {fragment!r} in {found}"
        )


class Accepts(SkillCase):
    def test_v2_commands_with_v1_lines(self) -> None:
        self.write("""
            ## Use

            Run `astro local af dags list` to see Dags.

            ```bash
            astro local af dags list -o json | jq '.[].dag_id'
            # v1: af dags list | jq '.dags[].dag_id'
            astro af dags list -d prod
            # v1: af instance use prod
            # v1: af dags list
            astro local check
            # v1: astro dev parse
            ```

            **v1:** `trigger-wait` exits 0 even on failure; read the JSON.

            - **v1:** a list item marker works too.

            > **v1:** so does a blockquote.

            | Task | Command |
            |---|---|
            | Parse | `astro local check` |

            The REST API lives under `/api/v1` on Airflow 2.
            """)
        self.assertClean()

    def test_v1_only_command_under_v2_none(self) -> None:
        self.write("""
            ## Use

            ```bash
            astro local start
            # v2: none (the proxy has no stop command)
            # v1: astro dev proxy stop
            ```
            """)
        self.assertClean()

    def test_af_registry_is_the_same_on_both(self) -> None:
        self.write("""
            ## Use

            Use `af registry modules <provider>`, or `uvx --from astro-airflow-mcp af registry providers`.

            ```bash
            af registry parameters standard
            astro local start
            ```
            """)
        self.assertClean()

    def test_non_shell_blocks_and_comment_lines_are_not_checked(self) -> None:
        self.write("""
            ## Use

            ```python
            class Extract(Blueprint):  # v1
                cmd = "af dags list"
            ```

            ```bash
            # Only let Otto run af and shell
            astro otto --allowed-tools af,bash "diagnose"
            astro local start
            ```
            """)
        self.assertClean()

    def test_skill_without_commands_needs_no_block(self) -> None:
        self.write(
            """
            ## Use

            Talk about v1 and v2 all you like; nothing here runs the CLI.
            """,
            block=False,
        )
        self.assertClean()

    def test_reference_file_follows_body_rules(self) -> None:
        self.write(
            "## Use\n\nSee reference.\n\n```bash\nastro local af dags list\n```\n"
        )
        self.write(
            """
            # Ref

            ```bash
            astro local af version
            # v1: af config version
            ```
            """,
            name="reference/ref.md",
        )
        self.assertClean()

    def test_version_neutral_commands_need_no_block(self) -> None:
        self.write(
            """
            ## Use

            Run `astro otto --persona reviewer` in CI, and check `af registry providers`.

            ```bash
            astro otto --mode text "review this"
            ```
            """,
            block=False,
        )
        self.assertClean()

    def test_command_in_reference_alone_requires_block(self) -> None:
        self.write("## Use\n\nNothing to run here.\n", block=False)
        self.write("```bash\nastro local start\n```\n", name="reference/ref.md")
        self.assertFlags("needs exactly one Astro CLI version block")


class Rejects(SkillCase):
    def test_missing_block(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n```\n", block=False)
        self.assertFlags("needs exactly one Astro CLI version block")

    def test_drifted_block(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n```\n")
        path = self.dir / "SKILL.md"
        path.write_text(
            path.read_text().replace("run them as written", "run them"),
            encoding="utf-8",
        )
        self.assertFlags("differs from shared/astro-cli-version.md")

    def test_two_blocks(self) -> None:
        self.write("## Use\n\n" + SOURCE + "\n```bash\nastro local start\n```\n")
        self.assertFlags("exactly one")

    def test_block_after_first_section(self) -> None:
        path = self.dir / "SKILL.md"
        path.write_text(
            FRONT
            + "## First\n\nText.\n\n"
            + SOURCE
            + "\n```bash\nastro local start\n```\n",
            encoding="utf-8",
        )
        self.assertFlags("must come before the first `##` section")

    def test_block_in_reference_file(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n```\n")
        (self.dir / "ref.md").write_text(SOURCE, encoding="utf-8")
        self.assertFlags("belongs only in SKILL.md")

    def test_block_in_skill_without_commands(self) -> None:
        self.write("## Use\n\nNo commands.\n")
        self.assertFlags("should not carry the version block")

    def test_trailing_v1_comment(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local start   # v1: astro dev start\n```\n"
        )
        self.assertFlags('"v1" in a code line')

    def test_bare_v1_command_in_code(self) -> None:
        self.write("## Use\n\n```bash\naf dags list\n```\n")
        self.assertFlags("v1-only command outside a `# v1:` line")

    def test_astro_dev_in_code(self) -> None:
        self.write("## Use\n\n```bash\nastro dev restart\n```\n")
        self.assertFlags("v1-only command outside a `# v1:` line")

    def test_uvx_af_in_code(self) -> None:
        self.write(
            "## Use\n\n```bash\nuvx --from astro-airflow-mcp af dags list\n```\n"
        )
        self.assertFlags("v1-only command outside a `# v1:` line")

    def test_v1_line_under_comment(self) -> None:
        self.write(
            "## Use\n\n```bash\n# start it\n# v1: astro dev start\nastro local start\n```\n"
        )
        self.assertFlags("directly under the v2 command")

    def test_v1_line_first_in_block(self) -> None:
        self.write(
            "## Use\n\n```bash\n# v1: astro dev start\n```\n\n```bash\nastro local start\n```\n"
        )
        self.assertFlags("directly under the v2 command")

    def test_v1_line_after_blank(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local start\n\n# v1: astro dev start\n```\n"
        )
        self.assertFlags("directly under the v2 command")

    def test_v1_line_outside_code(self) -> None:
        self.write("## Use\n\n`astro local start`\n# v1: astro dev start\n")
        self.assertFlags("must be inside a code block")

    def test_redundant_v1_line(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local af dags list -o json\n# v1: af dags list\n```\n"
        )
        self.assertFlags("redundant")

    def test_empty_v1_line(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n# v1:\n```\n")
        self.assertFlags("empty")

    def test_v2_none_without_v1_line(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local start\n# v2: none\nastro local stop\n```\n"
        )
        self.assertFlags("must be followed by the `# v1:` line")

    def test_other_v2_comment(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local stop\n# v2: astro local start\n# v1: astro dev start\n```\n"
        )
        self.assertFlags("the only `# v2:` line is `# v2: none`")

    def test_v1_command_in_shell_block_variant(self) -> None:
        self.write("## Use\n\n```sh\nastro local start\nastro dev start\n```\n")
        self.assertFlags("v1-only command outside a `# v1:` line")

    def test_v1_command_in_indented_code(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local start\n```\n\nOn the old CLI:\n\n    af dags list\n"
        )
        self.assertFlags("indented code block")

    def test_v1_command_in_prose(self) -> None:
        self.write(
            "## Use\n\nRun `astro local start` (on v1, `astro dev start`).\n\n```bash\nastro local start\n```\n"
        )
        self.assertFlags("v1-only command in prose")

    def test_v1_command_on_marker_line(self) -> None:
        self.write(
            "## Use\n\n```bash\nastro local start\n```\n\n**v1:** run `af dags list` instead.\n"
        )
        self.assertFlags("v1-only command in prose")

    def test_v1_command_in_table(self) -> None:
        self.write(
            "## Use\n\n| Task | Command |\n|---|---|\n| Parse | `astro dev parse` |\n"
        )
        self.assertFlags("v1-only command in prose or a table")

    def test_table_with_v1_column(self) -> None:
        self.write(
            "## Use\n\n| Task | v2 | v1 |\n|---|---|---|\n| Parse | `astro local check` | the old parse |\n"
        )
        self.assertFlags("table with a v1 column")

    def test_v1_prose(self) -> None:
        self.write(
            "## Use\n\nOn v1 this behaves differently.\n\n```bash\nastro local start\n```\n"
        )
        self.assertFlags("v1 mentioned in prose")

    def test_marker_mid_line(self) -> None:
        self.write(
            "## Use\n\nIt differs. **v1:** it exits 0.\n\n```bash\nastro local start\n```\n"
        )
        self.assertFlags("v1 mentioned in prose")

    def test_probe_outside_block(self) -> None:
        self.write(
            "## Use\n\nCheck first: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`\n"
        )
        self.assertFlags("version probe belongs only")


class Helpers(unittest.TestCase):
    def test_v2_af_is_not_v1(self) -> None:
        self.assertFalse(lint.has_v1_command("astro local af dags list"))
        self.assertFalse(lint.has_v1_command("astro af dags list -d prod"))
        self.assertFalse(lint.has_v1_command("the `af` CLI"))
        self.assertFalse(lint.has_v1_command("leaf node"))

    def test_v1_forms(self) -> None:
        self.assertTrue(lint.has_v1_command("af dags list"))
        self.assertTrue(lint.has_v1_command("af <cmd>"))
        self.assertTrue(lint.has_v1_command("astro dev start"))
        self.assertTrue(lint.has_v1_command("echo x | af api ls"))
        self.assertFalse(lint.has_v1_command("af registry providers"))

    def test_mechanical_v1(self) -> None:
        self.assertEqual(
            lint.mechanical_v1("astro local af runs list -o json"), "af runs list"
        )
        self.assertEqual(
            lint.mechanical_v1("astro local api ls --output json"), "af api ls"
        )


class Sync(SkillCase):
    def test_inserts_before_first_section(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n```\n", block=False)
        self.assertTrue(sync.sync(self.dir, SOURCE))
        text = (self.dir / "SKILL.md").read_text()
        self.assertLess(text.index(lint.START), text.index("## Use"))
        self.assertClean()

    def test_replaces_drifted_copy_in_place(self) -> None:
        self.write("## Use\n\n```bash\nastro local start\n```\n")
        path = self.dir / "SKILL.md"
        path.write_text(
            path.read_text().replace("run them as written", "run them"),
            encoding="utf-8",
        )
        self.assertTrue(sync.sync(self.dir, SOURCE))
        self.assertClean()
        self.assertFalse(sync.sync(self.dir, SOURCE))

    def test_removes_block_from_skill_without_commands(self) -> None:
        self.write("## Use\n\nNo commands.\n")
        self.assertTrue(sync.sync(self.dir, SOURCE))
        self.assertNotIn(lint.START, (self.dir / "SKILL.md").read_text())
        self.assertClean()


class Repository(unittest.TestCase):
    def test_every_skill_passes(self) -> None:
        problems = [p for d in lint.skill_dirs([]) for p in lint.check_skill(d, SOURCE)]
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
