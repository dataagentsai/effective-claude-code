"""ECC-0001 -- The repo has a CLAUDE.md."""

from _framework import failed, passed


def run(ctx):
    found = ctx.claude_md_files()
    if not found:
        return failed(
            "No CLAUDE.md at the repo root or in .claude/.",
            [f"searched {ctx.repo}"],
        )
    rels = [str(p.relative_to(ctx.repo)).replace("\\", "/") for p in found]
    return passed(f"{len(found)} CLAUDE.md file(s) present.", rels)
