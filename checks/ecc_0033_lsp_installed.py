"""ECC-0033 -- A language server is installed for the repo's primary language."""

import shutil

from _framework import na, failed, passed

# extension -> (language label, official plugin name, PATH binary we can confidently check for)
EXT_MAP = {
    ".py": ("python", "pyright", "pyright"),
    ".go": ("go", "gopls", "gopls"),
    ".rs": ("rust", "rust-analyzer", "rust-analyzer"),
    ".ts": ("typescript", "typescript", "typescript-language-server"),
    ".tsx": ("typescript", "typescript", "typescript-language-server"),
    ".java": ("java", "jdtls", None),
    ".cs": ("csharp", "csharp-ls", None),
    ".kt": ("kotlin", "kotlin", None),
    ".lua": ("lua", "lua", None),
    ".php": ("php", "php", None),
    ".swift": ("swift", "swift", None),
    ".c": ("c", "clangd", "clangd"),
    ".cpp": ("cpp", "clangd", "clangd"),
    ".h": ("c", "clangd", "clangd"),
    ".hpp": ("cpp", "clangd", "clangd"),
}
MIN_FILES = 20


def _plugin_slug(key: str) -> str:
    return key.split("@", 1)[0].strip().lower()


def run(ctx):
    counts: dict[str, int] = {}
    for f in ctx.tracked_files:
        for ext, (lang, _plugin, _bin) in EXT_MAP.items():
            if f.endswith(ext):
                counts[lang] = counts.get(lang, 0) + 1
                break

    if not counts:
        return na("No source files in a language with an official language-server plugin.")

    dominant = max(counts, key=counts.get)
    if counts[dominant] < MIN_FILES:
        return na(f"Only {counts[dominant]} {dominant} file(s) -- too few to call it the primary language.")

    plugin_name, path_binary = next(
        (p, b) for _e, (lang, p, b) in EXT_MAP.items() if lang == dominant
    )

    enabled = {}
    for _, settings in ctx.all_settings:
        enabled.update(settings.get("enabledPlugins") or {})
    active = {_plugin_slug(k) for k, v in enabled.items() if v}
    has_plugin = plugin_name in active

    evidence = [
        f"dominant language: {dominant} ({counts[dominant]} files)",
        f"expected plugin: {plugin_name}",
        f"enabled: {has_plugin}",
    ]

    if not has_plugin:
        return failed(
            f"{counts[dominant]} {dominant} file(s) and no '{plugin_name}' language-server plugin "
            "enabled. Navigation falls back to grep and validation to a full build.",
            evidence,
        )

    if path_binary:
        on_path = shutil.which(path_binary) is not None
        evidence.append(f"'{path_binary}' on PATH: {on_path}")
        if not on_path:
            return failed(
                f"The '{plugin_name}' plugin is enabled but '{path_binary}' does not resolve on "
                "PATH -- the plugin configures the connection but does not install the binary.",
                evidence,
            )

    return passed(f"The '{plugin_name}' language-server plugin is enabled for the dominant language.", evidence)
