"""ECC-0010 -- Permission configuration has a deny tier."""

from _framework import failed, passed

SENSITIVE = ("env", "credential", "secret", "force", "reset --hard", ".pem", ".key", "id_rsa")


def run(ctx):
    allow = ctx.permission_rules("allow")
    ask = ctx.permission_rules("ask")
    deny = ctx.permission_rules("deny")

    evidence = [f"allow={len(allow)}  ask={len(ask)}  deny={len(deny)}"]

    if not deny:
        return failed(
            f"{len(allow)} allow rules and no deny rules. The configuration records "
            "what was convenient, and states nothing about what must never happen.",
            evidence,
        )

    covered = [r for _, r in deny if any(s in str(r).lower() for s in SENSITIVE)]
    if not covered:
        return failed(
            "Deny rules exist but none cover credentials, key material or "
            "history-rewriting git operations.",
            evidence + [f"deny rules: {[r for _, r in deny][:10]}"],
        )
    return passed(f"{len(deny)} deny rules, {len(covered)} covering sensitive targets.", evidence)
