"""ECC-0051 -- Sessions have a context-reset discipline."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics" / "collectors"))

from _framework import failed, passed, skipped  # noqa: E402

MARATHON_MINUTES = 240
MARATHON_CALLS = 200
MIN_SESSIONS = 3
CLIMB_RATIO = 1.5


def run(ctx):
    from transcript_reader import read_all

    sessions = [s for s in read_all(project=ctx.repo.name, limit=20) if s.api_calls]
    if len(sessions) < MIN_SESSIONS:
        return skipped(
            f"Only {len(sessions)} session(s) with activity found for '{ctx.repo.name}' -- too "
            "few to see a duration or context-growth pattern."
        )

    marathons = [s for s in sessions if s.duration_minutes > MARATHON_MINUTES or s.api_calls > MARATHON_CALLS]

    chrono = sorted(sessions, key=lambda s: s.started or s.path.stat().st_mtime)
    mid = len(chrono) // 2
    first_half = chrono[:mid] or chrono[:1]
    second_half = chrono[mid:]
    first_mean = sum(s.mean_context_per_call for s in first_half) / len(first_half)
    second_mean = sum(s.mean_context_per_call for s in second_half) / len(second_half)
    climbing = first_mean > 0 and second_mean / first_mean >= CLIMB_RATIO

    evidence = [
        f"{len(sessions)} session(s) with activity",
        f"marathon session(s) (>{MARATHON_MINUTES}min or >{MARATHON_CALLS} calls): {len(marathons)}",
        f"mean context/call: {first_mean:,.0f} (earlier half) -> {second_mean:,.0f} (later half)",
    ]

    if marathons or climbing:
        reasons = []
        if marathons:
            reasons.append(f"{len(marathons)} session(s) ran past {MARATHON_MINUTES} minutes or {MARATHON_CALLS} calls")
        if climbing:
            reasons.append("mean context per call is climbing across recent sessions")
        return failed(
            "; ".join(reasons) + " -- consistent with sessions running until abandoned rather "
            "than being cleared at a deliberate point.",
            evidence,
        )

    return passed("No marathon sessions and mean context per call is not climbing across sessions.", evidence)
