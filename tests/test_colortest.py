"""colortest generator tests."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts.colortest import full_test_text, script_text  # noqa: E402
from fts.palette import Palette  # noqa: E402


class TestFullTestText(unittest.TestCase):
    def setUp(self):
        self.text = full_test_text(Palette.from_dict({}))

    def test_nonempty_and_markers(self):
        self.assertTrue(self.text.strip())
        self.assertIn("16 ANSI", self.text)
        self.assertIn("6x6x6", self.text)
        self.assertIn("grayscale", self.text.lower())
        self.assertIn("truecolor gradient", self.text.lower())

    def test_contains_16_block_rows_and_cube_rows(self):
        self.assertIn("[ 0]", self.text)
        self.assertIn("[15]", self.text)
        self.assertIn("r=0 |", self.text)
        self.assertIn("r=5 |", self.text)

    def test_uses_truecolor_sgr(self):
        self.assertIn("\x1b[48;2;", self.text)
        self.assertIn("\x1b[0m", self.text)

    def test_cube_values_spot_check(self):
        # cell 16 = (0,0,0), cell 231 = (255,255,255)
        self.assertIn("48;2;0;0;0m", self.text)
        self.assertIn("48;2;255;255;255m", self.text)

    def test_custom_palette_reflected(self):
        p = Palette.from_dict({"regular1": "#ff0102"})
        self.assertIn("#ff0102", full_test_text(p))


class TestScriptText(unittest.TestCase):
    def setUp(self):
        self.script = script_text(Palette.from_dict({}))

    def test_shebang_and_posix(self):
        self.assertTrue(self.script.startswith("#!/bin/sh"))

    def test_contains_same_sections(self):
        self.assertIn("16 ANSI", self.script)
        self.assertIn("6x6x6", self.script)
        self.assertIn("grayscale", self.script.lower())
        self.assertIn("truecolor", self.script.lower())

    def test_embeds_palette_truecolor_values(self):
        self.assertIn("48;2;", self.script)
        self.assertIn("#!/bin/sh", self.script.splitlines()[0])

    def test_passes_sh_syntax_check(self):
        # sh -n parses the script without executing it
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sh", delete=False
        ) as fh:
            fh.write(self.script)
            path = fh.name
        try:
            proc = subprocess.run(
                ["sh", "-n", path], capture_output=True, text=True
            )
            self.assertEqual(
                proc.returncode, 0, f"sh -n failed: {proc.stderr}"
            )
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
