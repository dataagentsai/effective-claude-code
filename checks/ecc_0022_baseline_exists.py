"""ECC-0022 -- A usage baseline exists before any optimisation is claimed."""

import json
from datetime import datetime, timezone

from _framework import failed, passed

STALE_DAYS = 30


def run(ctx):
    evidence_dir = ctx.repo / "evidence"
    baselines = sorted(evidence_dir.glob("*baseline*.json")) if evidence_dir.is_dir() else []

    if not baselines:
        return failed(
            "No baseline found under evidence/. Any claim that a CLAUDE.md, permission or "
            "model change made things more efficient has nothing to be checked against.",
            [f"evidence/ present: {evidence_dir.is_dir()}", "files matching *baseline*.json: 0"],
        )

    newest = max(baselines, key=lambda p: p.stat().st_mtime)
    age_days = (datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime) / 86400

    try:
        payload = json.loads(newest.read_text(encoding="utf-8"))
        has_shape = isinstance(payload, dict) and bool(payload)
    except (OSError, json.JSONDecodeError):
        has_shape = False

    evidence = [
        f"newest baseline: evidence/{newest.name}",
        f"age: {age_days:.0f} day(s)",
        f"parses as JSON: {has_shape}",
    ]

    if not has_shape:
        return failed(f"{newest.name} exists but is not readable JSON.", evidence)

    if age_days > STALE_DAYS:
        return failed(
            f"The newest baseline is {age_days:.0f} days old (>{STALE_DAYS}). A baseline this "
            "stale predates whatever change is being evaluated against it.",
            evidence,
        )

    return passed("A recent baseline exists under evidence/.", evidence)
