# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import tempfile
import unittest
from pathlib import Path

from mdview.session import load_session, save_session


class SessionTests(unittest.TestCase):
    def test_round_trip_order_active_and_empty_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state' / 'session.json'
            files = ['/tmp/日本語.md', '/tmp/a file.md']
            save_session(path, files, files[0])
            self.assertEqual(load_session(path), {'files': files, 'active': files[0]})
            save_session(path, [], None)
            self.assertEqual(load_session(path), {'files': [], 'active': None})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_corrupt_invalid_and_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            empty = {'files': [], 'active': None}
            self.assertEqual(load_session(path), empty)
            for value in (b'broken', b'[]', b'\xff', b'{"files": "wrong"}'):
                path.write_bytes(value)
                self.assertEqual(load_session(path), empty)
            path.write_text(json.dumps({'files': ['/a.md', None, 'relative.md', '/a.md', '/bad\0', '/b.md'], 'active': '/missing.md'}))
            self.assertEqual(load_session(path), {'files': ['/a.md', '/b.md'], 'active': None})
