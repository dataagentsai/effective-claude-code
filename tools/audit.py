"""Audit a repository's Claude Code setup against the ECC rules.

    python tools/audit.py                     # audit the current directory
    python tools/audit.py --repo C:\\src\\thing
    python tools/audit.py --json report.json

Every active rule is loaded from rules/, matched against the repo's profile, and
dispatched to its check. Rules whose check is missing or unimplemented report
NOT_EVALUATED with a reason -- they are never counted as passing.

The score counts MUST and SHOULD rules that were actually evaluated. Rules that
could not run are reported separately, because a score that quietly absorbs them
is a score that flatters.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "checks"))

from minyaml import load_file, MinYamlError  # noqa: E402
from _framework import (  # noqa: E402
    FAIL,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PASS,
    build_context,
    skipped,
)

WEIGHT = {"MUST": 3, "SHOULD": 1, "CONSIDER": 0}
GLYPH = {PASS: "PASS", FAIL: "FAIL", NOT_APPLICABLE: " n/a", NOT_EVALUATED: "  ??"}


def load_rules():
    rules = []
    for path in sorted((ROOT / "rules").glob("ECC-*.yaml")):
        try:
            rule = load_file(path)
        except MinYamlError as exc:
            print(f"  ! skipping malformed rule {path.name}: {exc}", file=sys.stderr)
            continue
        if rule.get("status") == "active":
            rules.append(rule)
    return rules


def applies(rule, ctx, profile) -> bool:
    scopes = rule.get("applies_to") or ["any-repo"]
    if "any-repo" in scopes:
        return True
    if "large-repo" in scopes and ctx.is_large:
        return True
    if "monorepo" in scopes and profile.get("monorepo"):
        return True
    if "team" in scopes and profile.get("team"):
        return True
    if "solo" in scopes and not profile.get("team"):
        return True
    if "public-repo" in scopes and profile.get("public"):
        return True
    return False


def run_check(rule, ctx):
    ref = rule.get("check")
    if ref is None:
        q = rule.get("review_question", "").strip().replace("\n", " ")
        return skipped(f"Not automatable. Review question: {q}")

    path = ROOT / ref
    if not path.is_file():
        return skipped(f"Check not implemented yet ({ref} does not exist).")

    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module.run(ctx)
    except Exception as exc:  # a broken check must not fail the audit
        return skipped(f"Check raised {type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="repository to audit (default: cwd)")
    ap.add_argument("--team", action="store_true", help="more than one person uses Claude Code here")
    ap.add_argument("--json", metavar="PATH", help="write the report as JSON")
    args = ap.parse_args()

    ctx = build_context(args.repo)
    profile = {
        "team": args.team,
        "monorepo": (ctx.repo / "packages").is_dir() or (ctx.repo / "apps").is_dir(),
        "public": (ctx.repo / "LICENSE").is_file(),
    }

    rules = load_rules()
    if not rules:
        print("No active rules found under rules/.", file=sys.stderr)
        return 2

    print(f"\n  ECC AUDIT  --  {ctx.repo}")
    print(f"  {ctx.file_count:,} files{'  (large repo)' if ctx.is_large else ''}"
          f"{'  team' if profile['team'] else '  solo'}\n")

    results, area_now = [], None
    for rule in rules:
        if not applies(rule, ctx, profile):
            verdict = None
        else:
            verdict = run_check(rule, ctx)
        results.append((rule, verdict))

    for rule, verdict in results:
        if verdict is None:
            continue
        if rule["area"] != area_now:
            area_now = rule["area"]
            print(f"  [{area_now}]")
        title = rule["title"].strip()
        print(f"    {GLYPH[verdict.verdict]}  {rule['id']}  {rule['level']:<8} {title}")
        if verdict.verdict in (FAIL, NOT_EVALUATED):
            for chunk in _wrap(verdict.reason, 84):
                print(f"          {chunk}")
            for item in verdict.evidence[:6]:
                print(f"            - {item}")
        print()

    scored = [
        (r, v) for r, v in results
        if v and v.verdict in (PASS, FAIL) and WEIGHT.get(r["level"], 0)
    ]
    earned = sum(WEIGHT[r["level"]] for r, v in scored if v.verdict == PASS)
    possible = sum(WEIGHT[r["level"]] for r, _ in scored)
    fails = [(r, v) for r, v in results if v and v.verdict == FAIL]
    unevaluated = [(r, v) for r, v in results if v and v.verdict == NOT_EVALUATED]
    must_fails = [r for r, _ in fails if r["level"] == "MUST"]

    print("  " + "=" * 60)
    pct = round(earned / possible * 100) if possible else 0
    print(f"  SCORE  {pct}%   ({earned}/{possible} weighted, {len(scored)} rules evaluated)")
    print(f"  {len(must_fails)} MUST failing, {len(fails) - len(must_fails)} SHOULD failing, "
          f"{len(unevaluated)} not evaluated")
    if unevaluated:
        print("  Not-evaluated rules are excluded from the score rather than assumed passing.")
    print("  " + "=" * 60)

    if fails:
        print("\n  DO THESE FIRST\n")
        for rule, _ in sorted(fails, key=lambda rv: -WEIGHT[rv[0]["level"]])[:6]:
            fix = (rule.get("remediation") or "").strip().split("\n")[0]
            print(f"  {rule['id']}  {rule['title'].strip()}")
            if fix:
                print(f"          {fix}")
        print()

    if args.json:
        payload = {
            "repo": str(ctx.repo),
            "file_count": ctx.file_count,
            "profile": profile,
            "score_pct": pct,
            "results": [
                {
                    "id": r["id"],
                    "level": r["level"],
                    "area": r["area"],
                    "title": r["title"].strip(),
                    "verdict": v.verdict if v else NOT_APPLICABLE,
                    "reason": v.reason if v else "Does not apply to this repo profile.",
                    "evidence": v.evidence if v else [],
                }
                for r, v in results
            ],
        }
        pathlib.Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  Wrote {args.json}\n")

    return 1 if must_fails else 0


def _wrap(text, width):
    words, line, out = str(text).split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
