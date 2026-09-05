"""FtsWindow: the main application window and all palette wiring.

Owns the working state (``working: Palette``, ``working_name: str``,
``modified: bool``).  All mutations funnel through :meth:`FtsWindow.set_palette`,
which refreshes swatches, preview, an open color-test dialog and the
header title, then emits the ``palette-changed`` signal.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GObject, Gtk  # noqa: E402

from .. import foot_config, omarchy, osc, paths  # noqa: E402
from ..palette import Palette  # noqa: E402
from .dialogs import ColorTestDialog, ExportDialog, SaveThemeDialog  # noqa: E402
from .imagewell import ImageWell  # noqa: E402
from .library_panel import LibraryPanel  # noqa: E402
from .library_panel import LibraryEntry  # noqa: F401  (re-export convenience)
from .preview import TerminalPreview  # noqa: E402
from .swatches import SwatchPanel  # noqa: E402

__all__ = ["FtsWindow"]


class FtsWindow(Adw.ApplicationWindow):
    """Top-level window: library | swatches+image well / preview."""

    __gtype_name__ = "FtsWindow"

    __gsignals__ = {
        "palette-changed": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self._working = Palette.from_dict(Palette.DEFAULTS)
        self._working_name = "Untitled"
        self._modified = False
        self._positioned = False
        self._colortest_dialog: ColorTestDialog | None = None

        self.set_title("Terminal Theme Studio")
        self.set_default_size(1280, 800)  # >= 1200x760
        self.set_size_request(900, 600)  # hard minimum

        # ---- panels (created first; header buttons reference them) ----
        self._library = LibraryPanel()
        self._library.connect("entry-selected", self._on_library_entry)

        self._swatches = SwatchPanel()
        self._swatches.connect("role-edited", self._on_role_edited)

        self._imagewell = ImageWell(toast=self.toast)
        self._imagewell.connect("image-palette", self._on_image_palette)

        self._preview = TerminalPreview()
        for attr, value in (
            ("set_margin_top", 8),
            ("set_margin_bottom", 8),
            ("set_margin_start", 8),
            ("set_margin_end", 8),
        ):
            getattr(self._preview, attr)(value)

        # ---- header bar ------------------------------------------------
        self._wtitle = Adw.WindowTitle(
            title=self._working_name, subtitle="Terminal Theme Studio"
        )
        header = Adw.HeaderBar()
        header.set_title_widget(self._wtitle)

        open_btn = Gtk.Button(label="Open Image")
        open_btn.set_tooltip_text("Extract a palette from an image")
        open_btn.connect("clicked", lambda *_args: self._imagewell.open_dialog())
        header.pack_start(open_btn)

        color_btn = Gtk.Button(label="Color Test")
        color_btn.set_tooltip_text("Spectrum in-app and in a real Foot")
        color_btn.connect("clicked", self._on_color_test)
        header.pack_start(color_btn)

        revert_btn = Gtk.Button(label="Revert")
        revert_btn.set_tooltip_text("Drop the override, back to the active theme")
        revert_btn.connect("clicked", self._on_revert)
        header.pack_start(revert_btn)

        apply_btn = Gtk.Button(label="Apply to Foot")
        apply_btn.add_css_class("suggested-action")
        apply_btn.set_tooltip_text(
            "Write ~/.config/foot/palette.ini and OSC-push into running Foot"
        )
        apply_btn.connect("clicked", self._on_apply)
        header.pack_end(apply_btn)

        save_btn = Gtk.Button(label="Save as Omarchy Theme…")
        save_btn.set_tooltip_text("Write a named user theme under ~/.config/omarchy/themes")
        save_btn.connect("clicked", self._on_save_theme)
        header.pack_end(save_btn)

        export_btn = Gtk.Button(label="Export…")
        export_btn.set_tooltip_text(
            "Save this palette as a theme file for Alacritty, Ghostty, "
            "Kitty, WezTerm, or any other terminal"
        )
        export_btn.connect("clicked", self._on_export)
        header.pack_end(export_btn)

        # ---- panes ------------------------------------------------------
        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        top_box.set_margin_top(10)
        top_box.set_margin_bottom(12)
        top_box.set_margin_start(12)
        top_box.set_margin_end(12)
        top_box.append(self._swatches)
        top_box.append(self._imagewell)

        top_scroll = Gtk.ScrolledWindow()
        # swatches wrap to the pane width; never scroll horizontally
        top_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        top_scroll.set_child(top_box)

        self._vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self._vpaned.set_start_child(top_scroll)
        self._vpaned.set_end_child(self._preview)
        self._vpaned.set_shrink_start_child(True)
        self._vpaned.set_shrink_end_child(False)
        self._vpaned.set_position(300)  # refined on map; preview gets ~60%

        self._hpaned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self._hpaned.set_start_child(self._library)
        self._hpaned.set_end_child(self._vpaned)
        self._hpaned.set_shrink_start_child(False)
        self._hpaned.set_shrink_end_child(True)
        self._hpaned.set_position(280)  # refined on map

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(self._hpaned)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._toasts)
        self.set_content(toolbar)

        self.connect("map", self._on_map)

        # ---- initial working palette ------------------------------------
        palette, name = self._initial_palette()
        self.set_palette(palette, name=name, mark_modified=False)

    # ------------------------------------------------------------------
    # working palette state
    # ------------------------------------------------------------------

    @property
    def working(self) -> Palette:
        return self._working

    @property
    def working_name(self) -> str:
        return self._working_name

    @property
    def modified(self) -> bool:
        return self._modified

    def set_palette(self, palette: Palette, name: str | None = None, *, mark_modified: bool = True) -> None:
        """Install a new working palette and refresh everything."""
        self._working = palette
        if name is not None:
            self._working_name = name
        self._modified = bool(mark_modified)
        self._swatches.set_palette(palette)
        self._preview.set_palette(palette)
        if self._colortest_dialog is not None:
            self._colortest_dialog.refresh()
        self._wtitle.set_title(self._working_name + (" •" if self._modified else ""))
        self.emit("palette-changed")

    def toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message, timeout=5))

    # ------------------------------------------------------------------
    # header actions
    # ------------------------------------------------------------------

    def _initial_palette(self) -> tuple[Palette, str]:
        colors = paths.current_theme_colors()
        if colors.is_file():
            try:
                return omarchy.load_colors_toml(colors), "current theme"
            except Exception as exc:
                print(
                    f"terminal-theme-studio: could not load current theme: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        return Palette.from_dict(Palette.DEFAULTS), "Untitled"

    def _on_role_edited(self, _panel, role: str, hexcolor: str) -> None:
        data = self._working.to_dict()
        data[role] = hexcolor
        self.set_palette(Palette.from_dict(data))

    def _on_library_entry(self, _panel, entry) -> None:
        self._library.set_active_entry(entry)
        self.set_palette(entry.palette, name=entry.name, mark_modified=False)

    def _on_image_palette(self, _well, palette: Palette, name: str) -> None:
        self._library.set_active_entry(None)
        self.set_palette(palette, name=name, mark_modified=False)
        self.toast(f"Extracted palette “{name}” from image")

    def _on_apply(self, button) -> None:
        try:
            count = foot_config.push_override_live(self._working)
        except Exception as exc:
            print(
                f"terminal-theme-studio: apply failed: {exc}", file=sys.stderr, flush=True
            )
            self.toast(f"Apply failed: {exc}")
            return
        self.toast(f"Foot override written + live-pushed to {count} terminal(s)")

    def _on_revert(self, button) -> None:
        try:
            foot_config.clear_palette_override()
        except Exception as exc:
            print(
                f"terminal-theme-studio: clearing override failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            self.toast(f"Could not clear the Foot override: {exc}")

        colors = paths.current_theme_colors()
        palette: Palette | None = None
        name = "Untitled"
        pushed: int | None = None
        if colors.is_file():
            try:
                palette = omarchy.load_colors_toml(colors)
                name = "current theme"
            except Exception as exc:
                print(
                    f"terminal-theme-studio: could not load current theme: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
        if palette is not None:
            try:
                pushed = osc.push_to_running_foot(palette)
            except Exception as exc:
                print(
                    f"terminal-theme-studio: OSC push failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                pushed = 0

        self._library.set_active_entry(None)
        self.set_palette(palette if palette is not None else Palette.from_dict(Palette.DEFAULTS), name=name, mark_modified=False)
        if pushed is None:
            self.toast("Reverted to defaults (no active Omarchy theme found)")
        else:
            self.toast(
                f"Reverted — Foot restored to the active theme ({pushed} terminal(s) refreshed)"
            )

    def _on_color_test(self, button) -> None:
        if self._colortest_dialog is None:
            self._colortest_dialog = ColorTestDialog(
                get_palette=lambda: self._working, toast=self.toast
            )
            self._colortest_dialog.connect(
                "closed", lambda *_args: setattr(self, "_colortest_dialog", None)
            )
        self._colortest_dialog.refresh()
        self._colortest_dialog.present(self)

    def _on_save_theme(self, button) -> None:
        dialog = SaveThemeDialog(
            get_palette=lambda: self._working,
            default_name=self._working_name,
            toast=self.toast,
            on_saved=self._on_theme_saved,
        )
        dialog.present(self)

    def _on_export(self, button) -> None:
        dialog = ExportDialog(
            get_palette=lambda: self._working,
            default_name=self._working_name,
            toast=self.toast,
        )
        dialog.present(self)

    def _on_theme_saved(self, slug: str, path) -> None:
        self._library.refresh()
        self._library.set_active_entry(self._find_user_entry(slug))
        self.set_palette(self._working, name=slug, mark_modified=False)

    def _find_user_entry(self, slug: str):
        for entry in self._library.entries:
            if entry.source == "user" and entry.origin.endswith(
                f"/{slug}/colors.toml"
            ):
                return entry
        return None

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------

    def _on_map(self, *args) -> None:
        """Set real pane split ratios once we know the window size."""
        if self._positioned:
            return
        self._positioned = True
        width = self.get_width() or 1280
        height = self.get_height() or 800
        self._hpaned.set_position(max(240, min(380, int(width * 0.24))))
        self._vpaned.set_position(int(height * 0.40))
