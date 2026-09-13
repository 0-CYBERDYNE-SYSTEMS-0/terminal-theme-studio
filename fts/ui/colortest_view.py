"""In-app spectrum surface: 16 ANSI blocks, 6x6x6 cube, gray ramp, gradient.

Cells 0-15 come from the working palette; the cube, grayscale ramp and
gradient use raw truecolor values (the 256-color cube/gray formulas).

The canvas follows its allocation width via :func:`fts.colortest.spectrum_geom`
so a narrow window never clips the cube or gradient off the right edge.
Put it in a :class:`Gtk.ScrolledWindow` with horizontal scrolling off.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Pango, PangoCairo  # noqa: E402

from ..colortest import spectrum_geom  # noqa: E402
from ..palette import hex_to_rgba  # noqa: E402

__all__ = ["ColorTestView"]

# Preferred spectrum width for the initial height; never used as a minimum.
_NATURAL_WIDTH = 640
_FONT = "JetBrainsMono Nerd Font, monospace 10"


def _rgb(hexcolor: str) -> tuple[float, float, float]:
    r, g, b, _a = hex_to_rgba(hexcolor)
    return (r, g, b)


def _cube_rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Truecolor value of 256-color cube cell 16 + 36r + 6g + b."""
    conv = lambda x: 0 if x == 0 else 55 + 40 * x  # noqa: E731
    return (conv(r), conv(g), conv(b))


class ColorTestView(Gtk.DrawingArea):
    """DrawFunc-based truecolor test canvas bound to a working palette."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._palette = None
        self.set_hexpand(True)
        self.set_vexpand(True)
        # No width request: a minimum here travels up through the pane and
        # pushes the window wider than a narrow tile.  The spectrum flexes to
        # whatever the pane gives it (spectrum_geom is safe at any width), so
        # only a preferred height is advertised.
        self.set_content_height(int(spectrum_geom(_NATURAL_WIDTH).height))
        self.set_draw_func(self._draw)
        self.connect("resize", self._on_resize)

    def set_palette(self, p) -> None:
        self._palette = p
        self.queue_draw()

    def _on_resize(self, _da, width: int, _height: int) -> None:
        needed = int(round(spectrum_geom(max(1, width)).height))
        if needed != self.get_content_height():
            self.set_content_height(needed)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------

    def _draw(self, da, cr, w, h) -> None:
        p = self._palette
        if p is None:
            cr.set_source_rgb(0.05, 0.05, 0.05)
            cr.paint()
            return
        geom = spectrum_geom(w)
        cr.set_source_rgb(*_rgb(p.background))
        cr.paint()

        x = geom.margin
        y = geom.top
        avail = geom.avail

        def heading(text: str) -> None:
            nonlocal y
            layout = self.create_pango_layout(text)
            layout.set_font_description(Pango.FontDescription.from_string(_FONT))
            layout.set_width(int(avail * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            cr.move_to(x, y)
            cr.set_source_rgb(*_rgb(p.foreground))
            PangoCairo.show_layout(cr, layout)
            _lw, lh = layout.get_pixel_size()
            y += lh + geom.heading_gap

        # ---- 16 ANSI palette (working palette) --------------------------
        heading("16 ANSI palette (working palette)")
        cell_w, cell_h, gap = geom.ansi_cell_w, geom.ansi_cell_h, geom.ansi_gap
        for i in range(16):
            row, col = divmod(i, 8)
            role = f"regular{i}" if i < 8 else f"bright{i - 8}"
            cr.rectangle(
                x + col * (cell_w + gap), y + row * (cell_h + gap), cell_w, cell_h
            )
            cr.set_source_rgb(*_rgb(getattr(p, role)))
            cr.fill()
        y += 2 * (cell_h + gap) + geom.section_gap

        # ---- 6x6x6 cube (raw truecolor) ---------------------------------
        heading("6×6×6 color cube (raw truecolor, cells 16–231)")
        c = geom.cube_cell
        gap_c = 1.0 if c > 3.0 else 0.0
        for r in range(6):
            for g in range(6):
                for b in range(6):
                    cr.rectangle(
                        x + (g * 6 + b) * c, y + r * c, c - gap_c, c - gap_c
                    )
                    cr.set_source_rgb(*_cube_rgb(r, g, b))
                    cr.fill()
        y += 6 * c + geom.section_gap

        # ---- grayscale ramp (raw truecolor) ------------------------------
        heading("Grayscale ramp (raw truecolor, cells 232–255)")
        gw = avail / 24.0
        for i in range(24):
            v = 8 + 10 * i
            cr.rectangle(x + i * gw, y, max(0.5, gw - 1.0), geom.gray_h)
            cr.set_source_rgb(v / 255.0, v / 255.0, v / 255.0)
            cr.fill()
        y += geom.gray_h + geom.section_gap

        # ---- truecolor gradient ------------------------------------------
        heading("Truecolor gradient — background → accent → foreground")
        steps = max(48, int(avail))
        seg = avail / steps
        start = _rgb(p.background)
        accent = _rgb(p.regular4)
        end = _rgb(p.foreground)
        for i in range(steps):
            t = i / (steps - 1)
            if t < 0.5:
                tt = t / 0.5
                a, b_ = start, accent
            else:
                tt = (t - 0.5) / 0.5
                a, b_ = accent, end
            col = tuple(a[ch] * (1 - tt) + b_[ch] * tt for ch in range(3))
            cr.rectangle(x + i * seg, y, seg + 0.75, geom.grad_h)
            cr.set_source_rgb(*col)
            cr.fill()
