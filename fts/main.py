"""Application entry point: ``python3 -m fts.main``."""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from .ui.window import FtsWindow  # noqa: E402

__all__ = ["FtsApplication", "main"]

APP_ID = "com.omarchy.FootThemeStudio"


class FtsApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self) -> None:
        win = self.props.active_window
        if win is None:
            win = FtsWindow(application=self)
        win.present()


def main(argv: list[str] | None = None) -> int:
    app = FtsApplication()
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
