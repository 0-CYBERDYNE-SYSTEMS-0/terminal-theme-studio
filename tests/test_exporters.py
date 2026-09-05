"""exporter tests: pure palette -> theme-file renderers.

No filesystem or display needed; every renderer must be deterministic,
end with a newline, and follow the target format's hex conventions
(foot bare, everything else '#rrggbb').
"""

import json
import os
import sys
import tomllib
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts import exporters  # noqa: E402
from fts.palette import Palette  # noqa: E402


def rendered(fmt: str) -> str:
    return exporters.render(fmt, Palette.from_dict({}), "Test Theme")


class TestRegistry(unittest.TestCase):
    def test_ids_unique_and_renderable(self):
        ids = [spec.id for spec in exporters.FORMATS]
        self.assertEqual(len(ids), len(set(ids)))
        for fmt in ids:
            self.assertIsInstance(rendered(fmt), str)

    def test_render_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            exporters.render("nope", Palette.from_dict({}))

    def test_suggested_basename_uses_slug_and_ext(self):
        self.assertEqual(
            exporters.suggested_basename("alacritty", "My Theme!"),
            "my-theme.toml",
        )
        # unsluggable title falls back to the format's default filename
        self.assertEqual(
            exporters.suggested_basename("foot", "///"), "foot.ini"
        )


class TestCommonProperties(unittest.TestCase):
    def test_deterministic_and_trailing_newline(self):
        for spec in exporters.FORMATS:
            out = rendered(spec.id)
            self.assertTrue(out.endswith("\n"), spec.id)
            self.assertEqual(out, rendered(spec.id), spec.id)

    def test_title_and_studio_appear(self):
        for spec in exporters.FORMATS:
            text = rendered(spec.id)
            if spec.id == "json":
                self.assertEqual(json.loads(text)["name"], "Test Theme")
            else:
                self.assertIn("Foot Theme Studio", text)

    def test_ansi_mapping_all_16_indices(self):
        """ghostty palette lines cover indices 0-15: regular0-7 then bright0-7."""
        p = Palette.from_dict({})
        entries = {}
        for line in rendered("ghostty").splitlines():
            if line.startswith("palette = "):
                index, value = line.removeprefix("palette = ").split("=", 1)
                entries[index] = value
        self.assertEqual(len(entries), 16)
        for i in range(8):
            self.assertEqual(entries[str(i)], getattr(p, f"regular{i}"))
            self.assertEqual(entries[str(i + 8)], getattr(p, f"bright{i}"))


class TestFoot(unittest.TestCase):
    def setUp(self):
        self.text = rendered("foot")

    def test_matches_palette_ini_key_lines(self):
        """Same key=value lines as the studio's own palette.ini override."""
        from fts.foot_config import palette_ini_text

        def key_lines(text):
            return [
                line for line in text.splitlines()
                if line and not line.startswith("#") and not line.startswith("[")
            ]

        self.assertEqual(
            key_lines(self.text), key_lines(palette_ini_text(Palette.from_dict({})))
        )

    def test_no_hash_in_values(self):
        body = [
            line for line in self.text.splitlines()
            if line and not line.startswith("#") and not line.startswith("[")
        ]
        for line in body:
            value = line.split("=", 1)[1]
            self.assertNotIn("#", value)


class TestAlacritty(unittest.TestCase):
    def setUp(self):
        self.text = rendered("alacritty")
        self.data = tomllib.loads(self.text)

    def test_parses_as_toml_with_expected_sections(self):
        colors = self.data["colors"]
        for section in ("primary", "cursor", "vi_mode_cursor", "selection",
                        "normal", "bright"):
            self.assertIn(section, colors)

    def test_hashed_hex_and_role_mapping(self):
        colors = self.data["colors"]
        self.assertEqual(colors["primary"]["background"], "#1e1e2e")
        self.assertEqual(colors["primary"]["foreground"], "#cdd6f4")
        # cursor text = background, cursor block = cursor (Omarchy convention)
        self.assertEqual(colors["cursor"]["text"], "#1e1e2e")
        self.assertEqual(colors["cursor"]["cursor"], "#cdd6f4")
        self.assertEqual(colors["selection"]["background"], "#45475a")
        self.assertEqual(colors["normal"]["red"], "#f38ba8")
        self.assertEqual(colors["bright"]["black"], "#585b70")


class TestGhostty(unittest.TestCase):
    def setUp(self):
        self.text = rendered("ghostty")

    def test_semantic_keys_and_palette_indices(self):
        self.assertIn("background = #1e1e2e", self.text)
        self.assertIn("cursor-color = #cdd6f4", self.text)
        self.assertIn("selection-background = #45475a", self.text)
        p = Palette.from_dict({})
        self.assertIn(f"palette = 1={p.regular1}", self.text)
        self.assertIn(f"palette = 8={p.bright0}", self.text)
        self.assertIn(f"palette = 15={p.bright7}", self.text)


class TestKitty(unittest.TestCase):
    def setUp(self):
        self.text = rendered("kitty")

    def test_keys_and_color_indices(self):
        p = Palette.from_dict({})
        self.assertIn(f"cursor = {p.cursor}", self.text)
        self.assertIn(f"cursor_text_color = {p.background}", self.text)
        self.assertIn(f"selection_background = {p.selection_bg}", self.text)
        self.assertIn(f"color1 = {p.regular1}", self.text)
        self.assertIn(f"color15 = {p.bright7}", self.text)


class TestWezTerm(unittest.TestCase):
    def setUp(self):
        self.text = rendered("wezterm")

    def test_scheme_table_shape(self):
        for key in ("foreground", "background", "cursor_bg", "cursor_fg",
                    "cursor_border", "selection_fg", "selection_bg"):
            self.assertRegex(
                self.text, rf"(?m)^\s+{key} = '#[0-9a-f]{{6}}',$"
            )
        self.assertIn("ansi = {", self.text)
        self.assertIn("brights = {", self.text)
        self.assertTrue(self.text.rstrip().endswith("return colors"))

    def test_cursor_fg_is_background(self):
        p = Palette.from_dict({})
        self.assertIn(f"cursor_fg = '{p.background}'", self.text)
        self.assertIn(f"cursor_bg = '{p.cursor}'", self.text)


class TestJson(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(rendered("json"))

    def test_round_trips_all_21_roles(self):
        palette = Palette.from_dict(self.data)
        self.assertEqual(palette, Palette.from_dict({}))
        self.assertEqual(self.data["name"], "Test Theme")


if __name__ == "__main__":
    unittest.main()
