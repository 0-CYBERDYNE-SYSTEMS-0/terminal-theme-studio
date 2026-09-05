"""Searchable palette library (left pane).

Lists every :func:`fts.library.load_all` entry (bundled community
palettes + system/user Omarchy themes) sorted by name, with live
substring filtering via :func:`fts.library.search` on each keystroke
(rows are built once and filtered by visibility, so typing never
rebuilds widgets).  Selecting a row emits ``entry-selected(entry)``.
The row of the currently-active entry shows a subtle check marker.
"""

from __future__ import annotations

from pathlib import PurePath

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GObject, Gtk, Pango  # noqa: E402

from .. import library  # noqa: E402
from ..library import LibraryEntry  # noqa: E402

__all__ = ["LibraryPanel"]

_CHECK_ICON = "object-select-symbolic"


class LibraryPanel(Gtk.Box):
    """Search entry + scrolled list of all library entries."""

    __gsignals__ = {
        "entry-selected": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (GObject.TYPE_PYOBJECT,),
        )
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        self._entries: list[LibraryEntry] = []
        self._active: LibraryEntry | None = None

        self.set_size_request(240, -1)

        self._search = Gtk.SearchEntry()
        self._search.set_margin_top(8)
        self._search.set_margin_start(8)
        self._search.set_margin_end(8)
        self._search.connect("search-changed", self._on_search_changed)
        self.append(self._search)

        self._list = Gtk.ListBox()
        self._list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list.set_activate_on_single_click(True)
        self._list.connect("row-activated", self._on_row_activated)
        self._list.set_margin_bottom(8)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self._list)
        scroll.set_vexpand(True)
        self.append(scroll)

        self.refresh()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @property
    def entries(self) -> list[LibraryEntry]:
        return list(self._entries)

    def refresh(self) -> None:
        """Reload all entries (keeps the current query + active marker)."""
        query = self._search.get_text()
        self._entries = sorted(library.load_all(), key=lambda e: e.name.lower())

        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt

        for entry in self._entries:
            self._list.append(self._create_row(entry))

        if self._active is not None:
            self._active = self._find(self._active)
        self._sync_markers()
        self._apply_query(query)

    def set_active_entry(self, entry: LibraryEntry | None) -> None:
        """Mark the entry as active (check marker) / clear the marker."""
        self._active = entry
        if entry is None:
            selected = self._list.get_selected_row()
            if selected is not None:
                self._list.unselect_row(selected)
        self._sync_markers()

    # ------------------------------------------------------------------
    # search filtering
    # ------------------------------------------------------------------

    def _apply_query(self, query: str) -> None:
        visible = {id(e) for e in library.search(self._entries, query)}
        row = self._list.get_first_child()
        while row is not None:
            entry = getattr(row, "fts_entry", None)
            if entry is not None:
                row.set_visible(id(entry) in visible)
            row = row.get_next_sibling()

    def _on_search_changed(self, entry) -> None:
        self._apply_query(entry.get_text())

    # ------------------------------------------------------------------
    # rows
    # ------------------------------------------------------------------

    def _find(self, entry: LibraryEntry) -> LibraryEntry | None:
        return next(
            (
                e
                for e in self._entries
                if e.name == entry.name and e.origin == entry.origin
            ),
            None,
        )

    @staticmethod
    def _subtitle(entry: LibraryEntry) -> str:
        if entry.source == "community":
            return "community palette"
        where = str(PurePath(entry.origin).parent)
        return f"omarchy · {where}" if entry.source == "omarchy" else f"user · {where}"

    def _create_row(self, entry: LibraryEntry) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.fts_entry = entry

        icon = Gtk.Image(icon_name=_CHECK_ICON)
        icon.set_pixel_size(12)
        icon.set_visible(False)
        row.fts_icon = icon

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text.set_hexpand(True)
        name = Gtk.Label(
            label=entry.name,
            xalign=0.0,
            ellipsize=Pango.EllipsizeMode.END,
            single_line_mode=True,
        )
        sub = Gtk.Label(
            label=self._subtitle(entry),
            xalign=0.0,
            ellipsize=Pango.EllipsizeMode.END,
            single_line_mode=True,
        )
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        text.append(name)
        text.append(sub)

        box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            margin_top=4,
            margin_bottom=4,
            margin_start=8,
            margin_end=8,
        )
        box.append(icon)
        box.append(text)
        row.set_child(box)
        return row

    def _on_row_activated(self, box, row) -> None:
        entry = getattr(row, "fts_entry", None)
        if entry is not None:
            self.emit("entry-selected", entry)

    def _mark_row(self, row) -> None:
        icon = getattr(row, "fts_icon", None)
        if icon is not None:
            icon.set_visible(
                self._active is not None and row.fts_entry is self._active
            )

    def _sync_markers(self) -> None:
        row = self._list.get_first_child()
        while row is not None:
            if isinstance(row, Gtk.ListBoxRow):
                self._mark_row(row)
            row = row.get_next_sibling()
