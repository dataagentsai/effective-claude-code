# hooks/

Reference hooks. Read them before enabling them — a hook runs shell commands on
your machine automatically, with no permission prompt (ECC-0041).

## prompt-coach

A `UserPromptSubmit` hook that flags a prompt likely to go wide and offers plan
mode when the work looks multi-file.

### Install standalone

Add to `.claude/settings.json` (project) or `~/.claude/settings.json` (user):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PROJECT_DIR}/hooks/prompt_coach.py\""
          }
        ]
      }
    ]
  }
}
```

Use an absolute path if the script lives outside the project. Confirm it
registered with `/hooks`.

### What it does

| Check | Fires when |
|---|---|
| Wide scope | A broad verb (`improve`, `clean up`, `refactor`, `optimise`…) with no file, symbol, error or backticked term to anchor on |
| Plan mode | Multi-file or architectural markers present **and** you are not already in plan mode |
| No verification target | A change request of 8+ words stating no expected outcome |
| Context size | Last reported context ≥250K tokens, read from the tail of the transcript |

Output goes to `systemMessage`, so you see it and Claude's context does not
change. At most two notes per prompt.

### What it does not do

**It cannot rewrite your prompt.** The `UserPromptSubmit` contract makes
`user_input` read-only — a hook may block the prompt, add context for Claude, or
show you a message, and nothing else. So it shows a suggestion rather than
silently editing what you typed.

**It never blocks.** It always exits 0. Blocking a prompt over its wording would
be a terrible trade; the worst case here is a line of text you ignore.

**It calls no model.** This runs on every prompt you ever type. An LLM here
would add latency and token cost to all of them, to produce advice that string
inspection mostly gets right. If you want model-graded prompt critique, run it
on demand as a skill, not on every keystroke of work.

### Why it is quiet

It says nothing for slash commands, continuations (`yes`, `go ahead`, `again`),
and anything under three words. It caps at two notes.

This is the whole design, not politeness. A hook that comments on every prompt
gets disabled within a day, and a disabled hook protects nothing. False
positives cost far more than misses here, so the patterns are deliberately
narrow — `fix the TypeError in src/auth.py line 42` is silent, because it is
already specific.

### Testing it

```bash
python hooks/prompt_coach.py --self-test
```

Twelve cases covering each check and each suppression. Add a case before
changing a pattern — the failure mode of this hook is becoming annoying, and the
test suite is what stops that happening quietly.

To try one prompt by hand:

```bash
echo '{"permission_mode":"default","transcript_path":"","user_input":"improve this codebase"}' \
  | python hooks/prompt_coach.py
```

### Tuning

`CONTEXT_WARN_TOKENS` (default 250,000) and `MAX_SUGGESTIONS` (default 2) are
module constants. The regexes are the real knobs; widen `ANCHOR` first if you
find it noisy, since most false positives are prompts that were specific in a
way the anchor pattern did not recognise.
