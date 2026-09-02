---
name: tune-permissions
description: Collapse an accreted Claude Code permission allowlist into a reviewable allow/ask/deny structure - deduplicating, folding entries into wildcards, and proposing a deny tier. Use when someone has hundreds of allow rules, gets too many permission prompts, wants to clean up settings.json, or asks how to configure Claude Code permissions safely.
---

# Tune a permission configuration

## Run the analysis

```bash
python tools/tune_permissions.py [--config-dir <path>] [--repo <path>] [--json <scratch>/perms.json]
```

It reports duplicates, entries shadowed by a broader wildcard, clusters that
could fold into one rule, and entries that are project-specific but sitting in
user-level settings.

## The reframe to lead with

An allowlist that has grown past a couple of hundred entries is not a strict
configuration — it is an unreviewed one. Every entry was added under time
pressure to stop a prompt, and none were ever removed. Making it *shorter* makes
it *safer*, because a list nobody reads permits whatever it happens to contain.

So the goal is not "fewer prompts". It is a configuration a person can read in
one sitting and correctly state what it permits.

## Propose three tiers

**deny** — first, and non-negotiable (ECC-0010). Credentials and key material,
history rewriting (`git push --force`, `git reset --hard`), anything that
publishes outward. A config with no deny tier states no policy.

**ask** — irreversible but legitimate. Pushing, deploying, deleting,
`git commit`. The prompt is the point here; do not fold these into allow to
reduce friction.

**allow** — read-only and trivially reversible operations, expressed as the
smallest set of wildcards that covers observed usage.

## Rules for folding

- Fold only within a tool and a stable prefix (`Bash(git status *)`, not
  `Bash(git *)` — that last one swallows `push --force`).
- Never widen across the ask/deny boundary to save an entry.
- Project-specific entries move to the project's `.claude/settings.json` and get
  committed (ECC-0012), rather than being folded into a user-level wildcard.
- Show the before/after count, and show which specific entries each proposed
  wildcard replaces. A fold the user cannot verify is a fold they should not
  accept.

## Applying

Show the proposed JSON and let the user approve it. Back up the existing
settings file first — it represents months of accumulated decisions, and some of
those entries are load-bearing in ways that are not obvious from reading them.
