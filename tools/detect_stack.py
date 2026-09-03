"""Detect a repo's real toolchain and draft the lint hooks it can actually run.

    python tools/detect_stack.py --repo C:\\src\\thing
    python tools/detect_stack.py --repo . --json stack.json

This is the detector that replaced a per-stack preset library. A preset is a
guess about a repo it has not read; the repo's own manifests are ground truth.
The difference is not academic -- a "Next.js profile" presuming `npm test` and
`npm run lint` emits hooks that fail in any repo that declares neither, which is
common, and a hook that fails silently gets disabled along with the ones that
worked.

So this proposes only what the repo declares, and where nothing is declared it
says so instead of inventing a plausible command.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from minyaml import load_all_file, MinYamlError  # noqa: E402

EXT_LANG = {
    ".py": "python", ".pyi": "python",
    ".ts": "nextjs", ".tsx": "nextjs", ".js": "nextjs", ".jsx": "nextjs", ".mjs": "nextjs",
    ".sql": "sql",
    ".scss": "nextjs", ".css": "nextjs",
}
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".next", "site-packages", ".mypy_cache", ".ruff_cache", "coverage",
}
SCRIPT_KEYS = ("lint", "format", "typecheck", "type-check", "check", "test")

SPARK_IMPORT = re.compile(
    r"^\s*(from|import)\s+pyspark\b|SparkSession\s*\.\s*builder|"
    r"^\s*from\s+databricks\b",
    re.M,
)


def walk(repo: pathlib.Path):
    langs, spark, files = {}, False, 0
    for path in repo.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        files += 1
        lang = EXT_LANG.get(path.suffix.lower())
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
        if not spark and path.suffix.lower() in (".py", ".sql") and files < 4000:
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            # Require an actual import, not a mention. Matching the bare string
            # "pyspark" reports this very repo as a Spark codebase, because its
            # linter registry and detector both name the framework in prose.
            if SPARK_IMPORT.search(head):
                spark = True
    if spark:
        langs["pyspark"] = langs.get("python", 0)
    return langs, files


def _candidates(repo: pathlib.Path, name: str):
    """Root first, then one level down.

    A monorepo puts the web app in ui/ or apps/web/ and its tsconfig.json with
    it. Checking only the root reports TypeScript as unconfigured in exactly the
    layouts where it is most certainly configured.
    """
    yield repo / name
    for child in repo.iterdir():
        if child.is_dir() and child.name not in SKIP_DIRS:
            yield child / name


def declared(repo: pathlib.Path, token: str) -> bool:
    """Resolve one `detect` entry: a filename, or filename:key."""
    name, _, key = token.partition(":")
    try:
        path = next((p for p in _candidates(repo, name) if p.is_file()), None)
    except OSError:
        return False
    if path is None:
        return False
    if not key:
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return key in text
        node = data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return True
    # TOML / INI: look for the section header.
    return f"[{key}]" in text or f"[{key}." in text


def package_scripts(repo: pathlib.Path) -> dict:
    """The repo's own declared commands. These outrank anything generic."""
    out = {}
    for pkg in list(repo.glob("package.json")) + list(repo.glob("*/package.json")):
        if any(p in SKIP_DIRS for p in pkg.parts):
            continue
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        scripts = data.get("scripts") or {}
        rel = str(pkg.parent.relative_to(repo)).replace("\\", "/")
        for key in SCRIPT_KEYS:
            if key in scripts:
                out[f"{rel}:{key}" if rel != "." else key] = scripts[key]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", metavar="PATH")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    try:
        linters = load_all_file(ROOT / "profiles" / "linters.yaml")
    except MinYamlError as exc:
        print(f"profiles/linters.yaml is malformed: {exc}", file=sys.stderr)
        return 2

    langs, files = walk(repo)
    scripts = package_scripts(repo)

    configured, missing = [], []
    for lint in linters:
        if lint.get("command", "").startswith("--"):
            continue  # documentation-only entries
        relevant = lint["lang"] == "any" or lint["lang"] in langs
        if not relevant:
            continue
        if any(declared(repo, tok) for tok in (lint.get("detect") or [])):
            configured.append(lint)
        else:
            missing.append(lint)

    print(f"\n  STACK  {repo}")
    print(f"  {files:,} files   " + "  ".join(f"{k} {v}" for k, v in sorted(langs.items(), key=lambda kv: -kv[1])))

    if scripts:
        print("\n  DECLARED BY THE REPO  (ground truth -- prefer these)\n")
        for key, cmd in scripts.items():
            print(f"    {key:<24} {cmd[:70]}")
    else:
        print("\n  No lint/format/test scripts declared in any package.json.")

    print("\n  CONFIGURED LINTERS\n")
    if configured:
        for lint in configured:
            fix = f"   fix: {lint['fix_command']}" if lint.get("fix_command") else ""
            print(f"    [{lint['speed']:<4}] {lint['name']:<28} {lint['command']}{fix}")
    else:
        print("    none detected")

    fast = [l for l in configured if l.get("speed") == "fast" and l.get("hook") == "posttooluse"]
    slow = [l for l in configured if l.get("speed") == "slow"]

    if fast:
        matcher = "Write|Edit|MultiEdit"
        hooks = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": matcher,
                        "hooks": [
                            {"type": "command", "command": l.get("fix_command") or l["command"]}
                            for l in fast
                        ],
                    }
                ]
            }
        }
        print("\n  PROPOSED PostToolUse HOOK  (fast, configured tools only)\n")
        for line in json.dumps(hooks, indent=2).splitlines():
            print(f"    {line}")
    else:
        print("\n  No fast configured linter, so no per-edit hook is proposed.")
        print("  Configure ruff or biome first -- a slow checker per edit makes")
        print("  the session feel broken and gets the whole hook removed.")

    if slow:
        print("\n  FOR A Stop HOOK OR CI  (too slow per edit)\n")
        for lint in slow:
            print(f"    {lint['name']:<28} {lint['command']}")

    if missing:
        print("\n  NOT CONFIGURED, RELEVANT TO THIS STACK\n")
        for lint in sorted(missing, key=lambda l: (l["lang"], l["id"])):
            note = (lint.get("note") or lint.get("notes") or "").strip().replace("\n", " ")
            print(f"    {lint['name']:<28} [{lint['lang']}/{lint['kind']}]  {lint['install']}")
            if note:
                print(f"        {note[:96]}")

    if "pyspark" in langs:
        print("\n  PYSPARK NOTE\n")
        print("    databricks-labs-pylint is the one genuinely Spark-aware linter in wide")
        print("    use. Beyond it there is no mainstream PySpark static analysis -- shuffle")
        print("    ordering, UDFs where built-ins exist, unbounded collect(), missing")
        print("    broadcast hints are all uncovered. Do not expect to install past this.")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({
            "repo": str(repo), "files": files, "languages": langs,
            "declared_scripts": scripts,
            "configured": [l["id"] for l in configured],
            "missing": [l["id"] for l in missing],
        }, indent=2), encoding="utf-8")
        print(f"\n  Wrote {args.json}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
