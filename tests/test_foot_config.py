"""foot_config tests: palette.ini text + foot.ini include management.

All paths are redirected to a tmpdir via FOOT_THEME_STUDIO_HOME; the real
~/.config/foot is never touched.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import EnvHomeTestCase  # noqa: E402

from fts import foot_config, paths  # noqa: E402
from fts.foot_config import (  # noqa: E402
    MARK_BEGIN,
    MARK_END,
    clear_palette_override,
    ensure_include,
    palette_ini_text,
    write_palette_override,
)
from fts.palette import Palette  # noqa: E402

OMARCHY_INCLUDE = "include=~/.local/state/omarchy/current/theme/foot.ini\n"

ORIGINAL_INI = (
    "[main]\n"
    + OMARCHY_INCLUDE
    + "term=xterm-256color\n"
    + "font=JetBrainsMono Nerd Font:size=9\n"
    "\n"
    "[scrollback]\n"
    "lines=10000\n"
)


def read(path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


class TestPaletteIniText(unittest.TestCase):
    def test_section_and_key_set(self):
        p = Palette.from_dict({})
        text = palette_ini_text(p)
        self.assertIn("[colors-dark]", text)
        for i in range(8):
            self.assertIn(f"regular{i}=", text)
            self.assertIn(f"bright{i}=", text)
        self.assertIn("foreground=cdd6f4", text)
        self.assertIn("background=1e1e2e", text)
        self.assertIn("selection-foreground=cdd6f4", text)
        self.assertIn("selection-background=45475a", text)

    def test_no_hash_in_values(self):
        text = palette_ini_text(Palette.from_dict({}))
        for line in text.splitlines():
            if line and not line.startswith("[") and not line.startswith("#"):
                self.assertNotIn("#", line, line)

    def test_cursor_line_two_fields(self):
        text = palette_ini_text(Palette.from_dict({}))
        cursor = next(
            line for line in text.splitlines() if line.startswith("cursor=")
        )
        fields = cursor[len("cursor=") :].split()
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields, ["1e1e2e", "cdd6f4"])  # bg then cursor fg

    def test_custom_palette_values(self):
        p = Palette.from_dict({"background": "#abcdef", "bright3": "#123456"})
        text = palette_ini_text(p)
        self.assertIn("background=abcdef", text)
        self.assertIn("bright3=123456", text)
        self.assertIn("cursor=abcdef", text)


class TestEnsureInclude(EnvHomeTestCase):
    def test_inserts_block_at_end_after_omarchy_include(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)

        ensure_include()

        text = read(ini)
        self.assertIn(MARK_BEGIN, text)
        self.assertIn(MARK_END, text)
        self.assertIn(f"include={paths.palette_ini()}", text)
        self.assertIn("[main]", text)
        # omarchy include comes first, studio block at the end
        self.assertLess(
            text.index(OMARCHY_INCLUDE.strip()), text.index(MARK_BEGIN)
        )
        block = text[text.index(MARK_BEGIN) :]
        self.assertEqual(text.count(MARK_BEGIN), 1)
        self.assertTrue(block.startswith(MARK_BEGIN))
        self.assertTrue(text.rstrip("\n").endswith(MARK_END))

    def test_idempotent_and_other_content_byte_identical(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)

        ensure_include()
        after_first = read(ini)
        ensure_include()
        after_second = read(ini)
        self.assertEqual(after_first, after_second)
        self.assertEqual(after_second.count(MARK_BEGIN), 1)

        # everything except the appended block is byte-identical
        block_start = after_second.index(MARK_BEGIN)
        self.assertEqual(
            after_second[:block_start],
            ORIGINAL_INI + "\n",
        )

    def test_replaces_existing_block_in_place(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)
        ensure_include()
        first = read(ini)
        # simulate a palette.ini path change by rewriting the block manually
        stale = first.replace(
            f"include={paths.palette_ini()}", "include=/stale/old/palette.ini"
        )
        with open(ini, "w") as fh:
            fh.write(stale)
        ensure_include()
        self.assertEqual(read(ini), first)

    def test_creates_missing_foot_ini(self):
        self.assertFalse(paths.foot_config().exists())
        ensure_include()
        text = read(paths.foot_config())
        self.assertIn(MARK_BEGIN, text)
        self.assertIn("[main]", text)
        self.assertIn(f"include={paths.palette_ini()}", text)

    def test_bak_created_once_before_first_modification(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)
        ensure_include()
        bak = ini.with_name(ini.name + ".bak")
        self.assertTrue(bak.exists())
        self.assertEqual(read(bak), ORIGINAL_INI)
        ensure_include()
        clear_palette_override()
        ensure_include()
        # bak still holds the pristine original
        self.assertEqual(read(bak), ORIGINAL_INI)

    def test_no_bak_when_created_fresh(self):
        ensure_include()
        self.assertFalse(
            paths.foot_config().with_name(paths.foot_config().name + ".bak").exists()
        )

    def test_misplaced_block_is_relocated_to_end(self):
        # A block parsed BEFORE omarchy's include would lose (later parse
        # wins); ensure_include must move it after every include= line.
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        misplaced = (
            "[main]\n"
            + f"{MARK_BEGIN}\n[main]\ninclude={paths.palette_ini()}\n{MARK_END}\n"
            + OMARCHY_INCLUDE
            + "term=xterm-256color\n"
        )
        with open(ini, "w") as fh:
            fh.write(misplaced)
        ensure_include()
        text = read(ini)
        block_end = text.index(MARK_END)
        omarchy_at = text.index(OMARCHY_INCLUDE)
        self.assertGreater(block_end, omarchy_at)
        self.assertEqual(text.count(MARK_BEGIN), 1)

    def test_multiple_stale_blocks_collapse_to_one(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        doubled = (
            ORIGINAL_INI
            + "\n"
            + f"{MARK_BEGIN}\n[main]\ninclude=/stale/a.ini\n{MARK_END}\n"
            + "\n"
            + f"{MARK_BEGIN}\n[main]\ninclude=/stale/b.ini\n{MARK_END}\n"
        )
        with open(ini, "w") as fh:
            fh.write(doubled)
        ensure_include()
        text = read(ini)
        self.assertEqual(text.count(MARK_BEGIN), 1)
        self.assertIn(f"include={paths.palette_ini()}", text)
        self.assertNotIn("/stale/a.ini", text)
        self.assertNotIn("/stale/b.ini", text)
        clear_palette_override()
        self.assertNotIn(MARK_BEGIN, read(ini))
        self.assertEqual(read(ini), ORIGINAL_INI)


class TestClearOverride(EnvHomeTestCase):
    def test_clear_removes_block_and_palette_ini(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)
        p = Palette.from_dict({})
        write_palette_override(p)
        self.assertTrue(paths.palette_ini().exists())
        self.assertIn(MARK_BEGIN, read(ini))

        clear_palette_override()

        self.assertFalse(paths.palette_ini().exists())
        self.assertNotIn(MARK_BEGIN, read(ini))
        self.assertNotIn(MARK_END, read(ini))
        self.assertEqual(read(ini), ORIGINAL_INI)

    def test_clear_without_anything_is_noop(self):
        clear_palette_override()  # must not raise
        self.assertFalse(paths.foot_config().exists())

    def test_clear_leaves_user_content_without_block(self):
        ini = paths.foot_config()
        ini.parent.mkdir(parents=True, exist_ok=True)
        with open(ini, "w") as fh:
            fh.write(ORIGINAL_INI)
        clear_palette_override()
        self.assertEqual(read(ini), ORIGINAL_INI)

    def test_write_override_round_trip(self):
        p = Palette.from_dict({"regular1": "#ff0000"})
        write_palette_override(p)
        text = read(paths.palette_ini())
        self.assertIn("regular1=ff0000", text)
        self.assertIn("[colors-dark]", text)


if __name__ == "__main__":
    unittest.main()
