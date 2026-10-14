# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mdview.links import local_link_path
from mdview.render import render


class LinkTests(unittest.TestCase):
    def test_relative_links_and_encoded_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, href in (("architecture.md", "docs/architecture.md"),
                               ("a b.md", "docs/a%20b.md"),
                               ("a b.md", "<docs/a b.md>"),
                               ("café#%.MARKDOWN", "docs/caf%C3%A9%23%25.MARKDOWN")):
                target = root / "docs" / name
                page = render(f"[target]({href})", root).html
                self.assertIn(f'href="{target.as_uri().replace("file:", "mdview:", 1)}"', page)
                self.assertEqual(local_link_path(target.as_uri() + "#heading"), target)
                self.assertEqual(local_link_path(target.as_uri().replace("file:", "mdview:", 1)), target)
            target = root.parent / "other.md"
            self.assertIn(target.as_uri().replace("file:", "mdview:", 1) + "#heading",
                          render("[target](../other.md#heading)", root).html)
            # Query strings must not silently turn into a different local file.
            page = render("[target](other.md?query=1)", root).html
            self.assertIn("other.md?query=1", page)
            self.assertIsNone(local_link_path((root / "other.md").as_uri() + "?query=1"))

    def test_canonical_paths_and_localhost(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "a.md"
            (root / "alias.md").symlink_to(target)
            self.assertEqual(local_link_path((root / "alias.md").as_uri()), target)
            self.assertEqual(local_link_path("file://localhost" + str(target)), target)

    def test_invalid_symlink_does_not_prevent_source_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Python 3.10–3.12 report symlink loops as RuntimeError; newer
            # versions can defer them until the target is actually read.
            with patch.object(Path, "resolve", side_effect=RuntimeError("Symlink loop")):
                page = render("# Source\n\n[target](loop.md)", root).html
                self.assertIn('id="source"', page)
                self.assertIn((root / "loop.md").as_uri().replace("file:", "mdview:", 1), page)
                self.assertIsNone(local_link_path((root / "loop.md").as_uri()))

    def test_restricted_schemes_and_invalid_targets(self):
        for uri in ("https://example.com/a.md", "javascript:alert(1)", "data:text/plain,a",
                    "ftp://host/a.md", "file://remote/tmp/a.md", "file:relative.md",
                    "file:///etc/passwd", "file:///tmp/a.svg", "file:///tmp/a.md?query",
                    "file:///tmp/a%00.md", "file:///tmp/a%FF.md", "file://[bad/a.md"):
            with self.subTest(uri=uri):
                self.assertIsNone(local_link_path(uri))
        for uri in ("mdview://remote/tmp/a.md", "mdview:relative.md", "mdview:///tmp/a.svg",
                    "mdview:///tmp/a%00.md", "mdview:///tmp/a.md?query"):
            self.assertIsNone(local_link_path(uri))
