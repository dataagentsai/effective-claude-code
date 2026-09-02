"""Read Claude Code's local session transcripts.

Claude Code writes one JSONL file per session under the projects directory. Each
line is an event; assistant events carry a usage block, and every event carries a
timestamp. This module is the single place that knows that layout, so the
analyzers above it do not each re-derive it.

Nothing here leaves the machine. No network, no dependencies.

Layout, as of Claude Code 2.x:

    ~/.claude/projects/<slugified-cwd>/<session-uuid>.jsonl

    {"type": "assistant", "timestamp": ..., "message": {"model": ...,
      "usage": {"input_tokens", "output_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "output_tokens_details": {...}}}}
    {"type": "user", "timestamp": ..., "toolUseResult": {...}}

The shape is not a public contract. read_session() tolerates missing keys
throughout rather than assuming any particular version.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from datetime import datetime


def transcript_root() -> pathlib.Path:
    """Where Claude Code keeps session transcripts on this machine."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = pathlib.Path(override) if override else pathlib.Path.home() / ".claude"
    return base / "projects"


def find_sessions(root: pathlib.Path | None = None, project: str | None = None):
    """Yield every session transcript, newest first.

    `project` filters on the slugified-cwd directory name, e.g. a substring of
    the repo path.
    """
    root = root or transcript_root()
    if not root.is_dir():
        return []
    files = []
    for proj_dir in root.iterdir():
        if not proj_dir.is_dir():
            continue
        if project and project.lower() not in proj_dir.name.lower():
            continue
        files.extend(proj_dir.glob("*.jsonl"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _ts(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@dataclass
class Session:
    """One session, reduced to the numbers worth reporting."""

    path: pathlib.Path
    session_id: str = ""
    project: str = ""
    started: datetime | None = None
    ended: datetime | None = None
    versions: set = field(default_factory=set)
    models: set = field(default_factory=set)

    prompts: int = 0
    api_calls: int = 0
    tool_calls: int = 0

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    tool_use: dict = field(default_factory=dict)
    tool_errors: list = field(default_factory=list)
    refusals: int = 0
    malformed_lines: int = 0

    @property
    def duration_minutes(self) -> float:
        if not (self.started and self.ended):
            return 0.0
        return round((self.ended - self.started).total_seconds() / 60, 1)

    @property
    def total_input_tokens(self) -> int:
        """Everything billed on the input side, cached or not."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    @property
    def cache_ratio(self) -> float:
        """Cache reads per cache write. High is good -- the cache is being reused."""
        return round(self.cache_read_tokens / self.cache_write_tokens, 1) if self.cache_write_tokens else 0.0

    @property
    def mean_context_per_call(self) -> int:
        """Average input tokens carried into each API call.

        The clearest single indicator of session bloat: it is the size of the
        conversation being re-sent, and it only ever grows within a session.
        """
        return round(self.total_input_tokens / self.api_calls) if self.api_calls else 0


def read_session(path: pathlib.Path) -> Session:
    """Parse one transcript. Malformed lines are counted, never fatal."""
    s = Session(path=path, session_id=path.stem, project=path.parent.name)

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                s.malformed_lines += 1
                continue
            if not isinstance(rec, dict):
                s.malformed_lines += 1
                continue

            when = _ts(rec.get("timestamp"))
            if when:
                if not s.started or when < s.started:
                    s.started = when
                if not s.ended or when > s.ended:
                    s.ended = when

            if rec.get("version"):
                s.versions.add(rec["version"])

            rtype = rec.get("type")

            if rtype == "assistant":
                s.api_calls += 1
                msg = rec.get("message") or {}
                if msg.get("model"):
                    s.models.add(msg["model"])
                if msg.get("stop_reason") == "refusal":
                    s.refusals += 1

                usage = msg.get("usage") or {}
                s.input_tokens += usage.get("input_tokens") or 0
                s.output_tokens += usage.get("output_tokens") or 0
                s.cache_read_tokens += usage.get("cache_read_input_tokens") or 0
                s.cache_write_tokens += usage.get("cache_creation_input_tokens") or 0
                details = usage.get("output_tokens_details") or {}
                s.thinking_tokens += details.get("thinking_tokens") or 0

                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        s.tool_calls += 1
                        name = block.get("name", "unknown")
                        s.tool_use[name] = s.tool_use.get(name, 0) + 1

            elif rtype == "user":
                result = rec.get("toolUseResult")
                if result is None and rec.get("promptSource"):
                    # A real human turn, not a tool result being fed back.
                    s.prompts += 1
                elif result is not None:
                    err = _extract_error(result)
                    if err:
                        s.tool_errors.append(err)

    return s


def _extract_error(result) -> str | None:
    """Pull an error string out of a tool result, whatever shape it arrived in."""
    if isinstance(result, str):
        text = result
    elif isinstance(result, dict):
        if result.get("is_error") or result.get("isError"):
            return str(result.get("content") or result.get("error") or "")[:500]
        text = str(result.get("stderr") or result.get("error") or "")
    else:
        return None

    lowered = text.lower()
    markers = (
        "no such file",
        "file does not exist",
        "cannot find",
        "enoent",
        "not found",
        "string to replace not found",
        "could not find the string",
        "has not been read yet",
        "error:",
    )
    if any(m in lowered for m in markers):
        return text.strip()[:500]
    return None


def read_all(project: str | None = None, limit: int | None = None):
    """Read every session, newest first."""
    paths = find_sessions(project=project)
    if limit:
        paths = paths[:limit]
    return [read_session(p) for p in paths]
