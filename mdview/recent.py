# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Persistent, most-recent-first history of successfully opened local files."""

import json
from pathlib import Path

from .storage import atomic_write_json

MAX_RECENT = 10


def load_recent(path: Path) -> list[str]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(saved, list):
        return []
    recent = []
    for item in saved:
        if (isinstance(item, str) and "\0" not in item
                and Path(item).is_absolute() and item not in recent):
            recent.append(item)
            if len(recent) == MAX_RECENT:
                break
    return recent


def remember_file(history_path: Path, document: Path) -> None:
    filename = str(document.absolute())
    recent = [filename, *(item for item in load_recent(history_path) if item != filename)]
    atomic_write_json(history_path, recent[:MAX_RECENT])
