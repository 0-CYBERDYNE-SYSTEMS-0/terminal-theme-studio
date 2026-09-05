"""Library tests: bundled palettes, local scan, search."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import EnvHomeTestCase  # noqa: E402

from fts import library, omarchy  # noqa: E402
from fts.library import LibraryEntry, load_all, load_bundled, search  # noqa: E402
from fts.palette import Palette  # noqa: E402


class TestBundled(unittest.TestCase):
    def setUp(self):
        self.entries = load_bundled()

    def test_at_least_300_entries(self):
        # data/palettes.json is vendored from Gogh's themes.json
        self.assertGreaterEqual(len(self.entries), 300)

    def test_all_palettes_parse(self):
        for entry in self.entries[:50]:  # spot-check subset for speed
            with self.subTest(name=entry.name):
                d = entry.palette.to_dict()
                self.assertEqual(len(d), 21)
                for role, value in d.items():
                    self.assertRegex(value, r"^#[0-9a-f]{6}$", f"{role}={value}")

    def test_entry_shape(self):
        e = self.entries[0]
        self.assertIsInstance(e, LibraryEntry)
        self.assertEqual(e.source, "community")
        self.assertTrue(e.name)
        self.assertTrue(e.origin)


class TestSearch(unittest.TestCase):
    def test_filters_case_insensitive(self):
        entries = load_bundled()
        hits = search(entries, "GRUV")
        self.assertTrue(hits)
        for e in hits:
            self.assertIn("gruv", e.name.lower())

    def test_empty_query_returns_all(self):
        entries = load_bundled()
        self.assertEqual(search(entries, ""), entries)
        self.assertEqual(search(entries, "   "), entries)

    def test_no_match(self):
        entries = load_bundled()
        self.assertEqual(search(entries, "zzzznotathemezzzz"), [])


class TestLoadAll(EnvHomeTestCase):
    def test_bundled_plus_local(self):
        # fake one user theme
        userdir = os.path.join(self.tmpdir, ".config/omarchy/themes/localguy")
        os.makedirs(userdir)
        with open(os.path.join(userdir, "colors.toml"), "w") as fh:
            fh.write(omarchy.colors_toml_text(Palette.from_dict({})))
        entries = load_all()
        sources = {e.source for e in entries}
        self.assertIn("community", sources)
        self.assertIn("user", sources)
        names = {e.name for e in entries if e.source == "user"}
        self.assertIn("localguy", names)


if __name__ == "__main__":
    unittest.main()
