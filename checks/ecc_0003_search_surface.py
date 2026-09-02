"""ECC-0003 -- Generated and vendored directories are excluded from search."""

from _framework import failed, na, passed

NOISE_DIRS = (
    "node_modules/", "dist/", "build/", "target/", "vendor/", ".next/",
    "__pycache__/", ".venv/", "venv/", "coverage/", "site-packages/",
)
NOISE_FILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock")


def run(ctx):
    if not ctx.is_large:
        return na(f"{ctx.file_count} files; rule applies to large repos (>=1000 files).")

    gitignore = ctx.repo / ".gitignore"
    ignored = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.is_file() else ""

    unignored = [
        d for d in NOISE_DIRS
        if any(f.startswith(d) or f"/{d}" in f for f in ctx.tracked_files)
        and d.rstrip("/") not in ignored
    ]
    big_locks = [f for f in ctx.tracked_files if f.rsplit("/", 1)[-1] in NOISE_FILES]

    evidence = [f"{ctx.file_count:,} files walked"]
    if unignored:
        evidence.append(f"generated dirs present and not gitignored: {unignored}")
    if big_locks:
        evidence.append(f"lockfiles tracked: {big_locks[:5]}")

    if unignored:
        return failed(
            f"{len(unignored)} generated/vendored director(ies) are in the search surface. "
            "Searches return hits from them, and edits to a vendored copy vanish on the "
            "next build.",
            evidence,
        )
    return passed("Generated and vendored paths are excluded.", evidence)
