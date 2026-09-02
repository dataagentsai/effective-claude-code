"""ECC-0002 -- CLAUDE.md stays inside a size budget."""

from _framework import failed, passed, skipped

MAX_BYTES = 12 * 1024
MAX_LINES = 300


def run(ctx):
    files = ctx.claude_md_files()
    if not files:
        return skipped("No CLAUDE.md to measure; ECC-0001 covers its absence.")

    oversized, evidence = [], []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return skipped(f"Could not read {path}: {exc}")
        size, lines = len(text.encode("utf-8")), text.count("\n") + 1
        rel = str(path.relative_to(ctx.repo)).replace("\\", "/")
        evidence.append(f"{rel}: {size:,} bytes, {lines} lines")
        if size > MAX_BYTES or lines > MAX_LINES:
            oversized.append(rel)

    if oversized:
        return failed(
            f"{len(oversized)} file(s) over budget ({MAX_BYTES // 1024} KB / {MAX_LINES} lines). "
            "This is prepended to every request in every session.",
            evidence,
        )
    return passed("All CLAUDE.md files within budget.", evidence)
