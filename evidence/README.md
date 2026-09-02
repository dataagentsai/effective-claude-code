# evidence/

Audit and usage output from real repositories, kept locally to build a trend.

**Everything in here except this file is gitignored, and it must stay that way.**
This repository is public. Audit reports carry absolute file paths, repository
and client names, permission rules quoting internal hostnames, and — in quality
reports — excerpts of prompts and tool output.

## What to keep

Store the **JSON summaries** the tools emit, not raw transcripts:

```bash
python tools/audit.py --repo <path> --json evidence/<repo>-audit-YYYY-MM-DD.json
python analytics/collectors/usage_report.py --json evidence/usage-YYYY-MM-DD.json
python analytics/collectors/quality_signals.py --json evidence/quality-YYYY-MM-DD.json
```

Date-stamp them. The point of this directory is comparison over time (ECC-0022,
ECC-0050) — a single snapshot answers nothing.

## Before sharing anything from here

Scrub paths, repo names and prompt excerpts by hand. There is no automated
redaction, and there will not be one — an automatic scrubber that misses a field
is more dangerous than no scrubber, because it is trusted.
