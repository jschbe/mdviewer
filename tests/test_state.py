# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

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
            self.assertEqual(load_state(path), {"width": 1100, "height": 800, "maximized": True, "zoom": 100})
            save_state(path, 900, 700, False)
            self.assertEqual(load_state(path), {"width": 900, "height": 700, "maximized": False, "zoom": 100})
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_corrupt_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            defaults = {"width": 960, "height": 760, "maximized": False, "zoom": 100}
            self.assertEqual(load_state(path), defaults)
            for value in ("broken", "[]", json.dumps({"width": -1, "height": True, "maximized": "yes"})):
                path.write_text(value)
                self.assertEqual(load_state(path), defaults)

    def test_zoom_persistence_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            for zoom in (50, 125, 300):
                save_state(path, 960, 760, False, zoom)
                self.assertEqual(load_state(path)["zoom"], zoom)
            for zoom in (None, True, "125", 125.0):
                path.write_text(json.dumps({"zoom": zoom}))
                self.assertEqual(load_state(path)["zoom"], 100)
                save_state(path, 960, 760, False, zoom)
                self.assertEqual(load_state(path)["zoom"], 100)
            # Window state written by earlier releases remains compatible.
            path.write_text(json.dumps({"width": 1234, "height": 800, "maximized": True}))
            self.assertEqual(load_state(path), {"width": 1234, "height": 800,
                                                "maximized": True, "zoom": 100})

    def test_clamp_old_zoom_without_changing_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "window.json"
            for zoom, expected in ((10, 50), (49, 50), (301, 300), (500, 300)):
                path.write_text(json.dumps({"width": 1234, "height": 800,
                                            "maximized": True, "zoom": zoom}))
                self.assertEqual(load_state(path), {"width": 1234, "height": 800,
                                                    "maximized": True, "zoom": expected})
                save_state(path, 1234, 800, True, zoom)
                self.assertEqual(json.loads(path.read_text())["zoom"], expected)
