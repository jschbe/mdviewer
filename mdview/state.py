# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Small, validated window-state file; no settings schema installation needed."""

import json
import os
import tempfile
from pathlib import Path


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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".window-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"width": width, "height": height, "maximized": maximized}, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
