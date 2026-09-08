"""ECC-0030 -- A repeated multi-step workflow is a skill, not a pasted prompt."""

import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "analytics" / "collectors"))

from _framework import failed, passed, skipped  # noqa: E402

REPEAT_THRESHOLD = 3
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip().lower())


def _prompt_text(message) -> str:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def run(ctx):
    from transcript_reader import find_sessions

    sessions = find_sessions(project=ctx.repo.name)
    if not sessions:
        return skipped(f"No local transcripts found for project '{ctx.repo.name}'.")

    counts: dict[str, int] = {}
    total_prompts = 0
    for path in sessions:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict) or rec.get("type") != "user" or not rec.get("promptSource"):
                    continue
                text = _normalize(_prompt_text(rec.get("message") or {}))
                if len(text) < 40:
                    continue  # too short to be a pasted procedure
                total_prompts += 1
                counts[text] = counts.get(text, 0) + 1

    repeated = sorted(((t, n) for t, n in counts.items() if n >= REPEAT_THRESHOLD), key=lambda p: -p[1])
    skills_dir = ctx.repo / ".claude" / "skills"
    has_skills = skills_dir.is_dir() and any(skills_dir.iterdir()) if skills_dir.is_dir() else False

    evidence = [
        f"{len(sessions)} transcript(s) scanned, {total_prompts} substantial prompts",
        f".claude/skills/ present with content: {has_skills}",
    ]
    evidence.extend(f"repeated {n}x: {t[:100]}" for t, n in repeated[:5])

    if not repeated:
        return passed("No prompt was pasted three or more times in the scanned transcripts.", evidence)

    if has_skills:
        return passed(
            f"{len(repeated)} prompt(s) repeat {REPEAT_THRESHOLD}+ times, but .claude/skills/ "
            "already exists -- confirm these are the ones it covers.",
            evidence,
        )

    return failed(
        f"{len(repeated)} prompt(s) were pasted {REPEAT_THRESHOLD}+ times with no .claude/skills/ "
        "to show for it. Each copy drifts from the others and nobody notices when one is fixed.",
        evidence,
    )
