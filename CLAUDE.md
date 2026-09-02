# effective-claude-code

Tooling that audits a repo's Claude Code setup and analyses usage from local
transcripts. See `README.md` for what lives where.

## Running things

```bash
python tools/audit.py --repo <path> [--team]     # exits 1 on a MUST failure
python tools/tune_permissions.py
python analytics/collectors/usage_report.py
python analytics/collectors/quality_signals.py
```

No build step and no install step. Python 3.9+.

## Hard constraints

**Standard library only.** Not a preference — this has to run on machines where
PyPI is unreachable and where `npm install` is not an option. If something needs
a dependency, it does not go in this repo. That is why `tools/minyaml.py` exists
instead of PyYAML.

**Nothing leaves the machine.** The analyzers read transcripts containing
prompts, file paths and client identifiers. No network calls, no uploads, no
telemetry of our own.

**`evidence/` is gitignored and stays that way.** It holds real audit output from
real repos. The repo is public.

## Conventions

- A rule is a YAML file in `rules/`, one per file, id `ECC-nnnn`, validated
  against `schema/rule.schema.json`. It states the requirement and the failure
  mode; it does not contain code.
- Its check is `checks/ecc_nnnn_<slug>.py` exposing `run(ctx) -> Verdict`.
- A check that cannot inspect what it needs returns `NOT_EVALUATED` **with a
  reason**. It never returns `PASS` for something it did not look at. This is the
  single most important invariant here — an audit that silently passes unchecked
  rules is worse than no audit, because it is believed.
- Rules cite canon principles via `discharges:`. They never restate one.
- `failure_mode` is written concretely — what actually goes wrong, in practice.
  It is the field people read and act on.

## Growth rule

A rule earns its place by having been violated at least once, in a real repo.
Seed from actual audit findings, not from what sounds prudent.
