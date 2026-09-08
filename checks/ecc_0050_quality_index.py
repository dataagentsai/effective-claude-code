"""ECC-0050 -- A hallucination-proxy index is tracked over time."""

import json
from datetime import datetime, timezone

from _framework import failed, passed

STALE_DAYS = 30
MIN_SNAPSHOTS = 2


def run(ctx):
    evidence_dir = ctx.repo / "evidence"
    snapshots = sorted(evidence_dir.glob("*quality*.json")) if evidence_dir.is_dir() else []

    evidence = [f"evidence/ present: {evidence_dir.is_dir()}", f"quality snapshots found: {len(snapshots)}"]

    if not snapshots:
        return failed(
            "No quality-index snapshot under evidence/. The proxy signals sitting in transcripts "
            "-- invented paths, edit mismatches, refusals, corrections -- are never being read.",
            evidence,
        )

    readable = []
    for path in snapshots:
        try:
            json.loads(path.read_text(encoding="utf-8"))
            readable.append(path)
        except (OSError, json.JSONDecodeError):
            continue

    if len(readable) < MIN_SNAPSHOTS:
        return failed(
            f"Only {len(readable)} readable quality snapshot(s) under evidence/. A single "
            "snapshot is an incident, not a trend -- run /trace-hallucinations again after "
            "the next batch of sessions and commit it alongside the last one.",
            evidence,
        )

    newest = max(readable, key=lambda p: p.stat().st_mtime)
    age_days = (datetime.now(timezone.utc).timestamp() - newest.stat().st_mtime) / 86400
    evidence.append(f"newest: evidence/{newest.name}, {age_days:.0f} day(s) old")

    if age_days > STALE_DAYS:
        return failed(
            f"The newest quality snapshot is {age_days:.0f} days old (>{STALE_DAYS}). The trend "
            "has gone cold.",
            evidence,
        )

    return passed(f"{len(readable)} quality snapshots under evidence/, most recent {age_days:.0f} day(s) old.", evidence)
