"""Layout budgets: panes must fit the narrowest window the app advertises.

The studio is used tiled next to other panes.  It used to demand 640px for the
window and 432px for the swatch grid, so a narrower tile pushed the window off
the screen edge (and the swatch grid clipped inside the pane).

These checks measure the real GTK widget tree and fail if a hard minimum comes
back.  They need PyGObject + GTK4 + libadwaita and a display, so they are
opt-in: set ``FTS_UI_MEASURE=1`` (CI runs them under ``xvfb-run``).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_ENABLED = os.environ.get("FTS_UI_MEASURE") == "1"

# The narrowest window the app claims to support (FtsWindow.set_size_request).
MIN_WINDOW_WIDTH = 400
# Room the horizontal split needs besides the two panes (handle + borders).
SPLIT_CHROME = 8


@unittest.skipUnless(
    _ENABLED, "set FTS_UI_MEASURE=1 with a display to measure the widget tree"
)
class UiLayoutBudgetTest(unittest.TestCase):
    """Measure FtsWindow and every dialog once, then assert the budgets."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="fts-ui-measure-")
        cls.addClassCleanup(shutil.rmtree, cls._tmp, ignore_errors=True)
        cls._saved_env = {
            var: os.environ.get(var)
            for var in ("FOOT_THEME_STUDIO_HOME", "OMARCHY_PATH")
        }
        os.environ["FOOT_THEME_STUDIO_HOME"] = cls._tmp
        os.environ["OMARCHY_PATH"] = os.path.join(cls._tmp, "omarchy-fake")
        cls.addClassCleanup(cls._restore_env)
        cls.measurements = cls._collect()

    @classmethod
    def _restore_env(cls) -> None:
        for var, old in cls._saved_env.items():
            if old is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = old

    @staticmethod
    def _collect() -> dict[str, int]:
        """Build the window, measure horizontal minimums, tear it down."""
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")

        from gi.repository import Adw, GLib, Gtk  # noqa: E402

        Adw.init()
        app = Adw.Application(application_id="dev.local.fts.layout.budget")
        out: dict[str, int] = {}
        failure: list[BaseException] = []

        def on_activate(application) -> None:
            from fts.ui.dialogs import (  # noqa: E402
                ColorTestDialog,
                ExportDialog,
                SaveThemeDialog,
            )
            from fts.ui.wallpaper_dialog import WallpaperDialog  # noqa: E402
            from fts.ui.window import FtsWindow  # noqa: E402

            def noop(*_args, **_kwargs) -> None:
                return None

            window = FtsWindow(application=application)
            window.present()

            def measure() -> bool:
                try:
                    def min_width(widget) -> int:
                        return widget.measure(Gtk.Orientation.HORIZONTAL, -1)[0]

                    out["window"] = min_width(window)
                    out["library"] = min_width(window._library)
                    out["top_pane"] = min_width(window._vpaned)
                    out["swatches"] = min_width(window._swatches)
                    out["imagewell"] = min_width(window._imagewell)

                    dialogs = {
                        "colortest": ColorTestDialog(
                            get_palette=lambda: window.working, toast=noop
                        ),
                        "save": SaveThemeDialog(
                            get_palette=lambda: window.working,
                            default_name="measure",
                            toast=noop,
                            on_saved=noop,
                        ),
                        "export": ExportDialog(
                            get_palette=lambda: window.working,
                            default_name="measure",
                            toast=noop,
                        ),
                        "wallpaper": WallpaperDialog(
                            get_palette=lambda: window.working,
                            default_name="measure",
                            toast=noop,
                            source_path=None,
                            on_theme_created=noop,
                        ),
                    }
                    for name, dialog in dialogs.items():
                        out[f"dialog:{name}"] = min_width(dialog.get_child())
                except BaseException as exc:  # noqa: BLE001 - re-raised below
                    failure.append(exc)
                finally:
                    application.quit()
                return False

            # Let CSS classes and the initial layout settle before measuring.
            GLib.timeout_add(750, measure)

        app.connect("activate", on_activate)
        GLib.timeout_add(20_000, lambda: (app.quit(), False)[-1])
        app.run([])
        if failure:
            raise failure[0]
        return out

    def test_window_floor_matches_a_supported_tile(self) -> None:
        self.assertLessEqual(
            self.measurements["window"],
            MIN_WINDOW_WIDTH,
            "FtsWindow minimum width grew past the floor narrow tiles rely on; "
            "the window will hang off the edge of a narrower pane",
        )

    def test_panes_still_fit_inside_the_floor_together(self) -> None:
        needed = (
            self.measurements["library"]
            + self.measurements["top_pane"]
            + SPLIT_CHROME
        )
        self.assertLessEqual(
            needed,
            MIN_WINDOW_WIDTH,
            f"library {self.measurements['library']}px + top pane "
            f"{self.measurements['top_pane']}px no longer fit a "
            f"{MIN_WINDOW_WIDTH}px window; a pane has to clip or overflow",
        )

    def test_swatch_grid_and_image_well_can_shrink(self) -> None:
        self.assertLessEqual(
            self.measurements["swatches"],
            160,
            "the swatch grid stopped collapsing to a single column",
        )
        self.assertLessEqual(
            self.measurements["imagewell"],
            220,
            "the image well row stopped wrapping",
        )

    def test_dialogs_can_be_tiled_narrow(self) -> None:
        for name, width in self.measurements.items():
            if not name.startswith("dialog:"):
                continue
            with self.subTest(dialog=name):
                self.assertLessEqual(
                    width,
                    MIN_WINDOW_WIDTH,
                    f"{name} dialog content demands {width}px",
                )


if __name__ == "__main__":
    unittest.main()
