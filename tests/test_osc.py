"""OSC building tests. push_to_running_foot is NEVER executed here."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts.osc import osc_bytes  # noqa: E402
from fts.palette import Palette  # noqa: E402


class TestOscBytes(unittest.TestCase):
    def setUp(self):
        self.p = Palette.from_dict({})
        self.data = osc_bytes(self.p)
        self.text = self.data.decode("ascii")

    def test_starts_with_foreground(self):
        self.assertTrue(self.text.startswith("\x1b]10;"))
        self.assertTrue(self.data.startswith(b"\x1b]10;#cdd6f4\x07"))

    def test_contains_all_codes(self):
        for snippet in (
            "\x1b]11;#1e1e2e\x07",
            "\x1b]12;#cdd6f4\x07",
            "\x1b]17;#45475a\x07",
            "\x1b]19;#cdd6f4\x07",
        ):
            self.assertIn(snippet, self.text, snippet)

    def test_contains_ansi_0_to_15(self):
        for i in range(16):
            self.assertIn(f"\x1b]4;{i};", self.text)
        self.assertIn("\x1b]4;0;#1e1e2e\x07", self.text)  # regular0 = bg
        self.assertIn("\x1b]4;1;#f38ba8\x07", self.text)  # regular1 = red
        self.assertIn("\x1b]4;8;#585b70\x07", self.text)  # bright0 = muted
        self.assertIn("\x1b]4;15;#cdd6f4\x07", self.text)  # bright7

    def test_bel_terminated(self):
        self.assertTrue(self.data.endswith(b"\x07"))
        self.assertNotIn("\x1b\\", self.text)  # no ST terminator

    def test_hex_has_hash_and_matches_roles(self):
        import re

        pairs = re.findall(r"\x1b\]4;(\d+);(#[0-9a-f]{6})\x07", self.text)
        self.assertEqual(len(pairs), 16)
        roles = [f"regular{i}" for i in range(8)] + [
            f"bright{i}" for i in range(8)
        ]
        for (idx, hexval), role in zip(pairs, roles):
            with self.subTest(role=role):
                self.assertEqual(int(idx), roles.index(role))
                self.assertEqual(hexval, getattr(self.p, role))

    def test_custom_palette(self):
        p = Palette.from_dict({"foreground": "#010203", "bright5": "#0a0b0c"})
        text = osc_bytes(p).decode("ascii")
        self.assertIn("\x1b]10;#010203\x07", text)
        self.assertIn("\x1b]4;13;#0a0b0c\x07", text)


if __name__ == "__main__":
    unittest.main()
