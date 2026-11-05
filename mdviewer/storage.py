# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Atomic JSON replacement shared by window state, sessions and recent files."""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path


def state_directory(root: Path) -> Path:
    """Copy legacy state once, without changing originals or existing new state."""
    current, legacy = root / "mdviewer", root / "mdview"
    if current.exists() or not legacy.is_dir():
        return current
    try:
        # Publish all three files together; an interrupted copy can be retried.
        with tempfile.TemporaryDirectory(prefix=".mdviewer-state-", dir=root) as temporary:
            staged = Path(temporary) / "mdviewer"
            staged.mkdir(mode=0o700)
            for name in ("window.json", "session.json", "recent.json"):
                source = legacy / name
                if source.is_file():
                    shutil.copyfile(source, staged / name)
            try:
                staged.rename(current)
            except OSError:
                # Another process has already published the migrated state.
                # Linux can report ENOTEMPTY rather than EEXIST here.
                if not current.is_dir():
                    raise
    except OSError as exc:
        logging.warning("Could not copy legacy mdview state; using it in place: %s", exc)
        return legacy
    return current


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.stem}-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
