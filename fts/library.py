"""Theme library: bundled community palettes + local Omarchy themes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .omarchy import list_local_themes
from .palette import Palette

__all__ = ["LibraryEntry", "load_bundled", "load_all", "search"]

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "palettes.json"


@dataclass(frozen=True)
class LibraryEntry:
    """One browsable theme.

    source: "community" | "omarchy" | "user"
    origin: vendored palette id (community) or colors.toml path (local)
    """

    name: str
    source: str
    palette: Palette
    origin: str


def load_bundled() -> list[LibraryEntry]:
    """Load the vendored community palettes from data/palettes.json.

    Malformed entries are skipped; a missing file yields an empty list
    (the library stays browsable via local themes).
    """
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    entries: list[LibraryEntry] = []
    for item in data if isinstance(data, list) else []:
        try:
            name = str(item["name"])
            palette = Palette.from_dict(item["palette"])
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
        entries.append(
            LibraryEntry(
                name=name,
                source="community",
                palette=palette,
                origin=name,
            )
        )
    return entries


def load_all() -> list[LibraryEntry]:
    """Bundled community palettes plus local Omarchy themes."""
    return load_bundled() + list_local_themes()


def search(entries: list[LibraryEntry], query: str) -> list[LibraryEntry]:
    """Case-insensitive substring filter on name; empty query returns all."""
    q = (query or "").strip().lower()
    if not q:
        return list(entries)
    return [e for e in entries if q in e.name.lower()]
