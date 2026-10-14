# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from mdview.zoom import clamp_zoom, step_zoom, valid_zoom


class ZoomTests(unittest.TestCase):
    def test_valid_percentages(self):
        for value in range(50, 301):
            self.assertTrue(valid_zoom(value))
        for value in (True, None, 100.0, "100", 49, 301):
            self.assertFalse(valid_zoom(value))

    def test_steps_and_boundaries(self):
        for value, lower, higher in ((100, 90, 110), (125, 120, 130), (120, 110, 130),
                                     (50, 50, 60), (51, 50, 60), (299, 290, 300),
                                     (300, 290, 300)):
            with self.subTest(value=value):
                self.assertEqual(step_zoom(value, False), lower)
                self.assertEqual(step_zoom(value, True), higher)
        for value in range(50, 301):
            lower, higher = step_zoom(value, False), step_zoom(value, True)
            self.assertTrue(50 <= lower <= value <= higher <= 300)
            self.assertEqual(lower % 10, 0)
            self.assertEqual(higher % 10, 0)
            self.assertLessEqual(higher - value, 10)
            self.assertLessEqual(value - lower, 10)

    def test_clamp_saved_values(self):
        for value, expected in ((10, 50), (49, 50), (50, 50), (125, 125), (300, 300),
                                (301, 300), (500, 300), (-100, 50), (10000, 300)):
            self.assertEqual(clamp_zoom(value), expected)
        for value in (True, None, 100.0, "100"):
            self.assertEqual(clamp_zoom(value), 100)
