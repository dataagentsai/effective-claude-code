"""ECC-0011 -- The allowlist is free of duplicates and shadowed rules."""

from collections import Counter

from _framework import failed, passed

REVIEWABLE_MAX = 120


def _shadows(broad: str, narrow: str) -> bool:
    """True if `broad` already permits everything `narrow` does."""
    if broad == narrow or not broad.endswith("*"):
        return False
    return narrow.startswith(broad[:-1])


def run(ctx):
    entries = ctx.permission_rules("allow")
    if not entries:
        return passed("No allow rules to audit.")

    rules = [str(r) for _, r in entries]
    counts = Counter(rules)
    dupes = {r: n for r, n in counts.items() if n > 1}

    unique = sorted(set(rules))
    shadowed = [
        (broad, narrow)
        for broad in unique
        if broad.endswith("*")
        for narrow in unique
        if _shadows(broad, narrow)
    ]

    evidence = [f"{len(rules)} allow rules, {len(unique)} unique"]
    if dupes:
        evidence.append(f"duplicates: {list(dupes)[:6]}")
    if shadowed:
        evidence.append(f"shadowed: {[f'{b} covers {n}' for b, n in shadowed[:6]]}")

    problems = []
    if dupes:
        problems.append(f"{sum(dupes.values()) - len(dupes)} duplicate entries")
    if shadowed:
        problems.append(f"{len(shadowed)} entries shadowed by a wildcard")
    if len(rules) > REVIEWABLE_MAX:
        problems.append(
            f"{len(rules)} entries is past the point anyone reviews it "
            f"(threshold {REVIEWABLE_MAX})"
        )

    if problems:
        return failed("; ".join(problems) + ".", evidence)
    return passed("Allowlist is compact and free of duplicates.", evidence)
