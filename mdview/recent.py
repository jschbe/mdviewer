# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Persistent, most-recent-first history of successfully opened local files."""

import json
import os
import tempfile
from pathlib import Path

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
    history_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=history_path.parent, prefix=".recent-",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(recent[:MAX_RECENT], stream)
            stream.write("\n")
        os.replace(temporary, history_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
