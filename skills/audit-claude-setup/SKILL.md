---
name: audit-claude-setup
description: Audit a repository's Claude Code setup against the ECC rule catalog and propose the missing artefacts. Use when someone asks whether their Claude Code setup is right, what they should add to a repo, how to set Claude Code up for a large or existing codebase, or asks for a CLAUDE.md / hooks / skills / permissions review.
---

# Audit a repo's Claude Code setup

Score the repo against `rules/`, then propose the specific artefacts it is
missing. Report findings; do not create files until the user picks.

## 1. Run the audit

```bash
python tools/audit.py --repo <path> [--team] --json <scratch>/ecc-audit.json
```

Add `--team` when more than one person uses Claude Code in this repo — it
activates the team-scoped rules. Exit code is 1 when a MUST rule fails, so the
same command works as a CI gate.

## 2. Read the verdicts properly

- `FAIL` — cite the rule id and its `failure_mode`. The failure mode says *why
  it bites in practice*; that is the part that persuades, not the requirement.
- `NOT_EVALUATED` — the check could not run, and says why. **Never present these
  as passing.** If the reason is "check not implemented", say the rule was not
  assessed and offer to write the check.
- `NOT_APPLICABLE` — do not mention unless asked.

The score deliberately excludes unevaluated rules. Quote it with the evaluated
count beside it, not alone.

## 3. Profile the repo before proposing

Read enough of the repo to make proposals concrete rather than generic:

- build/test/lint commands — from `package.json`, `pyproject.toml`, `Makefile`,
  CI workflow files
- the directory layout and where ownership boundaries actually fall
- existing `.claude/` contents
- whether generated code is tracked

Check `profiles/` for a preset matching the stack and start from it.

## 4. Propose artefacts, ranked

Give a short ranked list. For each: what it is, which rule it discharges, and
what it costs to adopt. Typical output —

| Artefact | Why |
|---|---|
| `CLAUDE.md` | ECC-0001; stop re-deriving the build and test commands every session |
| `.claude/settings.json` deny tier | ECC-0010; there is currently no statement of what must never happen |
| PostToolUse format/lint hook | ECC-0031; the "always run the formatter" line is a request, not a guarantee |
| `.claude/skills/<workflow>/` | ECC-0030; this procedure has been pasted repeatedly |

Rules to hold to when proposing:

- **Propose, then wait.** Writing eight config files unasked is how a setup
  becomes an unowned setup.
- **Do not propose an artefact the repo will not maintain.** One good CLAUDE.md
  beats four stale ones.
- A hook is right for anything deterministic; an instruction is right for
  judgement. Do not propose a hook for a thing that needs judgement.

## 5. If asked to apply

Create only what was accepted. Put project-scoped settings in the project's
`.claude/settings.json` and commit them — never in the user's global settings
(ECC-0012). Re-run the audit afterwards and show the delta.
