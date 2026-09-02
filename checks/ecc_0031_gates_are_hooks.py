"""ECC-0031 -- Deterministic gates are hooks, not instructions."""

import re

from _framework import failed, na, passed

# "always run X", "never commit without Y" -- an imperative naming a command.
IMPERATIVE = re.compile(
    r"^\s*[-*>#\s]*(?:you\s+)?(?:must\s+)?(always|never|make sure to|be sure to|remember to)\b.{0,120}",
    re.IGNORECASE,
)
COMMANDISH = re.compile(
    r"\b(npm|pnpm|yarn|make|pytest|ruff|black|prettier|eslint|mypy|cargo|go test|gradle|mvn|tox|"
    r"format|lint|typecheck|run the tests?)\b",
    re.IGNORECASE,
)


def run(ctx):
    files = ctx.claude_md_files()
    if not files:
        return na("No CLAUDE.md, so no instructions to compare against hooks.")

    candidates = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = str(path.relative_to(ctx.repo)).replace("\\", "/")
        for n, line in enumerate(lines, 1):
            if IMPERATIVE.match(line) and COMMANDISH.search(line):
                candidates.append(f"{rel}:{n}  {line.strip()[:100]}")

    hooks_configured = any(s.get("hooks") for _, s in ctx.all_settings)
    hook_files = [f for f in ctx.tracked_files if f.startswith(".claude/hooks/")]
    evidence = [f"hooks block configured: {hooks_configured}", f"hook scripts in repo: {len(hook_files)}"]

    if not candidates:
        return passed("No enforceable instructions found sitting in CLAUDE.md.", evidence)

    if hooks_configured:
        return passed(
            f"{len(candidates)} imperative instruction(s) found, but hooks are configured "
            "-- confirm the hooks cover them.",
            evidence + candidates[:6],
        )

    return failed(
        f"{len(candidates)} instruction(s) in CLAUDE.md name a command and demand it "
        "always/never happen, with no hooks configured. An instruction is followed most "
        "of the time, which is the failure rate that misleads.",
        evidence + candidates[:8],
    )
