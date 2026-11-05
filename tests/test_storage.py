# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mdviewer.storage import atomic_write_json, state_directory


class StateMigrationTests(unittest.TestCase):
    def test_copy_preserves_legacy_and_loads_existing_formats(self):
        from mdviewer.recent import load_recent
        from mdviewer.session import load_session
        from mdviewer.state import load_state

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'mdview'
            legacy.mkdir()
            values = {'window.json': {'width': 1200, 'zoom': 125},
                      'session.json': {'files': ['/tmp/Grüße.md'], 'active': '/tmp/Grüße.md'},
                      'recent.json': ['/tmp/Grüße.md']}
            for name, value in values.items():
                atomic_write_json(legacy / name, value)
            originals = {p.name: p.read_bytes() for p in legacy.iterdir()}
            current = state_directory(root)
            self.assertEqual(current, root / 'mdviewer')
            self.assertEqual(load_state(current / 'window.json')['zoom'], 125)
            self.assertEqual(load_session(current / 'session.json'), values['session.json'])
            self.assertEqual(load_recent(current / 'recent.json'), values['recent.json'])
            self.assertEqual({p.name: p.read_bytes() for p in current.iterdir()}, originals)
            atomic_write_json(current / 'session.json', {'files': [], 'active': None})
            self.assertEqual(state_directory(root), current)
            self.assertEqual(load_session(current / 'session.json')['files'], [])
            self.assertEqual({p.name: p.read_bytes() for p in legacy.iterdir()}, originals)

    def test_existing_new_directory_is_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'mdview').mkdir()
            (root / 'mdview/session.json').write_text('legacy')
            current = root / 'mdviewer'
            current.mkdir()
            self.assertEqual(state_directory(root), current)
            self.assertEqual(list(current.iterdir()), [])

    def test_fresh_install_and_missing_or_corrupt_legacy_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / 'mdviewer'
            self.assertEqual(state_directory(root), current)
            self.assertFalse(current.exists())
            legacy = root / 'mdview'
            legacy.mkdir()
            (legacy / 'window.json').write_text('invalid json')
            (legacy / 'unrelated').write_text('preserve')
            self.assertEqual(state_directory(root), current)
            self.assertEqual((current / 'window.json').read_text(), 'invalid json')
            self.assertFalse((current / 'unrelated').exists())
            self.assertTrue((legacy / 'unrelated').exists())

    def test_failed_copy_keeps_legacy_usable_and_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'mdview'
            legacy.mkdir()
            (legacy / 'session.json').write_text('{"files": [], "active": null}')
            with patch('mdviewer.storage.shutil.copyfile', side_effect=OSError('copy failed')):
                with self.assertLogs(level='WARNING'):
                    self.assertEqual(state_directory(root), legacy)
            self.assertEqual(list(root.iterdir()), [legacy])
            self.assertEqual(state_directory(root), root / 'mdviewer')

    def test_concurrent_migration_preserves_the_published_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'mdview'
            legacy.mkdir()
            (legacy / 'session.json').write_text('legacy session')
            current = root / 'mdviewer'

            def concurrent_publish(staged, destination):
                current.mkdir()
                (current / 'session.json').write_text('new session')
                raise OSError(errno.ENOTEMPTY, 'Directory not empty')

            with patch.object(Path, 'rename', autospec=True, side_effect=concurrent_publish):
                self.assertEqual(state_directory(root), current)
            self.assertEqual((current / 'session.json').read_text(), 'new session')
            self.assertEqual((legacy / 'session.json').read_text(), 'legacy session')
            self.assertEqual(set(root.iterdir()), {current, legacy})


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
            with patch('mdviewer.storage.os.replace', side_effect=OSError('write failed')):
                with self.assertRaises(OSError):
                    atomic_write_json(path, {'new': True})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.iterdir()), [path])
