"""Palette model + color math tests."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts.palette import (  # noqa: E402
    ROLE_GROUPS,
    ROLE_LABELS,
    Palette,
    ansi_index,
    hex_to_rgba,
    is_dark,
    mix,
    relative_luminance,
    rgba_to_hex,
)


class TestMix(unittest.TestCase):
    """mix() must match omarchy's awk mix_color integer math exactly."""

    @staticmethod
    def _oracle(a: str, b: str, amount: float) -> str:
        """Same integer math as omarchy-theme-color's mix_color, inline."""

        def chan(av: int, bv: int) -> int:
            return int(av * (1 - amount) + bv * amount + 0.5)

        ar, ag, ab = (int(a[i : i + 2], 16) for i in (1, 3, 5))
        br, bg, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
        return f"#{chan(ar, br):02x}{chan(ag, bg):02x}{chan(ab, bb):02x}"

    def test_known_value(self):
        # documented regression value from the spec
        self.assertEqual(mix("#1e1e2e", "#000000", 0.25), "#171723")

    def test_matches_awk_oracle(self):
        cases = [
            ("#f6b6ab", "#000000", 0.5),
            ("#1e1e2e", "#000000", 0.25),
            ("#1e1e2e", "#000000", 0.5),
            ("#1e1e2e", "#ffffff", 0.15),
            ("#89b4fa", "#ffffff", 0.2),
            ("#f9e2af", "#000000", 0.5),
            ("#23262e", "#000000", 0.25),
            ("#000000", "#ffffff", 0.001),
            ("#abcdef", "#123456", 0.37),
        ]
        for a, b, amount in cases:
            with self.subTest(a=a, b=b, amount=amount):
                self.assertEqual(mix(a, b, amount), self._oracle(a, b, amount))

    def test_extremes(self):
        self.assertEqual(mix("#112233", "#445566", 0.0), "#112233")
        self.assertEqual(mix("#112233", "#445566", 1.0), "#445566")


class TestPalette(unittest.TestCase):
    def test_defaults_are_catppuccin_mocha(self):
        d = Palette.DEFAULTS
        self.assertEqual(d["background"], "#1e1e2e")
        self.assertEqual(d["foreground"], "#cdd6f4")
        self.assertEqual(d["selection_bg"], "#45475a")
        self.assertEqual(d["regular1"], "#f38ba8")
        self.assertEqual(d["regular2"], "#a6e3a1")
        self.assertEqual(d["regular3"], "#f9e2af")
        self.assertEqual(d["regular4"], "#89b4fa")
        self.assertEqual(d["regular5"], "#f5c2e7")
        self.assertEqual(d["regular6"], "#94e2d5")
        self.assertEqual(d["bright0"], "#585b70")
        self.assertEqual(d["bright7"], "#cdd6f4")
        self.assertEqual(d["cursor"], "#cdd6f4")

    def test_from_dict_fills_missing_from_defaults(self):
        p = Palette.from_dict({"background": "#000000", "regular1": "#ff0000"})
        self.assertEqual(p.background, "#000000")
        self.assertEqual(p.regular1, "#ff0000")
        self.assertEqual(p.foreground, Palette.DEFAULTS["foreground"])
        self.assertEqual(p.bright6, Palette.DEFAULTS["bright6"])

    def test_to_dict_round_trip(self):
        p = Palette.from_dict({})
        d = p.to_dict()
        self.assertEqual(len(d), 21)
        self.assertEqual(Palette.from_dict(d), p)

    def test_from_dict_normalizes_hashless(self):
        p = Palette.from_dict({"background": "1E1E2E"})
        self.assertEqual(p.background, "#1e1e2e")

    def test_role_groups_shape(self):
        self.assertEqual(ROLE_GROUPS[0][0], "Terminal")
        self.assertEqual(len(ROLE_GROUPS[0][1]), 5)
        self.assertEqual(ROLE_GROUPS[1], ("Regular", [f"regular{i}" for i in range(8)]))
        self.assertEqual(ROLE_GROUPS[2], ("Bright", [f"bright{i}" for i in range(8)]))
        labels = [r for _, roles in ROLE_GROUPS for r in roles]
        self.assertEqual(set(ROLE_LABELS), set(labels))

    def test_labels(self):
        self.assertEqual(ROLE_LABELS["background"], "Background")
        self.assertEqual(ROLE_LABELS["regular1"], "Red")
        self.assertEqual(ROLE_LABELS["bright1"], "Bright Red")
        self.assertEqual(ROLE_LABELS["regular0"], "Black")
        self.assertEqual(ROLE_LABELS["bright7"], "Bright White")


class TestColorUtils(unittest.TestCase):
    def test_relative_luminance_extremes(self):
        self.assertAlmostEqual(relative_luminance("#000000"), 0.0)
        self.assertAlmostEqual(relative_luminance("#ffffff"), 1.0)

    def test_is_dark(self):
        self.assertTrue(is_dark("#1e1e2e"))
        self.assertTrue(is_dark("#000000"))
        self.assertFalse(is_dark("#ffffff"))
        self.assertFalse(is_dark("#f5eee6"))

    def test_hex_to_rgba(self):
        self.assertEqual(hex_to_rgba("#ff8000"), (1.0, 128 / 255, 0.0, 1.0))
        self.assertEqual(hex_to_rgba("#f00"), (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(hex_to_rgba("#00000000")[3], 0.0)

    def test_rgba_to_hex(self):
        self.assertEqual(rgba_to_hex(1.0, 128 / 255, 0.0), "#ff8000")
        self.assertEqual(rgba_to_hex(1.5, -0.5, 0.0), "#ff0000")
        self.assertEqual(rgba_to_hex(0, 0, 0, a=0.0), "#000000")

    def test_ansi_index(self):
        self.assertEqual(ansi_index("regular0"), 0)
        self.assertEqual(ansi_index("regular7"), 7)
        self.assertEqual(ansi_index("bright0"), 8)
        self.assertEqual(ansi_index("bright7"), 15)
        with self.assertRaises(ValueError):
            ansi_index("background")
        with self.assertRaises(ValueError):
            ansi_index("regular8")
        with self.assertRaises(ValueError):
            ansi_index("")


if __name__ == "__main__":
    unittest.main()
