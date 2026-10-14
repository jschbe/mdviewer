# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate local Markdown navigation without granting WebKit file access."""

from pathlib import Path
from urllib.parse import unquote, urlsplit


def local_link_path(uri: str) -> Path | None:
    try:
        parsed = urlsplit(uri)
        if (parsed.scheme not in ("file", "mdview") or parsed.netloc not in ("", "localhost")
                or parsed.query):
            return None
        filename = unquote(parsed.path, errors="strict")
        if "\0" in filename:
            return None
        path = Path(filename)
        if path.is_absolute() and path.suffix.lower() in (".md", ".markdown"):
            return path.resolve()
    except (ValueError, UnicodeError, OSError, RuntimeError):
        pass
    return None
