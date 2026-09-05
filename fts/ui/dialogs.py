"""Dialogs: save-as-Omarchy-theme and the color test.

Both are :class:`Adw.Dialog` subclasses; every shell-out and file write
is wrapped, failures surface as toasts or :class:`Adw.AlertDialog` --
they never raise into the main loop.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from .. import colortest, exporters, omarchy  # noqa: E402
from .colortest_view import ColorTestView  # noqa: E402

__all__ = ["ColorTestDialog", "ExportDialog", "SaveThemeDialog"]


class ColorTestDialog(Adw.Dialog):
    """In-app spectrum plus a 'Run in Foot' launcher."""

    def __init__(self, get_palette, toast, **kwargs) -> None:
        super().__init__(**kwargs)
        self._get_palette = get_palette
        self._toast = toast
        self._tmpfiles: list[Path] = []

        self.set_title("Color Test")
        self.set_content_width(940)
        self.set_content_height(620)

        self._view = ColorTestView()
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._view)

        run_btn = Gtk.Button(label="Run in Foot")
        run_btn.add_css_class("suggested-action")
        run_btn.set_tooltip_text("Open a new Foot running the color test script")
        run_btn.connect("clicked", self._on_run)

        header = Adw.HeaderBar()
        header.pack_start(run_btn)
        header.set_title_widget(
            Adw.WindowTitle(title="Color test", subtitle="in-app spectrum + the real Foot")
        )

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

        self.connect("closed", self._on_closed)
        self.refresh()

    def refresh(self) -> None:
        """Re-sync the spectrum with the current working palette."""
        self._view.set_palette(self._get_palette())

    # ------------------------------------------------------------------
    # run in foot
    # ------------------------------------------------------------------

    def _on_run(self, button) -> None:
        palette = self._get_palette()
        foot = shutil.which("foot")
        if foot:
            cmd = [foot, "--title=Terminal Theme Studio — Color Test", "sh", ""]
        else:
            xdg = shutil.which("xdg-terminal-exec")
            if not xdg:
                self._toast("Neither foot nor xdg-terminal-exec was found")
                return
            cmd = [xdg, "sh", ""]

        # Unique-name the script and keep it until the dialog closes: the
        # spawned shell reads it at startup, and deleting immediately would
        # race foot.  Written to $XDG_RUNTIME_DIR (or /tmp) with mode 0700;
        # removed on dialog close, so leftovers are bounded and unique.
        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        try:
            fd, name = tempfile.mkstemp(
                prefix="fts-colortest-", suffix=".sh", dir=base
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(colortest.script_text(palette))
            os.chmod(name, 0o700)
        except OSError as exc:
            self._toast(f"Could not write color test script: {exc}")
            print(f"terminal-theme-studio: {exc}", file=sys.stderr, flush=True)
            return
        self._tmpfiles.append(Path(name))
        cmd[-1] = name

        try:
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self._toast(f"Could not launch terminal: {exc}")
            print(f"terminal-theme-studio: {exc}", file=sys.stderr, flush=True)
            return
        self._toast("Color test running in a new terminal")

    def _on_closed(self, dialog) -> None:
        for path in self._tmpfiles:
            try:
                path.unlink()
            except OSError:
                pass
        self._tmpfiles.clear()


class SaveThemeDialog(Adw.Dialog):
    """Save the working palette as a named Omarchy user theme."""

    def __init__(
        self, get_palette, default_name, toast, on_saved=None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._get_palette = get_palette
        self._toast = toast
        self._on_saved = on_saved

        self.set_title("Save as Omarchy Theme")
        self.set_content_width(480)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)

        header = Adw.HeaderBar()
        header.pack_end(save_btn)
        header.set_title_widget(
            Adw.WindowTitle(title="Save as Omarchy theme", subtitle="")
        )

        self._entry = Adw.EntryRow(title="Theme name")
        self._entry.set_text(default_name or "")

        self._switch = Adw.SwitchRow(
            title="Apply now with `omarchy theme set`",
            subtitle=(
                "Full Omarchy theme (Foot, Ghostty, Hyprland, waybar…) — "
                "opt-in; off = save only"
            ),
        )

        group = Adw.PreferencesGroup()
        group.add(self._entry)
        group.add(self._switch)

        self._slug = Gtk.Label(xalign=0.0, wrap=True)
        self._slug.add_css_class("caption")
        self._slug.add_css_class("dim-label")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_valign(Gtk.Align.START)
        content.append(group)
        content.append(self._slug)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)
        self.set_child(toolbar)

        self._entry.connect("changed", self._update_slug)
        self._update_slug()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _slug_of(self, name: str) -> str | None:
        try:
            return omarchy.normalize_slug(name)
        except ValueError:
            return None

    def _update_slug(self, *args) -> None:
        slug = self._slug_of(self._entry.get_text().strip())
        if slug is None:
            self._slug.set_text(
                "Enter a name (must not be empty, start with '.', or contain '/')"
            )
            self._slug.add_css_class("error")
        else:
            self._slug.set_text(
                f"Saves to ~/.config/omarchy/themes/{slug}/colors.toml"
            )
            self._slug.remove_css_class("error")

    def _alert(self, heading: str, body: str) -> None:
        alert = Adw.AlertDialog(heading=heading, body=body)
        alert.add_response("close", "OK")
        alert.set_close_response("close")
        alert.present(self)

    def _on_save(self, button) -> None:
        name = self._entry.get_text().strip()
        slug = self._slug_of(name)
        if slug is None:
            self._toast(f"Invalid theme name: {name!r}")
            return
        try:
            path = omarchy.save_user_theme(self._get_palette(), name)
        except Exception as exc:
            self._alert("Could not save theme", str(exc))
            print(
                f"terminal-theme-studio: save_user_theme failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return

        if self._switch.get_active():
            try:
                omarchy.apply_full_theme(slug)
            except Exception as exc:
                # The theme itself was saved; only the full apply failed.
                self._alert(
                    "Theme saved, but the full apply failed",
                    f"colors.toml written to {path}\n\n"
                    f"omarchy theme set failed: {exc}",
                )
                print(
                    f"terminal-theme-studio: apply_full_theme failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                if self._on_saved is not None:
                    self._on_saved(slug, path)
                self.close()
                return
            self._toast(f"Theme “{slug}” saved and applied")
        else:
            self._toast(f"Theme “{slug}” saved to your Omarchy themes")

        if self._on_saved is not None:
            self._on_saved(slug, path)
        self.close()


class ExportDialog(Adw.Dialog):
    """Save the working palette as a theme file for another terminal.

    Export is file-based and user-chosen only: the studio renders the
    palette and writes it wherever the save dialog points; it never
    edits another tool's config or Omarchy-managed state.
    """

    def __init__(self, get_palette, default_name, toast, **kwargs) -> None:
        super().__init__(**kwargs)
        self._get_palette = get_palette
        self._default_name = default_name or "theme"
        self._toast = toast

        self.set_title("Export")
        self.set_content_width(520)

        export_btn = Gtk.Button(label="Export…")
        export_btn.add_css_class("suggested-action")
        export_btn.connect("clicked", self._on_export)

        header = Adw.HeaderBar()
        header.pack_end(export_btn)
        header.set_title_widget(
            Adw.WindowTitle(
                title="Export theme",
                subtitle="save the palette for any terminal",
            )
        )

        group = Adw.PreferencesGroup(
            description="Renders the working palette; you choose where the file goes."
        )
        self._first_check: Gtk.CheckButton | None = None
        self._checks: dict[str, Gtk.CheckButton] = {}
        for spec in exporters.FORMATS:
            check = Gtk.CheckButton()
            if self._first_check is None:
                self._first_check = check
                check.set_active(True)
            else:
                check.set_group(self._first_check)
            self._checks[spec.id] = check

            row = Adw.ActionRow(
                title=spec.label,
                subtitle=exporters.suggested_basename(spec.id, self._default_name),
            )
            row.add_prefix(check)
            row.set_activatable_widget(check)
            check.connect("toggled", self._on_toggled, spec.id)
            group.add(row)

        self._hint = Gtk.Label(xalign=0.0, wrap=True)
        self._hint.add_css_class("caption")
        self._hint.add_css_class("dim-label")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.set_valign(Gtk.Align.START)
        content.append(group)
        content.append(self._hint)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)
        self.set_child(toolbar)

        self._update_hint()

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _selected(self) -> str:
        for fmt_id, check in self._checks.items():
            if check.get_active():
                return fmt_id
        return exporters.FORMATS[0].id

    def _on_toggled(self, check, fmt_id: str) -> None:
        if check.get_active():
            self._update_hint()

    def _update_hint(self) -> None:
        self._hint.set_text(
            "Everything a terminal needs is 16 ANSI colors plus cursor and "
            "selection — each format is the same palette in its own shape."
        )

    def _alert(self, heading: str, body: str) -> None:
        alert = Adw.AlertDialog(heading=heading, body=body)
        alert.add_response("close", "OK")
        alert.set_close_response("close")
        alert.present(self)

    def _on_export(self, button) -> None:
        fmt_id = self._selected()
        palette = self._get_palette()
        title = self._default_name

        fd = Gtk.FileDialog()
        fd.set_initial_name(exporters.suggested_basename(fmt_id, title))
        root = self.get_root()
        parent = root if isinstance(root, Gtk.Window) else None
        fd.save(parent, None, self._on_save_finished, fmt_id, palette, title)

    def _on_save_finished(self, fd, result, fmt_id, palette, title) -> None:
        try:
            file = fd.save_finish(result)
        except Exception:
            return  # dialog cancelled
        if file is None:
            return
        path = file.get_path()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(exporters.render(fmt_id, palette, title))
        except OSError as exc:
            self._alert("Could not export", str(exc))
            print(
                f"terminal-theme-studio: export to {path} failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            return
        self._toast(f"Exported {path}")
        self.close()
