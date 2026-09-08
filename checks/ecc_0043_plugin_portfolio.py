"""ECC-0043 -- The installed plugin set is reviewed for context cost and disuse."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics" / "collectors"))

from _framework import failed, na, passed, skipped  # noqa: E402

LOOKBACK_SESSIONS = 10


def _plugin_slug(key: str) -> str:
    return key.split("@", 1)[0].strip().lower()


def run(ctx):
    from transcript_reader import find_sessions

    enabled = {}
    for _, settings in ctx.all_settings:
        enabled.update(settings.get("enabledPlugins") or {})
    active = sorted({_plugin_slug(k) for k, v in enabled.items() if v})

    if not active:
        return na("No enabledPlugins configured in any settings file scanned.")

    sessions = find_sessions()[:LOOKBACK_SESSIONS]
    if not sessions:
        return skipped("No local transcripts found to check plugin usage against.")

    blobs = []
    for path in sessions:
        try:
            blobs.append(path.read_text(encoding="utf-8", errors="replace").lower())
        except OSError:
            continue

    unused = [p for p in active if not any(p in blob for blob in blobs)]

    evidence = [
        f"{len(active)} enabled plugin(s), checked against the {len(blobs)} most recent transcripts",
    ]
    if unused:
        evidence.append(f"no mention across those sessions: {unused}")

    if not unused:
        return passed("Every enabled plugin was referenced somewhere in recent sessions.", evidence)

    return failed(
        f"{len(unused)} of {len(active)} enabled plugin(s) do not appear anywhere in the "
        f"{len(blobs)} most recent sessions. Each still announces its tools and skills on every "
        "turn regardless of whether it is used -- this is a proxy for disuse, not proof; "
        "confirm in /plugin before disabling.",
        evidence,
    )
