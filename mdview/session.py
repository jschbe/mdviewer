# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Persist open tabs separately from window geometry and recent-file history."""

import json
from pathlib import Path

from .storage import atomic_write_json


def load_session(path: Path) -> dict:
    session = {"files": [], "active": None}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return session
    if not isinstance(saved, dict) or not isinstance(saved.get("files"), list):
        return session
    for filename in saved["files"]:
        if (isinstance(filename, str) and "\0" not in filename
                and Path(filename).is_absolute() and filename not in session["files"]):
            session["files"].append(filename)
    active = saved.get("active")
    if isinstance(active, str) and active in session["files"]:
        session["active"] = active
    return session


def save_session(path: Path, files: list[str], active: str | None) -> None:
    atomic_write_json(path, {"files": files, "active": active})
