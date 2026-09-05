"""Swatch grid: a self-drawn, clickable tile for every palette role.

Tiles paint their own color block (rounded rect with a per-tile contrast
outline), the hex label drawn in the role's color on a neutral chip, and
the role name -- so they stay readable under any GTK theme.  Clicking a
tile opens a :class:`Gtk.ColorDialog` and reports the edit via the
panel's ``role-edited(role, hex)`` signal.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GLib, GObject, Gtk, Pango, PangoCairo  # noqa: E402

from ..palette import (  # noqa: E402
    ROLE_GROUPS,
    ROLE_LABELS,
    hex_to_rgba,
    is_dark,
    mix,
    rgba_to_hex,
)

__all__ = ["SwatchPanel", "SwatchTile"]

_TILE_W = 96
_TILE_H = 82
_SWATCH_H = 40
_HEX_FONT = "Monospace 9"
_NAME_FONT = "Monospace 8"
_NEUTRAL_LIGHT = "#e8e8e8"
_NEUTRAL_DARK = "#1b1b1b"
_NAME_GRAY = "#8a8a8a"


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


class SwatchTile(Gtk.DrawingArea):
    """One palette role: color block + hex chip + role name, all drawn."""

    def __init__(self, role: str, on_edit, **kwargs) -> None:
        super().__init__(**kwargs)
        self._role = role
        self._label = ROLE_LABELS.get(role, role)
        self._hex = "#000000"
        self._on_edit = on_edit

        self.set_content_width(_TILE_W)
        self.set_content_height(_TILE_H)
        self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        self.set_draw_func(self._draw)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

    @property
    def role(self) -> str:
        return self._role

    def set_color(self, hexcolor: str) -> None:
        if hexcolor != self._hex:
            self._hex = hexcolor
            self.queue_draw()

    # ------------------------------------------------------------------
    # interaction
    # ------------------------------------------------------------------

    def _on_pressed(self, gesture, n_press, x, y) -> None:
        self._open_dialog()

    def _open_dialog(self) -> None:
        dialog = Gtk.ColorDialog()
        dialog.set_title(f"Edit {self._label}")
        dialog.set_with_alpha(False)
        rgba = Gdk.RGBA()
        rgba.parse(self._hex)

        def on_open(dlg, result):
            try:
                color = dlg.open_finish(result)
            except GLib.Error:
                return  # dialog dismissed
            try:
                hexcolor = rgba_to_hex(color.red, color.green, color.blue)
            except (ValueError, TypeError):
                return
            self._on_edit(self._role, hexcolor)

        dialog.open(self.get_root(), rgba, None, on_open)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------

    def _draw(self, da, cr, w, h) -> None:
        color = self._hex
        dark = is_dark(color)

        # color block with a 1px outline in a per-tile contrast tone
        _round_rect(cr, 1.0, 1.0, w - 2.0, _SWATCH_H, 8.0)
        cr.set_source_rgb(*_rgb(color))
        cr.fill_preserve()
        border = mix(color, "#ffffff" if dark else "#000000", 0.4)
        cr.set_source_rgb(*_rgb(border))
        cr.set_line_width(1.0)
        cr.stroke()

        # hex label: the role's color on a fixed neutral chip (theme-proof)
        chip_y = _SWATCH_H + 7.0
        chip_h = 18.0
        _round_rect(cr, 1.0, chip_y, w - 2.0, chip_h, 4.0)
        cr.set_source_rgb(*_rgb(_NEUTRAL_LIGHT if dark else _NEUTRAL_DARK))
        cr.fill()

        layout = self.create_pango_layout(self._hex)
        layout.set_font_description(Pango.FontDescription.from_string(_HEX_FONT))
        lw, lh = layout.get_pixel_size()
        cr.move_to((w - lw) / 2.0, chip_y + (chip_h - lh) / 2.0)
        cr.set_source_rgb(*_rgb(color))
        PangoCairo.show_layout(cr, layout)

        # role name
        name_layout = self.create_pango_layout(self._label)
        name_layout.set_font_description(Pango.FontDescription.from_string(_NAME_FONT))
        nw, nh = name_layout.get_pixel_size()
        cr.move_to((w - nw) / 2.0, chip_y + chip_h + 4.0)
        cr.set_source_rgb(*_rgb(_NAME_GRAY))
        PangoCairo.show_layout(cr, name_layout)


class SwatchPanel(Gtk.Box):
    """Sections (Terminal / Regular / Bright) of swatch tiles."""

    __gsignals__ = {
        "role-edited": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_STRING, GObject.TYPE_STRING),
        )
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self._tiles: dict[str, SwatchTile] = {}
        for group, roles in ROLE_GROUPS:
            label = Gtk.Label(label=group, xalign=0.0)
            label.add_css_class("caption")
            label.add_css_class("dim-label")
            label.set_margin_top(10)
            label.set_margin_start(4)
            self.append(label)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            # wrap instead of overflowing: 8 columns when wide, down to 4
            # when the pane is narrow (max keeps the row count bounded)
            flow.set_min_children_per_line(4)
            flow.set_max_children_per_line(8)
            flow.set_column_spacing(8)
            flow.set_row_spacing(8)
            flow.set_margin_top(4)
            flow.set_hexpand(True)
            for role in roles:
                tile = SwatchTile(role, self._on_tile_edit)
                self._tiles[role] = tile
                flow.append(tile)
            self.append(flow)

    def set_palette(self, p) -> None:
        """Refresh every tile from the palette (repaints on change)."""
        for role, tile in self._tiles.items():
            tile.set_color(getattr(p, role))

    def _on_tile_edit(self, role: str, hexcolor: str) -> None:
        self.emit("role-edited", role, hexcolor)
