"""ECC-0040 -- Third-party skills and plugins carry a trust tier and a review date."""

from datetime import date

from _framework import failed, passed
from minyaml import MinYamlError, load_file

STALE_DAYS = 365


def _plugin_base_name(key: str) -> str:
    return key.split("@", 1)[0].strip().lower()


def run(ctx):
    enabled = {}
    for _, settings in ctx.all_settings:
        enabled.update(settings.get("enabledPlugins") or {})
    active_plugins = sorted(_plugin_base_name(k) for k, v in enabled.items() if v)

    registry_dir = ctx.repo / "registry"
    entries = []
    for path in sorted(registry_dir.glob("*.yaml")) if registry_dir.is_dir() else []:
        try:
            entries.append(load_file(path))
        except MinYamlError:
            continue

    known_names = {str(e.get("name", "")).strip().lower() for e in entries if e.get("name")}
    uncovered = [p for p in active_plugins if p and p not in known_names]

    today = date.today()
    stale = []
    for e in entries:
        if e.get("trust") != "vetted":
            continue
        reviewed = str(e.get("last_reviewed") or "")
        try:
            age = (today - date.fromisoformat(reviewed)).days
        except ValueError:
            stale.append(f"{e.get('id', '?')}: last_reviewed missing or unparseable ({reviewed!r})")
            continue
        if age > STALE_DAYS:
            stale.append(f"{e.get('id', '?')}: last reviewed {age} days ago")

    evidence = [
        f"enabledPlugins entries found: {len(enabled)} ({len(active_plugins)} active)",
        f"registry entries: {len(entries)}",
    ]
    if uncovered:
        evidence.append(f"active plugins with no registry entry: {uncovered}")
    if stale:
        evidence.extend(stale[:6])

    if not enabled:
        evidence.append("no enabledPlugins block in any settings file scanned -- plugin coverage not checked")

    if uncovered or stale:
        problems = []
        if uncovered:
            problems.append(f"{len(uncovered)} active plugin(s) have no registry entry")
        if stale:
            problems.append(f"{len(stale)} vetted registry entr(y/ies) are stale or undated")
        return failed(
            "; ".join(problems) + ". An installed skill or plugin with no recorded source, "
            "trust tier and review date is a supply-chain decision nobody can see.",
            evidence,
        )

    return passed("Every active plugin has a registry entry and vetted entries are current.", evidence)
