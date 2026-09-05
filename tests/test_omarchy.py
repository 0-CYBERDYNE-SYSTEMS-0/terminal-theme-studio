"""colors.toml load/write/save/apply tests.

Safety: reads of real Omarchy colors.toml files are read-only; the
omarchy-theme-color binary is only ever invoked read-only on a tmp file;
omarchy-theme-set is never invoked for real (subprocess is mocked).
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import EnvHomeTestCase  # noqa: E402

from fts import omarchy, paths  # noqa: E402
from fts.omarchy import (  # noqa: E402
    apply_full_theme,
    colors_toml_text,
    list_local_themes,
    load_colors_toml,
    normalize_slug,
    save_user_theme,
)
from fts.palette import Palette  # noqa: E402

CATPPUCCIN = "/usr/share/omarchy/themes/catppuccin/colors.toml"
ANDROMEDA = os.path.expanduser("~/.config/omarchy/themes/andromeda/colors.toml")
THEME_COLOR_BIN = shutil.which("omarchy-theme-color")


def _theme_color_all(path: str) -> dict[str, str]:
    """Read-only use of the real omarchy-theme-color resolver."""
    if THEME_COLOR_BIN is None:
        raise unittest.SkipTest("omarchy-theme-color not available")
    out = subprocess.run(
        [THEME_COLOR_BIN, "--file", path, "--all"],
        capture_output=True,
        text=True,
        check=True,
    )
    resolved = {}
    for line in out.stdout.splitlines():
        key, _, value = line.partition("\t")
        resolved[key] = value
    return resolved


class TestLoadColorsToml(unittest.TestCase):
    def test_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_colors_toml("/nonexistent/nope/colors.toml")

    def test_catppuccin_stock(self):
        if not os.path.isfile(CATPPUCCIN):
            raise unittest.SkipTest("catppuccin stock theme not installed")
        p = load_colors_toml(CATPPUCCIN)
        self.assertEqual(p.background, "#1e1e2e")
        self.assertEqual(p.regular1, "#f38ba8")
        self.assertEqual(p.bright0, "#585b70")
        self.assertEqual(p.selection_bg, "#45475a")
        self.assertEqual(p.cursor, "#cdd6f4")
        self.assertEqual(p.foreground, "#cdd6f4")
        self.assertEqual(p.regular5, "#f5c2e7")
        self.assertEqual(p.bright6, "#94e2d5")

    def test_andromeda_colon_n_based(self):
        if not os.path.isfile(ANDROMEDA):
            raise unittest.SkipTest("andromeda user theme not installed")
        p = load_colors_toml(ANDROMEDA)
        self.assertEqual(p.background, "#23262e")
        self.assertEqual(p.regular1, "#f92672")
        # colorN passthrough: regular2 = color2, bright0 = color8 (muted)
        self.assertEqual(p.regular2, "#00e8c6")
        self.assertEqual(p.bright0, "#666666")
        self.assertEqual(p.selection_bg, "#d65d0e")
        # cursor <- bright_foreground <- color15 ?? foreground
        self.assertEqual(p.cursor, "#e5e5e5")
        self.assertEqual(p.regular7, "#e5e5e5")

    def test_ansi_only_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "colors.toml")
            with open(path, "w") as fh:
                fh.write(
                    'color0 = "#111111"\n'
                    'color1 = "#ff0000"\n'
                    'color2 = "#00ff00"\n'
                    'color3 = "#ffff00"\n'
                    'color4 = "#0000ff"\n'
                    'color5 = "#ff00ff"\n'
                    'color6 = "#00ffff"\n'
                    'color7 = "#eeeeee"\n'
                    'color8 = "#555555"\n'
                    'color15 = "#ffffff"\n'
                )
            p = load_colors_toml(path)
            self.assertEqual(p.background, "#111111")
            self.assertEqual(p.foreground, "#eeeeee")
            self.assertEqual(p.regular0, "#111111")
            self.assertEqual(p.regular1, "#ff0000")
            self.assertEqual(p.regular7, "#eeeeee")
            self.assertEqual(p.bright0, "#555555")
            # bright7 <- color15
            self.assertEqual(p.bright7, "#ffffff")
            # cursor <- bright_foreground <- color15 ?? foreground
            self.assertEqual(p.cursor, "#ffffff")
            # selection <- color8 ?? color0 ?? background
            self.assertEqual(p.selection_bg, "#555555")
            # brights derived: mix(colorN, #ffffff, 0.2)
            self.assertEqual(p.bright1, "#ff3333")
            self.assertEqual(p.bright2, "#33ff33")

    def test_legacy_aliases_and_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "colors.toml")
            with open(path, "w") as fh:
                fh.write(
                    "mode = 'light'\n"
                    'bg = "#222222" # inline comment\n'
                    "fg = '#dddddd'\n"
                    "red = #aa0000\n"  # unquoted value
                )
            p = load_colors_toml(path)
            self.assertEqual(p.background, "#222222")
            self.assertEqual(p.foreground, "#dddddd")
            self.assertEqual(p.regular1, "#aa0000")
            self.assertEqual(p.bright1, mix_or_bright("#aa0000"))


def mix_or_bright(red: str) -> str:
    from fts.palette import mix

    return mix(red, "#ffffff", 0.2)


class TestColorsTomlText(unittest.TestCase):
    def test_full_key_set_and_format(self):
        p = Palette.from_dict({})
        text = colors_toml_text(p)
        keys = {}
        for line in text.splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                keys[k.strip()] = v.strip()
        self.assertEqual(keys["mode"], '"dark"')
        for key in (
            "accent",
            "selection",
            "selection_foreground",
            "muted",
            "background",
            "dark_background",
            "darker_background",
            "lighter_background",
            "foreground",
            "dark_foreground",
            "light_foreground",
            "bright_foreground",
            "red",
            "green",
            "yellow",
            "blue",
            "magenta",
            "purple",
            "cyan",
            "orange",
            "brown",
            "bright_red",
            "bright_green",
            "bright_yellow",
            "bright_blue",
            "bright_magenta",
            "bright_purple",
            "bright_cyan",
        ):
            self.assertIn(key, keys, key)
        # values WITH leading '#', `key = "#rrggbb"` format
        self.assertEqual(keys["background"], '"#1e1e2e"')
        self.assertEqual(keys["accent"], '"#89b4fa"')  # accent = blue role
        self.assertEqual(keys["muted"], '"#585b70"')  # muted = bright0
        self.assertEqual(keys["bright_foreground"], '"#cdd6f4"')  # = cursor
        self.assertEqual(keys["orange"], '"#f9e2af"')  # = yellow
        self.assertEqual(keys["purple"], keys["magenta"])
        self.assertEqual(keys["bright_purple"], keys["bright_magenta"])
        self.assertEqual(keys["dark_background"], '"#171723"')
        self.assertEqual(keys["brown"], '"#7d7158"')  # mix(yellow,#000,0.5)

    def test_light_mode_default(self):
        p = Palette.from_dict({"background": "#ffffff", "foreground": "#111111"})
        self.assertIn('mode = "light"', colors_toml_text(p))
        self.assertIn('mode = "dark"', colors_toml_text(p, mode="dark"))

    def test_mode_matches_omarchy_luminance_rule(self):
        # omarchy-theme-color: light iff r+g+b > 382.  WCAG luminance would
        # call #0088ff dark; the omarchy rule says light.
        p = Palette.from_dict({"background": "#0088ff"})
        self.assertIn('mode = "light"', colors_toml_text(p))
        p = Palette.from_dict({"background": "#1e1e2e"})
        self.assertIn('mode = "dark"', colors_toml_text(p))

    def test_round_trip_against_omarchy_theme_color(self):
        """Our written file must resolve to the same palette via the real binary."""
        if not os.path.isfile(CATPPUCCIN):
            raise unittest.SkipTest("catppuccin stock theme not installed")
        p = load_colors_toml(CATPPUCCIN)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "colors.toml")
            with open(path, "w") as fh:
                fh.write(colors_toml_text(p))
            resolved = _theme_color_all(path)
        self.assertEqual(resolved["background"], "#1e1e2e")
        self.assertEqual(resolved["red"], "#f38ba8")
        self.assertEqual(resolved["color8"], "#585b70")
        self.assertEqual(resolved["accent"], "#89b4fa")
        self.assertEqual(resolved["cursor"], "#cdd6f4")
        self.assertEqual(resolved["dark_background"], "#171723")
        self.assertEqual(resolved["magenta"], "#f5c2e7")
        self.assertEqual(resolved["selection"], "#45475a")

    def test_andromeda_round_trip_against_omarchy_theme_color(self):
        if not os.path.isfile(ANDROMEDA):
            raise unittest.SkipTest("andromeda user theme not installed")
        p = load_colors_toml(ANDROMEDA)
        self.assertEqual(p.background, "#23262e")
        self.assertEqual(p.regular1, "#f92672")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "colors.toml")
            with open(path, "w") as fh:
                fh.write(colors_toml_text(p))
            resolved = _theme_color_all(path)
        self.assertEqual(resolved["background"], "#23262e")
        self.assertEqual(resolved["red"], "#f92672")
        self.assertEqual(resolved["color8"], "#666666")
        self.assertEqual(resolved["accent"], "#7cb7ff")
        self.assertEqual(resolved["cursor"], "#e5e5e5")


class TestSaveUserTheme(EnvHomeTestCase):
    def test_slug_normalization(self):
        p = Palette.from_dict({})
        path = save_user_theme(p, "My Theme")
        self.assertEqual(path.name, "colors.toml")
        self.assertEqual(
            path,
            pathlib.Path(self.tmpdir, ".config/omarchy/themes/my-theme/colors.toml"),
        )
        # name with <...> groups stripped like omarchy-theme-set:
        # "<Catppuccin> Mocha" -> " Mocha" -> " mocha" -> "-mocha"
        # (omarchy's sed leaves the leading space; tr turns it into a dash)
        path2 = save_user_theme(p, "<Catppuccin> Mocha")
        self.assertEqual(path2.parent.name, "-mocha")

    def test_rejects_dangerous_slugs(self):
        for bad in ("../evil", "..", ".", "", "a/b", "sub/dir/name"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    save_user_theme(Palette.from_dict({}), bad)

    def test_written_theme_round_trips(self):
        p = Palette.from_dict({"regular1": "#ff5555"})
        path = save_user_theme(p, "Test Theme")
        loaded = load_colors_toml(path)
        self.assertEqual(loaded, p)

    def test_overwrite_is_atomic_safe(self):
        p1 = Palette.from_dict({})
        p2 = Palette.from_dict({"background": "#000000"})
        path = save_user_theme(p1, "Twice")
        save_user_theme(p2, "Twice")
        # after the write, regular0 <- background (omarchy cascade)
        expected = Palette.from_dict({"background": "#000000", "regular0": "#000000"})
        self.assertEqual(load_colors_toml(path), expected)
        leftovers = [
            f
            for f in os.listdir(path.parent)
            if f.startswith(".") and f.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])


class TestApplyFullTheme(EnvHomeTestCase):
    def test_success_calls_binary_with_slug(self):
        with mock.patch.object(
            omarchy.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            apply_full_theme("My Theme")
        args = run.call_args[0][0]
        self.assertEqual(args[-1], "my-theme")

    def test_failure_raises_runtime_error_with_stderr(self):
        fake = mock.Mock(returncode=3, stderr="boom: no such theme\n")
        with mock.patch.object(omarchy.subprocess, "run", return_value=fake):
            with self.assertRaises(RuntimeError) as ctx:
                apply_full_theme("nope")
        self.assertIn("boom", str(ctx.exception))


class TestListLocalThemes(EnvHomeTestCase):
    def test_scans_system_and_user_dirs(self):
        p = Palette.from_dict({})
        # fake system themes under OMARCHY_PATH (…/themes/<name>/colors.toml)
        sysroot = paths.omarchy_system_themes()
        os.makedirs(os.path.join(sysroot, "good"))
        with open(os.path.join(sysroot, "good", "colors.toml"), "w") as fh:
            fh.write(colors_toml_text(p))
        os.makedirs(os.path.join(sysroot, "empty"))  # no colors.toml -> skipped
        # fake user theme
        userdir = os.path.join(self.tmpdir, ".config/omarchy/themes/mine")
        os.makedirs(userdir)
        with open(os.path.join(userdir, "colors.toml"), "w") as fh:
            fh.write(colors_toml_text(p, mode="light"))
        # fake system theme with broken colors.toml -> skipped silently
        os.makedirs(os.path.join(sysroot, "broken"))
        with open(os.path.join(sysroot, "broken", "colors.toml"), "w") as fh:
            fh.write("this is not = = valid at all\n\x00trash\n")


        entries = list_local_themes()
        by_source = {(e.source, e.name): e for e in entries}
        self.assertIn(("omarchy", "good"), by_source)
        self.assertIn(("user", "mine"), by_source)
        self.assertNotIn(("omarchy", "empty"), by_source)
        self.assertNotIn(("omarchy", "broken"), by_source)
        self.assertTrue(by_source[("omarchy", "good")].origin.endswith("good/colors.toml"))
        self.assertEqual(by_source[("user", "mine")].palette, p)

    def test_missing_dirs_yield_nothing(self):
        self.assertEqual(list_local_themes(), [])


if __name__ == "__main__":
    unittest.main()
