<!-- astro-cli-version:start -->
## Astro CLI version

Commands in this skill, including its reference files, are written for Astro CLI v2. Before anything else, run this as a command of its own, with nothing chained before or after it, and choose the dialect from what it prints: `astro local af --help >/dev/null 2>&1 && echo v2 || echo v1`
On Windows `cmd.exe`, which has no `/dev/null`, run `astro local af --help >NUL 2>&1 && echo v2 || echo v1` instead.

- **v2:** run them as written.
- **v1** (Astro CLI 1.x, or no Astro CLI): use the standalone `af` CLI. Write `af` for `astro local af` and `af api` for `astro local api`, and drop `-o json` and `--output json` (`af` prints JSON, except `af instance` commands, which print tables). Where a command needs more than that, its v1 form is the line under it, starting `# v1:`. Where something behaves differently on v1, a line starting **v1:** says how. If `af` is not on PATH, write `uvx --from astro-airflow-mcp af <args>` out in full in every command. Don't put it in a shell variable or alias: zsh won't split `$AF`, and shell state doesn't carry over between commands.
- v2 replaced `astro dev` with `astro local`; `astro dev <cmd>` on v2 fails and names its replacement.
- If a v2 command reports an Astro v1 project, the v2 CLI cannot run that project, although the probe printed v2. Switch to the v1 forms: the standalone `af` still reaches an Airflow that is already running, but starting or parsing it (`astro dev ...`) needs Astro CLI 1.x. Tell the user; upgrading the project (`astro init`) is their call.
- `-d` and `-o` mean deployment and output in v2, but DAG id and offset in v1, so never carry either into a v1 command. `--dag-id`, `--offset`, `--state`, `--limit`, `--try`, `--map-index`, and `--timeout` mean the same in both.
- If a command here, or in the project's `AGENTS.md`, disagrees with the installed CLI, trust the CLI: check `astro <cmd> --help` (v1: `af <cmd> --help` or `astro dev <cmd> --help`).
<!-- astro-cli-version:end -->
