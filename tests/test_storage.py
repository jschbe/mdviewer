# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mdview.storage import atomic_write_json


class AtomicJsonTests(unittest.TestCase):
    def test_replace_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'state.json'
            atomic_write_json(path, {'old': True})
            value = {'files': ['日本語.md', 'Grüße.md']}
            atomic_write_json(path, value)
            self.assertEqual(json.loads(path.read_text()), value)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failure_preserves_old_file_and_removes_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            atomic_write_json(path, {'old': True})
            original = path.read_bytes()
            with self.assertRaises(TypeError):
                atomic_write_json(path, {'invalid': object()})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])
            with patch('mdview.storage.os.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {'new': True})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])
