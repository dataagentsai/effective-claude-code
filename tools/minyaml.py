"""A deliberately tiny YAML reader for the subset the rule files use.

PyYAML is not in the standard library, and installing it is not possible on
every machine this has to run on. Rather than depend on it, the rule format is
constrained to what fits in eighty lines of parser:

    key: scalar
    key: "quoted scalar"
    key: null
    key: [flow, list]
    key: |-
      block
      scalar
    key:
      - block
      - list

That is the whole grammar. Anything else in a rule file is a bug in the rule
file, and load() says so rather than guessing. Nesting beyond one level is not
supported and never will be here -- if a rule needs it, the rule is too complex.
"""

from __future__ import annotations


class MinYamlError(ValueError):
    """Raised with a line number when a file steps outside the subset."""


def _scalar(raw: str):
    text = raw.strip()
    if text in ("null", "~", ""):
        return None
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in inner.split(",")]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def load(text: str) -> dict:
    """Parse the subset above into a dict. Raises MinYamlError on anything else."""
    out: dict = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if line[0] in " \t":
            raise MinYamlError(f"line {i + 1}: unexpected indentation at top level")

        if ":" not in line:
            raise MinYamlError(f"line {i + 1}: expected 'key: value', got {stripped!r}")

        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        i += 1

        # Block scalar: |, |-, >, >-
        if rest[:1] in ("|", ">"):
            fold = rest[0] == ">"
            chomp = rest.endswith("-")
            body: list[str] = []
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
                body.append(lines[i])
                i += 1
            while body and not body[-1].strip():
                body.pop()
            indents = [len(b) - len(b.lstrip()) for b in body if b.strip()]
            pad = min(indents) if indents else 0
            body = [b[pad:] if len(b) >= pad else b for b in body]
            value = " ".join(x.strip() for x in body if x.strip()) if fold else "\n".join(body)
            out[key] = value if chomp else value + "\n"
            continue

        # Block list on following lines
        if rest == "":
            items = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or nxt.strip().startswith("#"):
                    i += 1
                    continue
                if nxt[:1] not in " \t":
                    break
                item = nxt.strip()
                if not item.startswith("- "):
                    raise MinYamlError(
                        f"line {i + 1}: nested mappings are not supported; got {item!r}"
                    )
                items.append(_scalar(item[2:]))
                i += 1
            out[key] = items
            continue

        out[key] = _scalar(rest)

    return out


def load_file(path) -> dict:
    import pathlib

    p = pathlib.Path(path)
    try:
        return load(p.read_text(encoding="utf-8"))
    except MinYamlError as exc:
        raise MinYamlError(f"{p}: {exc}") from exc
