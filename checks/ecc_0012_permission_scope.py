"""ECC-0012 -- Project-scoped permissions live in project settings."""

import re

from _framework import failed, na, passed

# An entry naming a concrete path or a project-specific script is not universal.
SPECIFIC = re.compile(r"(/[a-z0-9_.-]+){2,}|[A-Za-z]:\\\\|\./|scripts/|\.py\b|\.sh\b|\.ps1\b")


def run(ctx):
    user_rules = [
        r
        for label, r in ctx.permission_rules("allow")
        if label.startswith("user")
    ]
    if not user_rules:
        return na("No user-level allow rules.")

    specific = [str(r) for r in user_rules if SPECIFIC.search(str(r))]
    has_project_settings = bool(ctx.project_settings or ctx.project_settings_local)

    evidence = [
        f"{len(user_rules)} user-level allow rules, {len(specific)} name a specific path or script",
        f"project .claude/settings.json present: {has_project_settings}",
    ]
    if specific:
        evidence.extend(specific[:6])

    if len(specific) > 10:
        return failed(
            f"{len(specific)} user-level rules are project-specific. They follow you into "
            "every other project, and the team that owns this one cannot review them.",
            evidence,
        )
    return passed("User-level permissions are broadly scoped.", evidence)
