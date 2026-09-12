"""Wallpaper save/set/read tests under the sandboxed Omarchy layout.

omarchy-theme-bg-set is never invoked for real (subprocess is mocked);
all paths live inside FOOT_THEME_STUDIO_HOME.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import EnvHomeTestCase  # noqa: E402

from fts import omarchy, paths  # noqa: E402
from fts.palette import Palette  # noqa: E402


class TestThemeName(EnvHomeTestCase):
    def test_missing_state_file_is_none(self):
        self.assertIsNone(omarchy.current_theme_name())

    def test_reads_theme_dot_name(self):
        path = paths.current_theme_name()
        path.parent.mkdir(parents=True)
        path.write_text("retro-82\n", encoding="utf-8")
        self.assertEqual(omarchy.current_theme_name(), "retro-82")


class TestBackgroundDirs(EnvHomeTestCase):
    def test_user_backgrounds_dir(self):
        directory = omarchy.user_backgrounds_dir("My Theme")
        self.assertEqual(
            directory, paths.home() / ".config/omarchy/backgrounds/my-theme"
        )

    def test_theme_backgrounds_dir(self):
        directory = omarchy.theme_backgrounds_dir("My Theme")
        self.assertEqual(
            directory,
            paths.omarchy_user_themes() / "my-theme" / "backgrounds",
        )


class TestSaveWallpaper(EnvHomeTestCase):
    def test_numbering_follows_omarchy_convention(self):
        first = omarchy.save_wallpaper(b"png", "My Theme", "dawn", ".png")
        self.assertEqual(first.name, "1-dawn.png")
        self.assertIn("backgrounds/my-theme", str(first))

        second = omarchy.save_wallpaper(b"png", "My Theme", "dusk", ".png")
        self.assertEqual(second.name, "2-dusk.png")

        # numbers already present in the directory push the next one up
        (first.parent / "7-extra.jpg").write_bytes(b"x")
        third = omarchy.save_wallpaper(b"png", "My Theme", "night", ".png")
        self.assertEqual(third.name, "8-night.png")

    def test_content_round_trips(self):
        path = omarchy.save_wallpaper(b"JPEGDATA", "theme", "x", ".jpg")
        self.assertEqual(path.read_bytes(), b"JPEGDATA")

    def test_into_theme_flag_targets_the_theme_dir(self):
        path = omarchy.save_wallpaper(
            b"png", "My Theme", "dawn", ".png", into_theme=True
        )
        self.assertEqual(
            path,
            paths.omarchy_user_themes() / "my-theme" / "backgrounds" / "1-dawn.png",
        )


class TestSetWallpaper(EnvHomeTestCase):
    def setUp(self):
        super().setUp()
        self.wallpaper = omarchy.user_backgrounds_dir("t") / "1-x.png"
        self.wallpaper.parent.mkdir(parents=True, exist_ok=True)
        self.wallpaper.write_bytes(b"png")

    def test_invokes_omarchy_theme_bg_set(self):
        with mock.patch.object(omarchy.shutil, "which", return_value="/usr/sbin/x"), \
                mock.patch.object(
                    omarchy.subprocess, "run", return_value=mock.Mock(returncode=0)
                ) as run:
            omarchy.set_wallpaper(self.wallpaper)
        run.assert_called_once_with(
            ["/usr/sbin/x", str(self.wallpaper.resolve())],
            capture_output=True,
            text=True,
        )

    def test_nonzero_exit_raises_with_stderr(self):
        with mock.patch.object(omarchy.shutil, "which", return_value="/usr/sbin/x"), \
                mock.patch.object(
                    omarchy.subprocess,
                    "run",
                    return_value=mock.Mock(returncode=1, stderr="boom"),
                ):
            with self.assertRaises(RuntimeError) as ctx:
                omarchy.set_wallpaper(self.wallpaper)
        self.assertIn("boom", str(ctx.exception))

    def test_missing_binary_raises(self):
        with mock.patch.object(omarchy.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                omarchy.set_wallpaper(self.wallpaper)
        self.assertIn("omarchy-theme-bg-set", str(ctx.exception))

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            omarchy.set_wallpaper("/nonexistent/wall.png")


class TestCreateThemeE2E(EnvHomeTestCase):
    """The full create-theme sequence, as the wallpaper dialog runs it:
    colors.toml -> generated wallpapers into the theme dir -> apply ->
    set the first wallpaper.  omarchy-theme-set / bg-set are mocked per
    repo policy; everything on disk is real."""

    IMAGES = [(b"png-one", ".png"), (b"png-two", ".png")]

    def _run_flow(self, slug, palette, images, apply):
        saved = []
        colors_path = omarchy.save_user_theme(palette, slug)
        for data, ext in images:
            saved.append(
                omarchy.save_wallpaper(data, slug, "wallpaper", ext, into_theme=True)
            )
        if apply and saved:
            def fake_which(name):
                if name == "omarchy-theme-set":
                    return "/usr/sbin/theme-set"
                return "/usr/sbin/bg-set"

            with mock.patch.object(omarchy.shutil, "which",
                                   side_effect=fake_which), \
                    mock.patch.object(omarchy.subprocess, "run",
                                      return_value=mock.Mock(returncode=0)) as run:
                omarchy.apply_full_theme(slug)
                omarchy.set_wallpaper(saved[0])
            calls = [c.args[0] for c in run.call_args_list]
        else:
            calls = []
        return colors_path, saved, calls

    def test_full_theme_lands_on_disk_and_in_the_library(self):
        palette = Palette.from_dict({})
        colors_path, saved, calls = self._run_flow(
            "Mocha Flux", palette, self.IMAGES, apply=True
        )

        theme_dir = paths.omarchy_user_themes() / "mocha-flux"
        self.assertTrue((theme_dir / "colors.toml").is_file())
        self.assertEqual(colors_path, theme_dir / "colors.toml")
        self.assertEqual(
            [p.name for p in saved],
            ["1-wallpaper.png", "2-wallpaper.png"],
        )
        for path in saved:
            self.assertEqual(path.read_bytes().startswith(b"png-"), True)
        self.assertEqual(saved[0].parent, theme_dir / "backgrounds")

        # apply ran against the normalized slug, then set wallpaper #1
        self.assertEqual(calls[0], ["/usr/sbin/theme-set", "mocha-flux"])
        self.assertEqual(calls[1], ["/usr/sbin/bg-set", str(saved[0].resolve())])

        # the created theme is a first-class library citizen
        names = [e.name for e in omarchy.list_local_themes()]
        self.assertIn("mocha-flux", names)
        entry = next(e for e in omarchy.list_local_themes() if e.name == "mocha-flux")
        self.assertEqual(entry.source, "user")
        self.assertEqual(entry.palette, palette)

    def test_generation_failure_still_leaves_a_valid_theme(self):
        # colors.toml is written first, so a mid-generation failure leaves
        # a theme that applies with whatever wallpapers made it.
        palette = Palette.from_dict({})
        omarchy.save_user_theme(palette, "half-done")
        saved = [omarchy.save_wallpaper(b"png", "half-done", "w", ".png",
                                        into_theme=True)]
        theme_dir = paths.omarchy_user_themes() / "half-done"
        self.assertTrue((theme_dir / "colors.toml").is_file())
        self.assertEqual([p.name for p in saved], ["1-w.png"])


class TestCurrentWallpaper(EnvHomeTestCase):
    def test_missing_link_is_none(self):
        self.assertIsNone(omarchy.current_wallpaper())

    def test_resolves_the_symlink(self):
        target = paths.home() / "somewhere" / "bg.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"jpg")
        link = paths.current_background_link()
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        self.assertEqual(omarchy.current_wallpaper(), target.resolve())


if __name__ == "__main__":
    unittest.main()
