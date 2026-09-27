# SPDX-FileCopyrightText: 2026 Jochen Schmitt and mdview contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Markdown rendering without GTK dependencies or network access."""

import base64
import hashlib
import html
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

ASSETS = Path(__file__).with_name("assets")
MAX_DOCUMENT = 8 * 1024 * 1024
MAX_IMAGE = 10 * 1024 * 1024
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}


@dataclass
class Document:
    html: str
    codes: list[str]


class UnsupportedDocument(ValueError):
    """The file is not supported UTF-8 text."""

    def __init__(self):
        super().__init__("File cannot be displayed")


def read_document(path: Path) -> str:
    if not path.is_file():
        raise ValueError("Choose a regular Markdown file.")
    with path.open("rb") as stream:
        data = stream.read(MAX_DOCUMENT + 1)
    if len(data) > MAX_DOCUMENT:
        raise ValueError("This document exceeds the 8 MiB size limit.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise UnsupportedDocument() from exc
    # PDF can consist entirely of ASCII; binary control characters also occur
    # in files that happen to decode as UTF-8. Allow normal text whitespace.
    if text.startswith("%PDF-") or any(
        (ord(char) < 32 and char not in "\t\n\r\f\v") or 127 <= ord(char) <= 159
        for char in text
    ):
        raise UnsupportedDocument()
    return text


def local_image(src: str, directory: Path) -> str | None:
    """Embed only raster files contained in the document directory."""
    uri = urlsplit(src)
    if uri.scheme or uri.netloc or not uri.path or uri.query:
        return None
    root = directory.resolve()
    path = (root / unquote(uri.path)).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in IMAGE_TYPES:
        return None
    try:
        if not path.is_file():
            return None
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE + 1)
    except OSError:
        return None
    if len(data) > MAX_IMAGE:
        return None
    return f"data:{IMAGE_TYPES[path.suffix.lower()]};base64," + base64.b64encode(data).decode()


def render(source: str, directory: Path, *, dark: bool = False) -> Document:
    codes = []
    parser = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

    def fence(tokens, index, options, env):
        token = tokens[index]
        code = token.content
        number = len(codes)
        codes.append(code)
        language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
        formatted = html.escape(code)
        if language:
            try:
                lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
                formatted = highlight(code, lexer, HtmlFormatter(nowrap=True))
            except ClassNotFound:
                pass
        return (f'<section class="code-block"><div class="code-header">'
                f'<span>{html.escape(language or "Code")}</span>'
                f'<button type="button" data-copy="{number}" aria-label="Copy code">Copy</button>'
                f'</div><pre><code>{formatted}</code></pre></section>\n')

    def image(tokens, index, options, env):
        token = tokens[index]
        alt = parser.renderer.renderInlineAsText(token.children or [], options, env)
        src = local_image(token.attrGet("src") or "", directory)
        if src is None:
            return f'<span class="blocked-image">[Image unavailable: {html.escape(alt)}]</span>'
        return f'<img src="{src}" alt="{html.escape(alt, quote=True)}">'

    parser.renderer.rules["fence"] = fence
    parser.renderer.rules["image"] = image
    tokens = parser.parse(source)
    for token in tokens:
        for child in token.children or []:
            if child.type == "link_open":
                href = child.attrGet("href") or ""
                uri = urlsplit(href)
                if href and not href.startswith("#") and not uri.scheme and not uri.netloc:
                    target = (directory / unquote(uri.path)).resolve().as_uri()
                    child.attrSet("href", target + (f"#{uri.fragment}" if uri.fragment else ""))
    used_ids = set()
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            text = tokens[i + 1].content
            slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-") or "section"
            candidate, suffix = slug, 1
            while candidate in used_ids:
                candidate = f"{slug}-{suffix}"
                suffix += 1
            used_ids.add(candidate)
            token.attrSet("id", candidate)
    body = parser.renderer.render(tokens, parser.options, {})
    css = (ASSETS / "style.css").read_text()
    css += HtmlFormatter(style="friendly").get_style_defs("html:not(.dark) .code-block")
    css += HtmlFormatter(style="monokai").get_style_defs("html.dark .code-block")
    script = (ASSETS / "bridge.js").read_text()
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
           f"script-src 'sha256-{digest}'; connect-src 'none'; "
           "base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'")
    page = (f'<!doctype html><html class="{"dark" if dark else "light"}" lang="en">'
            '<head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<style>{css}</style></head><body><main>{body}</main>'
            f'<script>{script}</script></body></html>')
    return Document(page, codes)
