"""Fake Foot terminal preview, painted only from the working palette.

Draws window chrome (title strip), a shell prompt, an ``ls -l``-style
block, plain foreground text, a selection sample and a 16-color block
row.  Every color is taken from (or mixed from) the working palette --
no theme colors are used.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Pango, PangoCairo  # noqa: E402

from ..palette import hex_to_rgba, is_dark, mix  # noqa: E402

__all__ = ["TerminalPreview"]

_FONT = "JetBrainsMono Nerd Font, monospace 10"


def _rgb(hexcolor: str) -> tuple[float, float, float]:
    r, g, b, _a = hex_to_rgba(hexcolor)
    return (r, g, b)


def _round_rect(cr, x: float, y: float, w: float, h: float, r: float) -> None:
    cr.new_sub_path()
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2.0 * math.pi)
    cr.arc(x + w - r, y + h - r, r, 0.0, 0.5 * math.pi)
    cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
    cr.close_path()


def _user_at_host() -> str:
    import getpass
    import os

    try:
        return f"{getpass.getuser()}@{os.uname().nodename}"
    except Exception:
        return "user@host"


class TerminalPreview(Gtk.DrawingArea):
    """A fake terminal drawn from the working palette."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._palette = None
        self.set_draw_func(self._draw)

    def set_palette(self, p) -> None:
        self._palette = p
        self.queue_draw()

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------

    def _draw(self, da, cr, w, h) -> None:
        p = self._palette
        if p is None:
            return
        cr.set_source_rgb(*_rgb(p.background))
        cr.paint()

        metrics = self.create_pango_layout("M" * 16)
        metrics.set_font_description(Pango.FontDescription.from_string(_FONT))
        mw, mh = metrics.get_pixel_size()
        lh = float(mh)
        pad = 14.0
        title_h = 26.0

        # ---- title bar strip -------------------------------------------
        cr.set_source_rgb(*_rgb(mix(p.background, p.foreground, 0.10)))
        cr.rectangle(0, 0, w, title_h)
        cr.fill()
        for i, role in enumerate(("regular1", "regular3", "regular2")):
            cr.arc(pad + 4 + i * 14, title_h / 2.0, 4.5, 0, 2 * math.pi)
            cr.set_source_rgb(*_rgb(getattr(p, role)))
            cr.fill()
        title = self.create_pango_layout("foot — theme preview")
        title.set_font_description(Pango.FontDescription.from_string(_FONT))
        _tw, th = title.get_pixel_size()
        cr.move_to(pad + 52, (title_h - th) / 2.0)
        cr.set_source_rgb(*_rgb(mix(p.foreground, p.background, 0.45)))
        PangoCairo.show_layout(cr, title)
        cr.set_source_rgb(*_rgb(mix(p.background, p.foreground, 0.18)))
        cr.rectangle(0, title_h, w, 1.0)
        cr.fill()

        # ---- body -------------------------------------------------------
        y = title_h + 12.0

        def line(segments) -> None:
            nonlocal y
            x = pad
            for text, color in segments:
                layout = self.create_pango_layout(text)
                layout.set_font_description(
                    Pango.FontDescription.from_string(_FONT)
                )
                cr.move_to(x, y)
                cr.set_source_rgb(*_rgb(color))
                PangoCairo.show_layout(cr, layout)
                lw, _lh = layout.get_pixel_size()
                x += lw
            y += lh + 3.0

        # prompt: green user@host, blue path, yellow git branch
        line(
            [
                (_user_at_host() + " ", p.regular2),
                ("~/Projects/foot-theme-studio ", p.regular4),
                ("git:(main) ", p.regular3),
                ("$ ", p.foreground),
            ]
        )
        line([])

        # ls -l-style block
        for text, color in (
            ("drwxr-xr-x  user 4.0K  src/", p.regular4),
            ("drwxr-xr-x  user 4.0K  docs/", p.bright4),
            ("-rwxr-xr-x  user 8.2K  build.sh", p.regular2),
            ("lrwxrwxrwx  user   12  latest -> v1.2/", p.regular6),
            ("-rw-r--r--  user 220K  wallpaper.png", p.regular5),
            ("-rw-r--r--  user 1.2M  backup.tar.gz", p.regular1),
            ("-rw-r--r--  user  918  TODO.txt", p.bright0),
        ):
            line([(text, color)])
        line([])

        # plain foreground text
        line(
            [
                (
                    "The quick brown fox jumps over the lazy dog — 0123456789",
                    p.foreground,
                )
            ]
        )

        # selection sample
        sel = self.create_pango_layout("  selected text with selection colors  ")
        sel.set_font_description(Pango.FontDescription.from_string(_FONT))
        sw, _sh = sel.get_pixel_size()
        cr.set_source_rgb(*_rgb(p.selection_bg))
        cr.rectangle(pad - 2, y - 1, sw + 6, lh + 2)
        cr.fill()
        cr.move_to(pad, y)
        cr.set_source_rgb(*_rgb(p.selection_fg))
        PangoCairo.show_layout(cr, sel)
        y += lh + 9.0

        # 16-color block row
        cell_w, cell_h, gap = 26.0, 15.0, 4.0
        for i in range(16):
            role = f"regular{i}" if i < 8 else f"bright{i - 8}"
            color = getattr(p, role)
            cx = pad + i * (cell_w + gap)
            _round_rect(cr, cx, y, cell_w, cell_h, 3.5)
            cr.set_source_rgb(*_rgb(color))
            cr.fill_preserve()
            border = mix(color, p.foreground if is_dark(color) else p.background, 0.5)
            cr.set_source_rgb(*_rgb(border))
            cr.set_line_width(1.0)
            cr.stroke()
