---
name: analyze-claude-usage
description: Report Claude Code token consumption, cache efficiency, session duration and tool mix from local transcripts, and identify where the spend actually goes. Use when someone asks what Claude Code is costing, how to reduce token usage or spend, whether their usage is efficient, or wants a usage baseline before or after a change.
---

# Analyze Claude Code usage

Reads the JSONL transcripts already on the machine. Local, stdlib-only, no
network — the data never leaves.

## Run it

```bash
python analytics/collectors/usage_report.py [--project <substr>] [--json <scratch>/usage.json]
```

`--project` filters on the slugified working-directory name, so pass a fragment
of the repo path to scope to one codebase.

## Interpret it — this is most of the job

The report is easy to run and easy to misread. Lead with these:

**Mean context per call is usually the answer.** It is the conversation being
re-sent on every turn. It only grows within a session, and in an agentic
workflow it typically dwarfs output tokens. If someone wants to cut spend and is
trimming their prompts, they are optimising the smallest line item.

**Cache read:write ratio is the health signal.** High is good — the cache is
being reused. Below roughly 5:1 means sessions are being restarted or
invalidated often enough that cache writes are not paying for themselves.
A high ratio is not a problem to fix; say so plainly rather than manufacturing
a recommendation.

**API calls per prompt** is agentic loop depth. High is not inherently bad — it
is what the tool does — but a sharp rise between periods is worth a look.

**Tool mix** shows where the turns go. A Bash-dominated mix in a repo with no
hooks often means work that should have been a hook is being done by hand each
time (ECC-0031).

## Baselines

If the user is about to change something for efficiency, capture the baseline
first (ECC-0022) and store the JSON summary — never raw transcripts — under
`evidence/`. Re-run afterwards and compare. Without a before, no claim about the
after can be checked.

## On cost figures

The tool reports tokens and applies a price table only via `--prices`. Do not
substitute remembered rates: they differ by plan, model and tier, and change.
If the user wants dollars, ask them for their rate card or point them at
`ccusage` (see `registry/`), which maintains one.

## Limits worth stating

- Transcripts expire — 30 days by default (ECC-0021). Anything older is gone.
- There is **no timing data here**. Turn duration and time-to-first-token exist
  only in OpenTelemetry (`interaction.duration_ms`, `ttft_ms`); see ECC-0020.
- This machine's transcripts only. Team-wide numbers need OTel or the analytics
  dashboard.
