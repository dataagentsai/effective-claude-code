# Ontology

A small typed graph of what a Claude Code setup is made of, so that "what should
we have?" is a query rather than an opinion.

The point is not taxonomy for its own sake. The graph exists so that
`tools/coverage.py` can walk it and produce the gap list mechanically — per
activity, which capabilities are needed, which artefact supplies each one, where
that artefact comes from, and whether we actually have it.

## Entities

| Type | Id | Is | Lives in |
|---|---|---|---|
| **Activity** | `ACT-nn` | What a person is doing — coding, testing, debugging, troubleshooting | `activities.yaml` |
| **Capability** | `CAP-nnn` | Something the setup can *do*, stated independently of what supplies it | `capabilities.yaml` |
| **Artefact** | — | The installable thing that supplies it: skill, hook, MCP server, LSP server, plugin, monitor, settings | `kind:` on a capability |
| **Source** | — | Where the artefact comes from: `anthropic-official`, `claude-community`, `third-party`, `own` | `source:` on a capability |
| **FailureMode** | `FM-nn` | What goes wrong when a capability is missing | `failure_modes.yaml` |
| **Signal** | — | The observable that detects a failure mode | `detected_by:` |
| **Control** | `ECC-nnnn` | The rule that mitigates it | `mitigated_by:` |

## Relations

```
Activity  --needs-->        Capability
Capability --realized_by--> Artefact  --supplied_by--> Source
Activity  --exhibits-->     FailureMode
FailureMode --detected_by-> Signal    --derived_from-> Substrate
FailureMode --mitigated_by-> Control  --enforced_by--> Artefact
Control (rule) --discharges-> CanonPrinciple
```

Two traversals do the useful work:

**Coverage.** `Activity → needs → Capability → status` yields what is missing for
the way people actually work. Run `python tools/coverage.py`.

**Diagnosis.** `Signal → detects → FailureMode → mitigated_by → Control` turns a
number from the analyzers into a specific thing to change. A rising
`invented_path` count is not a vague quality concern — it points at `FM-01`,
which names three controls, one of which is installing a language server.

## The build-versus-reuse line

Every capability carries a `source`, and the split is deliberate rather than
case-by-case:

- **`anthropic-official` / `claude-community` — anything that crosses a tool
  boundary.** Language servers, MCP integrations to GitHub, Sentry, Linear,
  Figma. These are maintained against APIs that change, and rebuilding them is
  pure liability. The official marketplace is auto-registered; there is rarely a
  reason to hand-roll one of these.
- **`own` — anything about whether *our* setup is correct and measurable.** The
  audit, the analytics, the quality proxies, the stack profiles, the governance
  rules. Nobody else has an incentive to build these, and they are inherently
  organisation-specific.

Stated shortly: **reuse capability, build governance.** A capability marked
`own` that could plausibly be reused is a bug in this file, and a capability
marked reusable that we have quietly reimplemented is worse.

## Status values

| Status | Meaning |
|---|---|
| `built` | Exists and is verified |
| `partial` | Exists but incomplete — the note says how |
| `gap` | Identified, not built |
| `install` | Supplied by someone else; the work is deciding to install it, not writing it |
