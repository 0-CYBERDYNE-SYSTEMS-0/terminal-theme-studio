"""paths indirection tests."""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import EnvHomeTestCase  # noqa: E402

from fts import paths  # noqa: E402


class TestPaths(EnvHomeTestCase):
    def test_home_redirect(self):
        self.assertEqual(paths.home(), pathlib.Path(self.tmpdir))

    def test_foot_paths(self):
        self.assertEqual(
            paths.foot_config(),
            pathlib.Path(self.tmpdir, ".config/foot/foot.ini"),
        )
        self.assertEqual(
            paths.palette_ini(),
            pathlib.Path(self.tmpdir, ".config/foot/palette.ini"),
        )

    def test_omarchy_paths(self):
        self.assertEqual(
            paths.omarchy_user_themes(),
            pathlib.Path(self.tmpdir, ".config/omarchy/themes"),
        )
        self.assertEqual(
            paths.omarchy_system_themes(),
            pathlib.Path(self.tmpdir, "omarchy-fake/themes"),
        )
        self.assertEqual(
            paths.current_theme_colors(),
            pathlib.Path(
                self.tmpdir,
                ".local/state/omarchy/current/theme/colors.toml",
            ),
        )

    def test_defaults_without_env(self):
        for var in ("FOOT_THEME_STUDIO_HOME", "OMARCHY_PATH"):
            os.environ.pop(var)
        try:
            self.assertEqual(paths.home(), pathlib.Path.home())
            self.assertEqual(
                paths.omarchy_system_themes(),
                pathlib.Path("/usr/share/omarchy/themes"),
            )
            self.assertEqual(
                paths.foot_config(),
                pathlib.Path.home() / ".config" / "foot" / "foot.ini",
            )
        finally:
            os.environ["FOOT_THEME_STUDIO_HOME"] = self.tmpdir
            os.environ["OMARCHY_PATH"] = os.path.join(self.tmpdir, "omarchy-fake")


if __name__ == "__main__":
    unittest.main()
