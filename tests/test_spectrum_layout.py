"""In-app color-test canvas geometry: must fit every band inside width."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts.colortest import SpectrumGeom, spectrum_geom  # noqa: E402

_WIDTHS = (320, 400, 520, 600, 720, 760, 900, 941, 1200, 1600)


class TestSpectrumGeom(unittest.TestCase):
    def test_bands_never_exceed_avail(self) -> None:
        for width in _WIDTHS:
            with self.subTest(width=width):
                geom = spectrum_geom(width)
                self.assertIsInstance(geom, SpectrumGeom)
                self.assertLessEqual(geom.ansi_row_width, geom.avail + 1e-6)
                self.assertLessEqual(geom.cube_row_width, geom.avail + 1e-6)
                self.assertAlmostEqual(geom.ansi_row_width, geom.avail, places=6)
                self.assertLessEqual(2 * geom.margin + geom.avail, width + 1e-6)
                self.assertGreater(geom.height, 0)
                self.assertGreater(geom.cube_cell, 0)
                self.assertGreater(geom.ansi_cell_w, 0)

    def test_narrow_window_still_fits_the_36_cell_cube(self) -> None:
        geom = spectrum_geom(400)
        self.assertLessEqual(geom.cube_row_width, geom.avail + 1e-6)
        self.assertEqual(geom.margin, 12.0)

    def test_wide_window_caps_cube_cells(self) -> None:
        geom = spectrum_geom(1600)
        self.assertEqual(geom.cube_cell, 24.0)
        self.assertEqual(geom.margin, 24.0)

    def test_zero_and_tiny_widths_do_not_crash(self) -> None:
        for width in (0, 1, 64, 200):
            geom = spectrum_geom(width)
            self.assertGreaterEqual(geom.avail, 64.0)
            self.assertGreater(geom.height, 0)
            self.assertLessEqual(geom.cube_row_width, geom.avail + 1e-6)

    def test_tiled_half_hd_matches_the_overflow_bug(self) -> None:
        # The studio was 941px tiled beside another pane; 900px canvas +
        # 940px dialog chrome ran off the right edge. Geometry at that
        # width must keep every band on-canvas.
        geom = spectrum_geom(941)
        self.assertLessEqual(geom.cube_row_width, geom.avail + 1e-6)
        self.assertLessEqual(geom.ansi_row_width, 941)


if __name__ == "__main__":
    unittest.main()
