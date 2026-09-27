# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small, validated window-state file; no settings schema installation needed."""

import json
from pathlib import Path

from .storage import atomic_write_json


def load_state(path: Path) -> dict:
    state = {"width": 960, "height": 760, "maximized": False}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if not isinstance(saved, dict):
        return state
    for key in ("width", "height"):
        value = saved.get(key)
        if type(value) is int and 1 <= value <= 32768:
            state[key] = value
    if type(saved.get("maximized")) is bool:
        state["maximized"] = saved["maximized"]
    return state


def save_state(path: Path, width: int, height: int, maximized: bool) -> None:
    atomic_write_json(path, {"width": width, "height": height, "maximized": maximized})
