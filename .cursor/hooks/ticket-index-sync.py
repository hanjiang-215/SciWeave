#!/usr/bin/env python3
"""Keep docs/tickets in sync after fer or ticket-file changes.

Registered for two Cursor hooks:
  afterShellExecution  -> argument ``after-shell``
  afterFileEdit        -> argument ``after-file-edit``

The hook only reacts to mutations of fer tickets or of
``docs/tickets/index.toml`` and then runs ``ticket_index.py render``.
Anything else exits immediately. Failures are reported on stderr and never
block the command or the edit.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_SCRIPT = REPO_ROOT / ".cursor/skills/engineering/ticket-index/scripts/ticket_index.py"

FER_WORD = re.compile(r"\bfer(?:\.exe)?\b", re.IGNORECASE)
FER_MUTATION = re.compile(
    r"\b(?:create|start|close|status|reopen|dep|undep|link|unlink|edit|add-note)\b",
    re.IGNORECASE,
)
TICKET_FILE = re.compile(r"\.tickets[/\\]ai4-[0-9a-z]{4}\.md$", re.IGNORECASE)
INDEX_CONFIG = re.compile(r"docs[/\\]tickets[/\\]index\.toml$", re.IGNORECASE)


def touches_tickets(event: str, payload: dict) -> bool:
    if event == "after-shell":
        command = str(payload.get("command", ""))
        return bool(FER_WORD.search(command) and FER_MUTATION.search(command))
    if event == "after-file-edit":
        path = str(payload.get("file_path", ""))
        return bool(TICKET_FILE.search(path) or INDEX_CONFIG.search(path))
    return False


def render() -> None:
    result = subprocess.run(
        [sys.executable, str(INDEX_SCRIPT), "render"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"ticket-index 自动同步失败：{detail}", file=sys.stderr)


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not touches_tickets(event, payload):
        return 0
    if not INDEX_SCRIPT.is_file():
        return 0
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
