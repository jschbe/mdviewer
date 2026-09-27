# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import tempfile
import unittest
from pathlib import Path

from mdview.recent import MAX_RECENT, load_recent, remember_file


class RecentFilesTests(unittest.TestCase):
    def test_persistence_order_duplicates_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "state" / "recent.json"
            files = [Path(directory) / f"file {i} 日本語.md" for i in range(MAX_RECENT + 2)]
            for path in files:
                remember_file(history, path)
            self.assertEqual(load_recent(history), [str(p) for p in reversed(files[-MAX_RECENT:])])
            remember_file(history, files[-3])
            recent = load_recent(history)
            self.assertEqual(recent[0], str(files[-3]))
            self.assertEqual(recent[1], str(files[-1]))
            self.assertEqual(len(recent), MAX_RECENT)
            self.assertEqual(recent.count(str(files[-3])), 1)
            self.assertEqual(list(history.parent.iterdir()), [history])

    def test_missing_corrupt_and_invalid_history(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "recent.json"
            self.assertEqual(load_recent(history), [])
            for value in (b"broken", b"{}", b"null", b"\xff"):
                history.write_bytes(value)
                self.assertEqual(load_recent(history), [])
            history.write_text(json.dumps([None, 123, "relative.md", "/bad\0path",
                                           "/valid.md", "/valid.md", "/other.md"]))
            self.assertEqual(load_recent(history), ["/valid.md", "/other.md"])
            remember_file(history, Path(directory) / "new.md")
            self.assertEqual(load_recent(history)[0], str(Path(directory) / "new.md"))

    def test_separate_updates_keep_previous_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "recent.json"
            first, second = Path(directory) / "a.md", Path(directory) / "b.md"
            remember_file(history, first)
            remember_file(history, second)
            self.assertEqual(load_recent(history), [str(second), str(first)])
