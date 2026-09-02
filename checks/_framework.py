"""Shared plumbing for rule checks.

A check is a module in this directory exposing `run(ctx) -> Verdict`. It gets a
Context describing the repo and the settings in force, and returns one of four
outcomes:

    PASS             the requirement is met
    FAIL             the requirement is not met
    NOT_APPLICABLE   the rule does not apply here (wrong scale, wrong stack)
    NOT_EVALUATED    the check could not run -- and always says why

That last one is the point. A check that cannot inspect what it needs must say
so, never quietly return PASS. An audit that silently passes what it did not
look at is worse than no audit, because it is believed.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_EVALUATED = "NOT_EVALUATED"


@dataclass
class Verdict:
    verdict: str
    reason: str = ""
    evidence: list = field(default_factory=list)

    def __post_init__(self):
        if self.verdict == NOT_EVALUATED and not self.reason:
            raise ValueError("NOT_EVALUATED must carry a reason")


def passed(reason="", evidence=None):
    return Verdict(PASS, reason, evidence or [])


def failed(reason, evidence=None):
    return Verdict(FAIL, reason, evidence or [])


def na(reason):
    return Verdict(NOT_APPLICABLE, reason)


def skipped(reason):
    return Verdict(NOT_EVALUATED, reason)


def _read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


@dataclass
class Context:
    """Everything a check is allowed to look at."""

    repo: pathlib.Path
    config_dir: pathlib.Path
    user_settings: dict = field(default_factory=dict)
    user_settings_local: dict = field(default_factory=dict)
    project_settings: dict = field(default_factory=dict)
    project_settings_local: dict = field(default_factory=dict)
    tracked_files: list = field(default_factory=list)
    file_count: int = 0

    # ---- convenience accessors -------------------------------------------

    @property
    def all_settings(self):
        return [
            ("user settings.json", self.user_settings),
            ("user settings.local.json", self.user_settings_local),
            ("project settings.json", self.project_settings),
            ("project settings.local.json", self.project_settings_local),
        ]

    def permission_rules(self, tier: str):
        """Every rule in a tier ('allow' | 'ask' | 'deny'), with its source."""
        out = []
        for label, settings in self.all_settings:
            for rule in (settings.get("permissions") or {}).get(tier) or []:
                out.append((label, rule))
        return out

    def setting(self, key: str):
        """First definition of a top-level key, project settings winning."""
        for _, settings in reversed(self.all_settings):
            if key in settings:
                return settings[key]
        return None

    def claude_md_files(self):
        found = []
        for candidate in (self.repo / "CLAUDE.md", self.repo / ".claude" / "CLAUDE.md"):
            if candidate.is_file():
                found.append(candidate)
        for nested in self.repo.rglob("CLAUDE.md"):
            if nested not in found and ".git" not in nested.parts and "node_modules" not in nested.parts:
                found.append(nested)
        return found

    @property
    def is_large(self) -> bool:
        return self.file_count >= 1000


def build_context(repo: str | pathlib.Path) -> Context:
    repo = pathlib.Path(repo).resolve()
    config_dir = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or (pathlib.Path.home() / ".claude"))

    ctx = Context(repo=repo, config_dir=config_dir)
    ctx.user_settings = _read_json(config_dir / "settings.json") or {}
    ctx.user_settings_local = _read_json(config_dir / "settings.local.json") or {}
    ctx.project_settings = _read_json(repo / ".claude" / "settings.json") or {}
    ctx.project_settings_local = _read_json(repo / ".claude" / "settings.local.json") or {}

    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".next"}
    count = 0
    files = []
    for root, dirs, filenames in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in filenames:
            count += 1
            if len(files) < 20000:
                files.append(str(pathlib.Path(root, name).relative_to(repo)).replace("\\", "/"))
    ctx.file_count = count
    ctx.tracked_files = files
    return ctx
