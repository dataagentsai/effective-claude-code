"""Validate every rule file against schema/rule.schema.json.

    python tools/lint_rules.py

No jsonschema dependency -- this enforces the subset of the schema that matters
(required fields, enums, id format, check/review_question pairing, referenced
check files existing). Exits non-zero on the first failure set.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from minyaml import load_file, MinYamlError  # noqa: E402


def main() -> int:
    schema = json.loads((ROOT / "schema" / "rule.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    required = schema["required"]

    errors, seen_ids, count = [], set(), 0

    for path in sorted((ROOT / "rules").glob("*.yaml")):
        count += 1
        name = path.name
        try:
            rule = load_file(path)
        except MinYamlError as exc:
            errors.append(f"{name}: {exc}")
            continue

        for key in required:
            if key not in rule or rule[key] in (None, "", []):
                errors.append(f"{name}: missing required field '{key}'")

        for key in rule:
            if key not in props:
                errors.append(f"{name}: unknown field '{key}'")

        rid = rule.get("id", "")
        if not (rid.startswith("ECC-") and len(rid) == 8 and rid[4:].isdigit()):
            errors.append(f"{name}: id '{rid}' is not ECC-nnnn")
        elif rid in seen_ids:
            errors.append(f"{name}: duplicate id '{rid}'")
        else:
            seen_ids.add(rid)
        if rid and path.stem != rid:
            errors.append(f"{name}: filename does not match id '{rid}'")

        for field in ("status", "level", "area"):
            allowed = props[field].get("enum")
            if allowed and rule.get(field) not in allowed:
                errors.append(f"{name}: {field}='{rule.get(field)}' not one of {allowed}")

        scopes = props["applies_to"]["items"]["enum"]
        for scope in rule.get("applies_to") or []:
            if scope not in scopes:
                errors.append(f"{name}: applies_to '{scope}' not one of {scopes}")

        if "check" in rule:
            if rule["check"] is None:
                if not rule.get("review_question"):
                    errors.append(f"{name}: check is null but no review_question given")
            else:
                if not (ROOT / rule["check"]).is_file():
                    # Not an error -- the audit reports it as NOT_EVALUATED --
                    # but worth surfacing so it does not go unnoticed forever.
                    print(f"  note: {name} points at {rule['check']}, not yet implemented")

        for cid in rule.get("discharges") or []:
            if not str(cid).startswith("CANON-"):
                errors.append(f"{name}: discharges '{cid}' is not a CANON id")

    if errors:
        print(f"\n{len(errors)} problem(s) in {count} rule file(s):\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"\n  {count} rule files valid, {len(seen_ids)} unique ids.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
