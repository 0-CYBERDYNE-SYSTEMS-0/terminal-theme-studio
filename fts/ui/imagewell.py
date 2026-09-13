"""Image well: drop or choose an image, extract a 16-color palette.

Loads the image via GdkPixbuf bounded at ~512px (which also bounds
quantization time), runs :func:`fts.quantize.extract_palette` and
:func:`fts.quantize.palette_from_colors`, and reports the result via the
``image-palette(palette, name)`` signal (name = file stem).
"""

from __future__ import annotations

from pathlib import PurePath

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, GObject, Gtk, Pango, PangoCairo  # noqa: E402

from .. import quantize  # noqa: E402

__all__ = ["ImageWell"]

_SCALE_MAX = 512
_THUMB = 160
_IMAGE_MIMES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
    "image/gif",
)


class _Placeholder(Gtk.DrawingArea):
    """Dashed 'Drop image here' surface."""

    def __init__(self, on_click, **kwargs) -> None:
        super().__init__(**kwargs)
        self._on_click = on_click
        self.set_content_height(120)
        self.set_hexpand(True)
        self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        self.set_draw_func(self._draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self._pressed)
        self.add_controller(click)

    def _pressed(self, gesture, n_press, x, y) -> None:
        self._on_click()

    def _draw(self, da, cr, w, h) -> None:
        fg = self.get_color()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.55 * fg.alpha)
        cr.set_line_width(1.5)
        cr.set_dash([6.0, 4.0])
        cr.rectangle(10.5, 10.5, w - 21.0, h - 21.0)
        cr.stroke()
        cr.set_dash([])

        line1 = self.create_pango_layout("Drop image here")
        line1.set_font_description(Pango.FontDescription.from_string("Sans 11"))
        line2 = self.create_pango_layout("or click — png · jpeg · webp · bmp · gif")
        line2.set_font_description(Pango.FontDescription.from_string("Sans 9"))
        w1, h1 = line1.get_pixel_size()
        w2, h2 = line2.get_pixel_size()
        top = (h - h1 - h2 - 6.0) / 2.0
        cr.move_to((w - w1) / 2.0, top)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, fg.alpha)
        PangoCairo.show_layout(cr, line1)
        cr.move_to((w - w2) / 2.0, top + h1 + 6.0)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.7 * fg.alpha)
        PangoCairo.show_layout(cr, line2)


class ImageWell(Gtk.Box):
    """Card showing the loaded image (or a drop placeholder)."""

    __gsignals__ = {
        "image-palette": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT, GObject.TYPE_STRING),
        )
    }

    def __init__(self, toast, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        self._toast = toast
        self._source_path: str | None = None

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self._stack.set_vhomogeneous(False)

        self._placeholder = _Placeholder(self.open_dialog)
        self._picture = Gtk.Picture()
        self._picture.set_can_shrink(False)
        self._stack.add_named(self._placeholder, "empty")
        self._stack.add_named(self._picture, "image")

        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(self._stack)
        self.append(frame)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hint = Gtk.Label(label="Image → 16-color palette", xalign=0.0, wrap=True)
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        hint.set_hexpand(True)
        hint.set_valign(Gtk.Align.CENTER)
        btn = Gtk.Button(label="Open Image…")
        btn.connect("clicked", lambda *_args: self.open_dialog())
        row.append(hint)
        row.append(btn)
        self.append(row)

        self._setup_dnd()

    # ------------------------------------------------------------------
    # drag & drop + file chooser
    # ------------------------------------------------------------------

    @property
    def source_path(self) -> str | None:
        """The file the current image (and palette) came from, if any.

        The wallpaper dialog passes this to Gemini as a reference image;
        None when no image has been loaded.
        """
        return self._source_path

    def _setup_dnd(self) -> None:
        file_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        file_target.connect("drop", self._on_drop_files)
        self.add_controller(file_target)

        # fallback for sources that only offer text/uri-list
        uri_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.COPY)
        uri_target.connect("drop", self._on_drop_string)
        self.add_controller(uri_target)

    def _on_drop_files(self, target, value, x, y) -> bool:
        try:
            files = value.get_files()
        except AttributeError:
            return False
        if files is None or files.get_n_items() == 0:
            return False
        f = files.get_item(0)
        path = f.get_path()
        if not path:
            try:
                path = GLib.filename_from_uri(f.get_uri())[0]
            except (GLib.Error, TypeError, IndexError):
                return False
        if not path:
            return False
        self.load_path(path)
        return True

    def _on_drop_string(self, target, value, x, y) -> bool:
        for chunk in str(value).replace("\r\n", "\n").split("\n"):
            uri = chunk.strip()
            if not uri:
                continue
            if "://" in uri:
                try:
                    path = GLib.filename_from_uri(uri)[0]
                except (GLib.Error, TypeError, IndexError):
                    continue
            else:
                path = uri
            if path:
                self.load_path(path)
                return True
        return False

    def open_dialog(self) -> None:
        """Gtk.FileDialog with an image mime filter."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Open image")
        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")
        for mime in _IMAGE_MIMES:
            image_filter.add_mime_type(mime)
        dialog.set_default_filter(image_filter)

        def on_open(dlg, result):
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                return  # dialog dismissed
            path = file.get_path()
            if path:
                self.load_path(path)

        dialog.open(self.get_root(), None, on_open)

    # ------------------------------------------------------------------
    # loading + extraction
    # ------------------------------------------------------------------

    def load_path(self, path: str) -> None:
        """Load an image file, extract its palette and announce it."""
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, _SCALE_MAX, _SCALE_MAX, True
            )
        except GLib.Error as exc:
            self._toast(f"Could not load image: {exc.message or exc}")
            return
        except Exception as exc:  # corrupt / unreadable file
            self._toast(f"Could not load image: {exc}")
            print(f"terminal-theme-studio: image load failed: {exc}", flush=True)
            return

        try:
            colors = quantize.extract_palette(pixbuf, 16)
            palette = quantize.palette_from_colors(colors)
        except Exception as exc:
            self._toast("Palette extraction failed")
            print(f"terminal-theme-studio: extraction failed: {exc}", flush=True)
            return

        self._source_path = path

        try:
            thumb = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, _THUMB, _THUMB, True
            )
        except GLib.Error:
            thumb = pixbuf
        self._picture.set_paintable(Gdk.Texture.new_for_pixbuf(thumb))
        self._stack.set_visible_child(self._picture)

        name = PurePath(path).stem or "image"
        self.emit("image-palette", palette, name)
