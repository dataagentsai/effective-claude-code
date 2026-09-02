"""Walk the ontology and report what is missing.

    python tools/coverage.py                     # coverage for every activity
    python tools/coverage.py --activity ACT-03   # just debugging
    python tools/coverage.py --gaps              # the build list, ranked
    python tools/coverage.py --signal invented_path
    python tools/coverage.py --json coverage.json

The last form is the diagnosis traversal: give it an observable the analyzers
produce and it names the failure mode, the rules that mitigate it, and the
capabilities that would remove it. That is what makes the graph worth having
rather than a taxonomy for its own sake.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from minyaml import load_all_file, MinYamlError  # noqa: E402

MARK = {"built": "[x]", "partial": "[~]", "gap": "[ ]", "install": "[+]"}
LEGEND = (
    "[x] built here    [~] partial    [ ] gap, ours to build    "
    "[+] install, someone else maintains it"
)
# Ranking for the build list: what blocks the most activities, soonest.
STATUS_RANK = {"gap": 0, "partial": 1, "install": 2, "built": 3}


def load():
    try:
        acts = load_all_file(ROOT / "ontology" / "activities.yaml")
        caps = load_all_file(ROOT / "ontology" / "capabilities.yaml")
        fms = load_all_file(ROOT / "ontology" / "failure_modes.yaml")
    except MinYamlError as exc:
        print(f"ontology is malformed: {exc}", file=sys.stderr)
        raise SystemExit(2)
    return (
        acts,
        {c["id"]: c for c in caps},
        {f["id"]: f for f in fms},
    )


def check_integrity(acts, caps, fms) -> list:
    """Dangling references are silent rot in a graph. Surface them."""
    problems = []
    rule_ids = {p.stem for p in (ROOT / "rules").glob("ECC-*.yaml")}

    for a in acts:
        for cid in a.get("needs") or []:
            if cid not in caps:
                problems.append(f"{a['id']} needs unknown capability {cid}")
        for fid in a.get("exhibits") or []:
            if fid not in fms:
                problems.append(f"{a['id']} exhibits unknown failure mode {fid}")
    for c in caps.values():
        for fid in c.get("addresses") or []:
            if fid not in fms:
                problems.append(f"{c['id']} addresses unknown failure mode {fid}")
    for f in fms.values():
        for rid in f.get("mitigated_by") or []:
            if rid not in rule_ids:
                problems.append(f"{f['id']} cites rule {rid}, which does not exist yet")
        for cid in f.get("capabilities") or []:
            if cid not in caps:
                problems.append(f"{f['id']} cites unknown capability {cid}")
    return problems


def _cap_line(c) -> str:
    src = c.get("source", "?")
    sup = c.get("supplier")
    origin = f"{src}" + (f" · {sup}" if sup else "")
    return f"    {MARK.get(c.get('status'), '[?]')} {c['id']}  {c['label']:<38} {origin}"


def show_activities(acts, caps, only=None):
    print(f"\n  CAPABILITY COVERAGE BY ACTIVITY\n  {LEGEND}\n")
    for a in acts:
        if only and a["id"] != only:
            continue
        needed = [caps[c] for c in (a.get("needs") or []) if c in caps]
        gaps = [c for c in needed if c.get("status") in ("gap", "partial")]
        held = [c for c in needed if c.get("status") == "built"]
        installs = [c for c in needed if c.get("status") == "install"]
        print(f"  {a['id']}  {a['label'].upper()}   ({a.get('phase','')})")
        print(f"        {len(held)} built · {len(installs)} to install · {len(gaps)} to build")
        for c in needed:
            print(_cap_line(c))
        if a.get("exhibits"):
            print(f"        prone to: {', '.join(a['exhibits'])}")
        print()


def show_gaps(acts, caps):
    """Rank unbuilt capabilities by how many activities they block."""
    blocks: dict[str, list] = {}
    for a in acts:
        for cid in a.get("needs") or []:
            blocks.setdefault(cid, []).append(a["label"])

    rows = [
        c for c in caps.values() if c.get("status") in ("gap", "partial")
    ]
    rows.sort(key=lambda c: (-len(blocks.get(c["id"], [])), STATUS_RANK[c["status"]]))

    print("\n  WHAT TO BUILD, RANKED BY HOW MANY ACTIVITIES IT BLOCKS\n")
    for c in rows:
        who = blocks.get(c["id"], [])
        print(f"  {MARK[c['status']]} {c['id']}  {c['label']}")
        print(f"        blocks {len(who)}: {', '.join(who) if who else '-'}")
        note = (c.get("note") or "").strip().replace("\n", " ")
        if note:
            for chunk in _wrap(note, 82):
                print(f"        {chunk}")
        print()

    print("  TO INSTALL RATHER THAN BUILD\n")
    for c in sorted(caps.values(), key=lambda c: c["id"]):
        if c.get("status") == "install":
            print(f"  [+] {c['id']}  {c['label']:<38} {c.get('supplier','')}")
    print()


def show_signal(signal, caps, fms):
    hits = [f for f in fms.values() if signal in (f.get("detected_by") or [])]
    if not hits:
        known = sorted({s for f in fms.values() for s in (f.get("detected_by") or [])})
        print(f"\n  No failure mode is detected by '{signal}'.\n  Known signals:\n")
        for s in known:
            print(f"    {s}")
        print()
        return
    print(f"\n  DIAGNOSIS FOR SIGNAL: {signal}\n")
    for f in hits:
        print(f"  {f['id']}  {f['label']}")
        for chunk in _wrap((f.get("description") or "").strip().replace("\n", " "), 82):
            print(f"        {chunk}")
        print(f"\n        detected by   {', '.join(f.get('detected_by') or [])}")
        print(f"        substrate     {f.get('substrate','-')}")
        print(f"        rules         {', '.join(f.get('mitigated_by') or []) or '-'}")
        print("        capabilities  ", end="")
        cs = [caps[c] for c in (f.get("capabilities") or []) if c in caps]
        print(", ".join(f"{c['id']} ({c.get('status')})" for c in cs) or "-")
        if f.get("note"):
            print()
            for chunk in _wrap(f["note"].strip().replace("\n", " "), 82):
                print(f"        {chunk}")
        print()


def show_summary(caps):
    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for c in caps.values():
        by_source[c.get("source", "?")] = by_source.get(c.get("source", "?"), 0) + 1
        by_status[c.get("status", "?")] = by_status.get(c.get("status", "?"), 0) + 1

    print("  " + "=" * 62)
    print(f"  {len(caps)} capabilities")
    print("  by source:  " + "   ".join(f"{k} {v}" for k, v in sorted(by_source.items())))
    print("  by status:  " + "   ".join(f"{k} {v}" for k, v in sorted(by_status.items())))
    reuse = sum(v for k, v in by_source.items() if k != "own")
    print(f"\n  {reuse} of {len(caps)} are somebody else's to maintain.")
    print("  Reuse capability, build governance.")
    print("  " + "=" * 62 + "\n")


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activity", help="restrict to one activity id, e.g. ACT-03")
    ap.add_argument("--gaps", action="store_true", help="the build list, ranked")
    ap.add_argument("--signal", help="diagnose from an observable, e.g. invented_path")
    ap.add_argument("--json", metavar="PATH", help="write the whole graph as JSON")
    args = ap.parse_args()

    acts, caps, fms = load()

    problems = check_integrity(acts, caps, fms)
    if problems:
        print("\n  ONTOLOGY REFERENCE PROBLEMS\n", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        print(file=sys.stderr)

    if args.signal:
        show_signal(args.signal, caps, fms)
    elif args.gaps:
        show_gaps(acts, caps)
        show_summary(caps)
    else:
        show_activities(acts, caps, only=args.activity)
        if not args.activity:
            show_summary(caps)

    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps(
                {"activities": acts, "capabilities": list(caps.values()), "failure_modes": list(fms.values())},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  Wrote {args.json}\n")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
