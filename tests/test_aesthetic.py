"""Aesthetic derivation and wallpaper prompt building tests.

Pure functions only -- no gi, no network, deterministic buckets.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts import aesthetic  # noqa: E402
from fts.palette import Palette, is_dark  # noqa: E402


def _palette(background: str, accents: list[str]) -> Palette:
    """A palette from a background + six accent colors (regular/bright 1-6)."""
    data = {
        "background": background,
        "foreground": "#eeeeee" if is_dark(background) else "#111111",
        "cursor": "#ffffff",
        "selection_bg": "#444444",
        "selection_fg": "#eeeeee",
    }
    for i, hexcolor in enumerate(accents):
        data[f"regular{i + 1}"] = hexcolor
        data[f"bright{i + 1}"] = hexcolor
    return Palette.from_dict(data)


class TestDeriveAesthetic(unittest.TestCase):
    def test_dark_monochrome(self):
        grays = ["#909090"] * 6
        self.assertEqual(
            aesthetic.derive_aesthetic(_palette("#101010", grays)),
            "dark moody monochrome",
        )

    def test_light_monochrome(self):
        grays = ["#a0a0a0"] * 6
        self.assertEqual(
            aesthetic.derive_aesthetic(_palette("#f0f0f0", grays)),
            "clean minimal daylight",
        )

    def test_dark_single_hue_warm(self):
        self.assertEqual(
            aesthetic.derive_aesthetic(_palette("#100800", ["#ff5500"] * 6)),
            "rich saturated neon dusk, warm tones",
        )

    def test_dark_single_hue_cool(self):
        self.assertEqual(
            aesthetic.derive_aesthetic(_palette("#000810", ["#2266ff"] * 6)),
            "rich saturated neon dusk, cool tones",
        )

    def test_dark_multihue_vivid(self):
        rainbow = ["#ff0044", "#00ff66", "#ffdd00", "#0066ff", "#ff00ff", "#00ffff"]
        phrase = aesthetic.derive_aesthetic(_palette("#0a0e14", rainbow))
        self.assertTrue(
            phrase.startswith("vibrant neon nightscape"),
            f"unexpected phrase: {phrase!r}",
        )

    def test_default_catppuccin_is_dark_phrase(self):
        phrase = aesthetic.derive_aesthetic(Palette.from_dict(Palette.DEFAULTS))
        self.assertIn(phrase.split(",")[0], {
            "dark moody monochrome",
            "deep atmospheric twilight",
            "colorful midnight aurora",
            "rich saturated neon dusk",
            "vibrant neon nightscape",
        }, f"unexpected phrase: {phrase!r}")

    def test_deterministic(self):
        rainbow = ["#ff0044", "#00ff66", "#ffdd00", "#0066ff", "#ff00ff", "#00ffff"]
        palette = _palette("#0a0e14", rainbow)
        self.assertEqual(
            aesthetic.derive_aesthetic(palette), aesthetic.derive_aesthetic(palette)
        )


class TestAccentSwatches(unittest.TestCase):
    def test_picks_distinct_hues(self):
        rainbow = ["#ff0044", "#00ff66", "#ffdd00", "#0066ff", "#ff00ff", "#00ffff"]
        picked = aesthetic.accent_swatches(_palette("#0a0e14", rainbow), 4)
        self.assertEqual(len(picked), 4)
        base_names = {"Red", "Green", "Yellow", "Blue", "Magenta", "Cyan"}
        for name, hexcolor in picked:
            self.assertIn(hexcolor, rainbow)
            self.assertTrue(
                name in base_names or name[len("Bright "):] in base_names,
                f"unexpected accent name: {name!r}",
            )

    def test_collapses_duplicate_hues(self):
        picked = aesthetic.accent_swatches(_palette("#000810", ["#2266ff"] * 6), 4)
        self.assertEqual(len(picked), 1)
        self.assertEqual(picked[0][1], "#2266ff")


class TestBuildPrompt(unittest.TestCase):
    def test_prompt_parts(self):
        palette = Palette.from_dict(Palette.DEFAULTS)
        prompt = aesthetic.build_prompt("misty pine forest", palette, "16:9")
        self.assertIn("misty pine forest", prompt)
        self.assertIn("16:9", prompt)
        self.assertIn(palette.background, prompt)
        self.assertIn("No text", prompt)
        self.assertIn("watermark", prompt)

    def test_prompt_embeds_accent_hexes(self):
        palette = _palette("#0a0e14", ["#ff0044", "#00ff66", "#ffdd00",
                                       "#0066ff", "#ff00ff", "#00ffff"])
        prompt = aesthetic.build_prompt("vapor", palette, "21:9")
        self.assertIn("#ff0044", prompt)
        self.assertIn("21:9", prompt)

    def test_negative_prompt(self):
        self.assertIn("watermark", aesthetic.negative_prompt())
        self.assertIn("text", aesthetic.negative_prompt())


if __name__ == "__main__":
    unittest.main()
