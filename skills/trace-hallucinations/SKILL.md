---
name: trace-hallucinations
description: Extract hallucination-proxy signals from Claude Code transcripts - invented file paths, failed edit matches, refusals and user-correction turns - and report them as a trend. Use when someone asks how often Claude gets things wrong, wants to track output quality or error rate, suspects the model is fabricating, or wants to compare quality before and after a setup change.
---

# Trace hallucination-proxy signals

## State the caveat first, every time

Nothing in a transcript records whether the model was right. There is no
ground-truth signal. This measures **proxies** — events more common when the
model is fabricating than when it is not — and every one has innocent
explanations.

Never report the output as a hallucination rate. Report it as a set of signals
worth investigating. If the user asks for a hallucination percentage, explain
why that number does not exist in this data rather than producing one.

## Run it

```bash
python analytics/collectors/quality_signals.py [--project <substr>] [--json <scratch>/quality.json]
```

## The signals, strongest first

| Signal | What it suggests | Innocent explanation |
|---|---|---|
| `invented_path` | A path was produced from pattern, not from looking | Genuine exploration of a repo the agent is new to |
| `edit_mismatch` | Code was reconstructed from memory inaccurately | The file changed underneath between read and edit |
| `correction_turn` | A human rejected the previous turn | The user changed their mind |
| `refusal` | `stop_reason: refusal` | A genuinely out-of-scope request |
| `unread_edit` | Edit attempted before reading | Ordinary tool sequencing slip |
| `rework_loop` | Re-read its own edit immediately | Diligent verification |

The index is weighted and normalised per 100 API calls so sessions of different
lengths compare. It has no absolute meaning — only a relative one.

## How to use the output

1. **Trend, never a single session.** One elevated session is noise. Compare
   across weeks, or before and after a CLAUDE.md or model change.
2. **Use the worst-sessions table as a reading list.** The value is that it
   points at transcripts to actually open, not that it produces a number.
3. **Look for a cause in the setup.** A high `invented_path` count often traces
   to a missing or wrong CLAUDE.md (ECC-0001) or to generated directories
   polluting search (ECC-0003) — the model is guessing because looking is
   expensive or misleading.

## Recording it

Store the JSON summary under `evidence/` to build the trend (ECC-0050). Never
commit raw transcripts — they contain prompts, paths and client identifiers.
