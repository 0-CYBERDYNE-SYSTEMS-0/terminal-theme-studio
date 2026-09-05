"""Quantize tests (pure python; no GTK needed)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts.palette import Palette, mix  # noqa: E402
from fts.quantize import median_cut, palette_from_colors  # noqa: E402


def _repeat(colors, n=40):
    return [c for c in colors for _ in range(n)]


class TestMedianCut(unittest.TestCase):
    def test_recovers_four_solid_regions(self):
        regions = [(10, 10, 10), (220, 40, 40), (40, 220, 40), (40, 40, 220)]
        pixels = _repeat(regions, 40)
        means = median_cut(pixels, 4)
        self.assertEqual(len(means), 4)
        for want in regions:
            close = [
                m
                for m in means
                if all(abs(m[i] - want[i]) <= 2 for i in range(3))
            ]
            self.assertTrue(close, f"{want} not recovered in {means}")

    def test_weighted_by_pixel_count(self):
        # 90% dark pixels + a few bright ones -> dominant dark mean kept
        pixels = _repeat([(5, 5, 5)], 900) + _repeat([(250, 250, 250)], 100)
        means = median_cut(pixels, 2)
        self.assertEqual(len(means), 2)
        darks = [m for m in means if sum(m) < 300]
        self.assertTrue(any(all(abs(v - 5) <= 2 for v in m) for m in darks))

    def test_k_larger_than_distinct_colors(self):
        pixels = _repeat([(1, 2, 3)], 10)
        means = median_cut(pixels, 8)
        self.assertEqual(means, [(1, 2, 3)])

    def test_empty_and_zero_k(self):
        self.assertEqual(median_cut([], 4), [])
        self.assertEqual(median_cut([(1, 1, 1)], 0), [])

    def test_output_sorted_dark_to_light(self):
        pixels = _repeat([(250, 250, 250)], 10) + _repeat([(10, 10, 10)], 10)
        means = median_cut(pixels, 2)
        lums = [sum(m) for m in means]
        self.assertEqual(lums, sorted(lums))


class TestPaletteFromColors(unittest.TestCase):
    def setUp(self):
        self.colors = [
            "#141420",  # darkest -> background
            "#f2f2f6",  # lightest -> foreground
            "#cc2222",  # red
            "#22cc55",  # green
            "#2255cc",  # blue
            "#cccc33",  # yellow
            "#22bbbb",  # cyan
            "#bb44bb",  # magenta
        ]
        self.p = palette_from_colors(self.colors)

    def test_darkest_background_lightest_foreground(self):
        self.assertEqual(self.p.background, "#141420")
        self.assertEqual(self.p.regular0, "#141420")
        self.assertEqual(self.p.foreground, "#f2f2f6")
        self.assertEqual(self.p.regular7, "#f2f2f6")
        self.assertEqual(self.p.cursor, "#f2f2f6")
        self.assertEqual(self.p.bright7, "#f2f2f6")

    def test_reddest_saturated_becomes_regular1(self):
        self.assertEqual(self.p.regular1, "#cc2222")

    def test_hue_slots(self):
        self.assertEqual(self.p.regular2, "#22cc55")  # green
        self.assertEqual(self.p.regular3, "#cccc33")  # yellow
        self.assertEqual(self.p.regular4, "#2255cc")  # blue
        self.assertEqual(self.p.regular5, "#bb44bb")  # magenta
        self.assertEqual(self.p.regular6, "#22bbbb")  # cyan

    def test_selection_and_muted(self):
        self.assertEqual(self.p.selection_bg, mix("#141420", "#f2f2f6", 0.25))
        self.assertEqual(self.p.selection_fg, "#f2f2f6")
        # dark background -> bright0 mixed toward white
        self.assertEqual(self.p.bright0, mix("#141420", "#ffffff", 0.35))

    def test_brights_derived_when_no_leftovers(self):
        p = palette_from_colors(["#101018", "#eeeeee"])
        self.assertEqual(p.background, "#101018")
        self.assertEqual(p.foreground, "#eeeeee")
        for i in range(1, 7):
            self.assertEqual(
                p.to_dict()[f"bright{i}"],
                mix(p.to_dict()[f"regular{i}"], "#ffffff", 0.2),
            )

    def test_all_roles_valid_hex(self):
        import re

        for role, value in self.p.to_dict().items():
            self.assertRegex(value, r"^#[0-9a-f]{6}$", f"{role}={value}")

    def test_empty_input_returns_defaults(self):
        p = palette_from_colors([])
        self.assertEqual(p, Palette.from_dict({}))


if __name__ == "__main__":
    unittest.main()
