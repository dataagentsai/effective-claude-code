"""ECC-0021 -- Transcript retention is set deliberately."""

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics" / "collectors"))

from _framework import failed, passed  # noqa: E402

DEFAULT_DAYS = 30


def run(ctx):
    value = ctx.setting("cleanupPeriodDays")
    from transcript_reader import find_sessions

    sessions = find_sessions()
    evidence = [f"{len(sessions)} transcripts on disk"]

    if value is None:
        return failed(
            f"cleanupPeriodDays is not set, so transcripts are deleted after the "
            f"{DEFAULT_DAYS}-day default. The loss is silent and unrecoverable -- "
            "this setting has to be changed before you need the history, not after.",
            evidence,
        )
    return passed(f"cleanupPeriodDays is set to {value}.", evidence)
