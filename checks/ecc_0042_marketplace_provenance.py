"""ECC-0042 -- Third-party plugins come from a screened, pinned marketplace."""

from _framework import failed, na, passed
from minyaml import MinYamlError, load_file

SCREENED = {"claude-plugins-official", "claude-community"}


def run(ctx):
    enabled = {}
    marketplaces = {}
    for _, settings in ctx.all_settings:
        enabled.update(settings.get("enabledPlugins") or {})
        marketplaces.update(settings.get("extraKnownMarketplaces") or {})

    active = [k for k, v in enabled.items() if v]
    if not active:
        return na("No enabledPlugins configured in any settings file scanned.")

    outside = []
    for key in active:
        if "@" not in key:
            continue  # bare name: the default/official marketplace
        _name, _, market = key.partition("@")
        if market not in SCREENED:
            outside.append((key, market))

    registry_dir = ctx.repo / "registry"
    entries = []
    for path in sorted(registry_dir.glob("*.yaml")) if registry_dir.is_dir() else []:
        try:
            entries.append(load_file(path))
        except MinYamlError:
            continue
    registry_names = {str(e.get("name", "")).strip().lower() for e in entries}

    unrecorded = []
    for key, market in outside:
        plugin_name = key.split("@", 1)[0].strip().lower()
        if plugin_name not in registry_names:
            unrecorded.append((key, market))

    evidence = [
        f"{len(active)} enabled plugin(s), {len(marketplaces)} extra marketplace(s) configured",
    ]
    if outside:
        evidence.extend(f"{k}  (marketplace: {m})" for k, m in outside[:8])

    if not outside:
        return passed("Every enabled plugin comes from the official or community marketplace.", evidence)

    if unrecorded:
        return failed(
            f"{len(unrecorded)} of {len(outside)} plugin(s) outside the official/community "
            "marketplaces have no registry entry recording the commit they were reviewed at.",
            evidence,
        )

    return passed(
        f"{len(outside)} plugin(s) come from outside the screened marketplaces, but each has a "
        "registry entry.",
        evidence,
    )
