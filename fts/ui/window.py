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
from .wallpaper_dialog import WallpaperDialog  # noqa: E402

__all__ = ["FtsWindow"]


def _action_button(
    label: str,
    tooltip: str,
    on_click,
    *,
    suggested: bool = False,
) -> Gtk.Button:
    """Labeled toolbar button; the tooltip keeps the long description."""
    button = Gtk.Button(label=label)
    button.set_tooltip_text(tooltip)
    button.connect("clicked", on_click)
    if suggested:
        button.add_css_class("suggested-action")
    return button


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
        self.set_size_request(640, 480)  # tiled-half and wrap-bar still work

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

        # ---- header + wrapping action bar ------------------------------
        # Apply stays on the HeaderBar so the primary action never clips.
        # Everything else lives in an Adw.WrapBox that folds onto a second
        # line when the window is tiled next to another pane (~900px).
        self._wtitle = Adw.WindowTitle(
            title=self._working_name, subtitle="Terminal Theme Studio"
        )
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.LOOSE)
        header.set_title_widget(self._wtitle)

        apply_btn = _action_button(
            "Apply",
            "Apply to Foot — write ~/.config/foot/palette.ini and OSC-push "
            "into running Foot",
            self._on_apply,
            suggested=True,
        )
        header.pack_end(apply_btn)

        open_btn = _action_button(
            "Open Image",
            "Extract a palette from an image",
            lambda *_args: self._imagewell.open_dialog(),
        )
        color_btn = _action_button(
            "Color Test",
            "Spectrum in-app and in a real Foot",
            self._on_color_test,
        )
        revert_btn = _action_button(
            "Revert",
            "Drop the override, back to the active theme",
            self._on_revert,
        )
        wallpapers_btn = _action_button(
            "Wallpapers…",
            "Generate matching desktop wallpapers and set one the Omarchy way",
            self._on_wallpapers,
        )
        export_btn = _action_button(
            "Export…",
            "Save this palette as a theme file for Alacritty, Ghostty, "
            "Kitty, WezTerm, or any other terminal",
            self._on_export,
        )
        save_btn = _action_button(
            "Save Theme…",
            "Write a named user theme under ~/.config/omarchy/themes",
            self._on_save_theme,
        )

        actions = Adw.WrapBox()
        actions.add_css_class("toolbar")
        actions.set_hexpand(True)
        actions.set_child_spacing(6)
        actions.set_line_spacing(6)
        actions.set_wrap_policy(Adw.WrapPolicy.MINIMUM)
        actions.set_justify(Adw.JustifyMode.NONE)
        actions.set_margin_start(8)
        actions.set_margin_end(8)
        actions.set_margin_top(2)
        actions.set_margin_bottom(6)
        for btn in (
            open_btn,
            color_btn,
            revert_btn,
            wallpapers_btn,
            export_btn,
            save_btn,
        ):
            actions.append(btn)

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
        toolbar.add_top_bar(actions)
        toolbar.set_content(self._toasts)
        self.set_content(toolbar)

        self.connect("map", self._on_map)

        # ---- initial working palette ------------------------------------
        palette, name = self._initial_palette()
        self.set_palette(palette, name=name, mark_modified=False)

        dismiss = Gtk.GestureClick()
        dismiss.set_button(1)
        dismiss.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        dismiss.connect("pressed", self._on_capture_click)
        self.add_controller(dismiss)

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
        if self._colortest_dialog is not None:
            self._colortest_dialog.close()
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

    def _on_capture_click(self, _gesture, _n_press, x: float, y: float) -> None:
        """Clicking the dimmed area outside Color Test closes it."""
        dialog = self._colortest_dialog
        if dialog is None:
            return
        # Prefer widget pick: the sheet's descendants are inside, the
        # dimming/library/header are not.
        node = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while node is not None:
            if node is dialog:
                return
            node = node.get_parent()
        ok, rect = dialog.compute_bounds(self)
        if ok:
            left, top = rect.origin.x, rect.origin.y
            right = left + rect.size.width
            bottom = top + rect.size.height
            if left <= x <= right and top <= y <= bottom:
                return
        dialog.close()

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

    def _on_wallpapers(self, button) -> None:
        dialog = WallpaperDialog(
            get_palette=lambda: self._working,
            default_name=self._working_name,
            toast=self.toast,
            source_path=self._imagewell.source_path,
            on_theme_created=self._on_theme_saved,
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
