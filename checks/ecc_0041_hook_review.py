"""ECC-0041 -- External hooks are read before they are enabled."""

import re

from _framework import failed, na, passed

NETWORK_PIPE = re.compile(
    r"\b(curl|wget|iwr|invoke-webrequest)\b.{0,200}\|\s*(sh|bash|zsh|python[23]?|pwsh|powershell)\b",
    re.IGNORECASE,
)
SCRIPT_REF = re.compile(r"([./$\w{}-]+\.(?:py|sh|js|mjs|cjs|ps1))\b")
VAR_PREFIX = re.compile(r"^\$\{CLAUDE_(?:PROJECT_DIR|PLUGIN_ROOT)\}/?")


def _flatten(settings) -> list[str]:
    commands = []
    for _matcher_groups in (settings.get("hooks") or {}).values():
        for group in _matcher_groups or []:
            for h in group.get("hooks") or []:
                if h.get("type") == "command" and h.get("command"):
                    commands.append(str(h["command"]))
    return commands


def run(ctx):
    project_commands = _flatten(ctx.project_settings) + _flatten(ctx.project_settings_local)
    if not project_commands:
        return na("No hooks configured in project settings.")

    flagged = []
    for cmd in project_commands:
        if NETWORK_PIPE.search(cmd):
            flagged.append(f"fetches and pipes to an interpreter: {cmd[:120]}")
            continue
        m = SCRIPT_REF.search(cmd)
        if not m:
            continue
        ref = VAR_PREFIX.sub("", m.group(1)).lstrip("./")
        if not any(f == ref or f.endswith("/" + ref) for f in ctx.tracked_files):
            flagged.append(f"references a script not tracked in this repo: {cmd[:120]}")

    evidence = [f"{len(project_commands)} project hook command(s) found"]
    evidence.extend(flagged[:6])

    if flagged:
        return failed(
            f"{len(flagged)} of {len(project_commands)} project hook command(s) either pipe a "
            "download into an interpreter or point at a script this repo does not carry, so "
            "there is nothing here to have read.",
            evidence,
        )
    return passed("All project hook commands run a vendored, in-repo script.", evidence)
