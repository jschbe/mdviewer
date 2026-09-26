import json
import tempfile
import unittest
from pathlib import Path

from mdview.state import load_state, save_state


class WindowStateTests(unittest.TestCase):
    def test_round_trip_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mdview" / "window.json"
            save_state(path, 1100, 800, True)
            self.assertEqual(load_state(path), {"width": 1100, "height": 800, "maximized": True})
            save_state(path, 900, 700, False)
            self.assertEqual(load_state(path), {"width": 900, "height": 700, "maximized": False})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_corrupt_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            defaults = {"width": 960, "height": 760, "maximized": False}
            self.assertEqual(load_state(path), defaults)
            for value in ("broken", "[]", json.dumps({"width": -1, "height": True, "maximized": "yes"})):
                path.write_text(value)
                self.assertEqual(load_state(path), defaults)
