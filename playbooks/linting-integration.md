# Integrating linting with Claude Code

Linting reaches Claude at four surfaces. Putting a tool on the wrong one is why
these setups get abandoned — not because the linter was wrong, but because it
fired at the wrong moment.

## Choose the surface first

| Surface | Fires | Right for | Wrong for |
|---|---|---|---|
| **LSP plugin** | After every edit, inline | Type errors, symbol navigation | Formatting, style |
| **PostToolUse hook** | After each Write/Edit | Fast fixers: ruff, biome, prettier | Anything over ~2s |
| **Stop hook** | When the turn ends | tsc, mypy, pylint, sqlfluff | Per-edit feedback |
| **MCP / CI** | On demand or on push | Sonar, pip-audit, knip, npm audit | Anything needing an answer now |

The rule is latency. A checker that takes four seconds, run after every edit,
makes the session feel broken — and the hook that gets removed takes the fast
checks with it.

## 1. LSP first, and it is not a hook

Install the code-intelligence plugin for your language and its binary:

```
/plugin install pyright-lsp@claude-plugins-official
/plugin install typescript-lsp@claude-plugins-official
```

The language server reports type errors and missing imports straight back after
each edit, so Claude catches its own mistake in the same turn. No subprocess, no
hook latency, and it also gives real symbol navigation — which is what stops file
paths being guessed rather than looked up.

**Then do not also run a type checker in a PostToolUse hook.** `pyright` in a
hook duplicates what `pyright-lsp` already delivers, more slowly. Type checking
belongs in the LSP, or in the Stop hook if you have no LSP plugin.

## 2. PostToolUse: fix, don't report

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PROJECT_DIR}/hooks/lint_on_edit.py\""
          }
        ]
      }
    ]
  }
}
```

`hooks/lint_on_edit.py` reads `tool_input.file_path`, picks the fast linters this
repo has actually configured *and* has on PATH, runs their **fix** command on
that one file, and reports only what survives.

Four properties, each one a way the naive version fails:

- **One file, not the repo.** Linting the whole tree after every edit is slow and
  surfaces pre-existing issues in files nobody touched, which teaches everyone to
  ignore the output.
- **Fix rather than report.** A formatting problem the tool can repair itself
  should never reach the conversation. Spending a turn telling Claude about
  whitespace is waste.
- **What remains goes to Claude.** Exit 2 puts it on stderr, which Claude sees as
  a warning. A hook that finds a problem and keeps it to itself has done nothing.
  Note that PostToolUse cannot block — the edit already happened.
- **Degrade silently.** A linter that is not installed is skipped, not an error.
  Where the package index is blocked, half of them will be missing, and a hook
  that complains about that is a hook people delete.

## 3. Stop hook: the slow, whole-project checks

Run once when the turn ends, where four seconds is fine:

```bash
npx tsc --noEmit && mypy . && npx sqlfluff lint --dialect sparksql
```

Exit 2 blocks the stop, so Claude fixes before finishing rather than you finding
out later. Honour `stop_hook_active` so it blocks at most once.

`tsc --noEmit` is the highest-value check in a TypeScript repo and the one most
often missing — because `next build` type-checks, so people assume it is covered,
but nobody runs a build after every turn.

## 4. Sonar: MCP, not a hook

```
sonar integrate claude
```

Sonar ships an official Claude Code plugin and MCP server, so quality-gate status
and issues arrive in the session instead of a browser tab, and Claude can write,
scan and self-correct in one loop. It also blocks the agent from reading files
containing hardcoded credentials — a safety property independent of the linting.

Connecting to a self-hosted Server needs a **user** token; project, global and
scoped organization tokens will not work.

Server-side analysis is far too slow for a per-edit hook. Leave `sonar-scanner`
in CI and let the MCP server answer questions on demand.

## Per-stack wiring

Run `python tools/detect_stack.py --repo <path>` first — it proposes only what
the repo declares.

| Stack | LSP | PostToolUse | Stop | CI |
|---|---|---|---|---|
| Python | `pyright-lsp` | `ruff check --fix`, `ruff format` | `mypy`, `bandit` | `pip-audit`, `vulture` |
| PySpark | `pyright-lsp` | `ruff` | `pylint --load-plugins=databricks.labs.pylint.all` | `sqlfluff` over extracted SQL |
| SQL | — | — | `sqlfluff lint --dialect sparksql` | `sqlfluff`, Sonar |
| Next.js | `typescript-lsp` | `biome check --write` or `eslint --fix`, `prettier --write` | `tsc --noEmit` | `knip`, `npm audit` |

Two stack-specific notes. **Set the SQL dialect** — linting Databricks SQL as
`ansi` produces a stream of false errors that gets sqlfluff switched off.
**PySpark's linter is slow** because pylint imports your code, so it belongs in
the Stop hook, never per-edit.

## Also tell Claude the commands

Hooks enforce; CLAUDE.md informs. Put the commands in CLAUDE.md too, so Claude
can run them deliberately when it wants to check something rather than waiting
for a hook to tell it:

```markdown
## Checks
ruff check --fix <file>    # fast, runs automatically on edit
mypy .                     # slow, runs at end of turn
```

Keep it to the commands. Do not write "always run the formatter" — that is an
instruction where a hook belongs, and an instruction is followed most of the
time, which is the failure rate that misleads (ECC-0031).
