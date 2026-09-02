# effective-claude-code

**The concrete half of working well with Claude Code.**

`engineering-canon` says *why*. This repo says *what to install, what to measure,
and what to fix* — as executable checks, shippable artefacts, and a curated index
of everything worth reusing.

It answers four questions for a real codebase:

| Question | Where |
|---|---|
| What Claude Code setup should *this* repo have? | `/audit-claude-setup` → `rules/` + `checks/` + `profiles/` |
| What is it costing me, and where is the waste? | `/analyze-claude-usage` → `analytics/` |
| How often is the model getting things wrong? | `/trace-hallucinations` → `analytics/metrics/` |
| Which community/official skills are worth using? | `registry/` |

---

## Install

The repo root *is* a Claude Code plugin, so it installs directly:

```
/plugin marketplace add dataagentsai/effective-claude-code
/plugin install effective-claude-code
```

Then, from inside any repo:

```
/audit-claude-setup            # score this repo's setup, propose the missing artefacts
/analyze-claude-usage          # token / cost / cache / waste report from local logs
/trace-hallucinations          # error-and-correction proxy signals
/tune-permissions              # collapse an accreted allowlist into allow/ask/deny
```

Everything runs **locally, stdlib-only, zero dependencies, no network**. The
analyzers read the transcripts already on your disk; nothing is uploaded.

---

## Layout

```
.claude-plugin/     plugin + marketplace manifests
skills/             the shippable skills (the four above)
commands/           thin /slash wrappers
agents/             subagent presets (large-codebase explorer, …)
hooks/              reference hooks — format / lint / test gates
rules/              NORMATIVE. One YAML per rule, ECC-nnnn, canon-shaped
checks/             executable counterpart, 1:1 with rules/
ontology/           activities · capabilities · failure modes, as a queryable graph
profiles/           per-stack presets (pyspark-databricks, nextjs, fastapi, …)
playbooks/          narrative: large-codebase, onboarding, multi-dev, cost-control
analytics/          collectors/ · metrics/ · reports/
registry/           pointers to external skills & plugins, with trust tiers
crosswalks/         ECC ↔ CANON ↔ AHC identifier joins
schema/             JSON Schema for rules, registry entries, metrics
evidence/           local baselines — gitignored, never committed
site/               rendered index.html (committed, CI-verified)
tools/              render / lint / CI
```

## How a rule works

Rules are normative and machine-readable; checks are their executable form. A
rule never restates a canon principle — it **discharges** one, the same way
`ai-harness-catalog` discharges `ai-assurance-catalog`.

```yaml
id: ECC-0010
level: MUST
area: PERM
title: Permission configuration has a deny tier
discharges: [CANON-SEC-002]
check: checks/ecc_0010_deny_tier.py
```

That makes an audit verdict explainable — "failed ECC-0010" with a cited
principle — instead of an opinion. It also means the catalog is already shaped
as input for an architecture-review agent rather than as prose.

Verdicts are `PASS` / `FAIL` / `NOT_APPLICABLE` / `NOT_EVALUATED`, and
`NOT_EVALUATED` always carries a reason. A check that cannot run says so; it
never silently passes.

## Repo family

| Repo | Asks |
|---|---|
| `ai-assurance-catalog` (AAC) | what must be **true** |
| `ai-harness-catalog` (AHC) | what must **exist** in a shipped AI system |
| `engineering-canon` (CANON) | **why** — principles, anti-patterns |
| **`effective-claude-code` (ECC)** | **how**, executable — the working setup |

## Status

Early. The rule set is seeded from real findings, and grows by the canon's rule:
a rule earns its place by having been violated at least once.

## Licence

Code under `LICENSE`. Specification content (`rules/`, `registry/`, `playbooks/`)
under `LICENSE-SPEC.txt`.
