"""Palette model and color math.

The :class:`Palette` dataclass is the internal working palette (21 roles,
hex ``#rrggbb``).  Color helpers mirror Omarchy's ``omarchy-theme-color``
integer math exactly where behavior must match byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import ClassVar

__all__ = [
    "Palette",
    "ROLE_GROUPS",
    "ROLE_LABELS",
    "mix",
    "relative_luminance",
    "is_dark",
    "hex_to_rgba",
    "rgba_to_hex",
    "ansi_index",
]


@dataclass(frozen=True)
class Palette:
    """The 21 terminal color roles, hex ``#rrggbb`` (leading ``#``)."""

    background: str
    foreground: str
    cursor: str
    selection_bg: str
    selection_fg: str
    regular0: str
    regular1: str
    regular2: str
    regular3: str
    regular4: str
    regular5: str
    regular6: str
    regular7: str
    bright0: str
    bright1: str
    bright2: str
    bright3: str
    bright4: str
    bright5: str
    bright6: str
    bright7: str

    #: Catppuccin Mocha -- also Omarchy's default look.
    DEFAULTS: ClassVar[dict[str, str]] = {
        "background": "#1e1e2e",
        "foreground": "#cdd6f4",
        "cursor": "#cdd6f4",
        "selection_bg": "#45475a",
        "selection_fg": "#cdd6f4",
        "regular0": "#1e1e2e",
        "regular1": "#f38ba8",
        "regular2": "#a6e3a1",
        "regular3": "#f9e2af",
        "regular4": "#89b4fa",
        "regular5": "#f5c2e7",
        "regular6": "#94e2d5",
        "regular7": "#cdd6f4",
        "bright0": "#585b70",
        "bright1": "#f38ba8",
        "bright2": "#a6e3a1",
        "bright3": "#f9e2af",
        "bright4": "#89b4fa",
        "bright5": "#f5c2e7",
        "bright6": "#94e2d5",
        "bright7": "#cdd6f4",
    }

    def to_dict(self) -> dict[str, str]:
        """All 21 roles as a plain dict."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict, /) -> "Palette":
        """Build a Palette; missing or malformed keys fall back to DEFAULTS."""
        kwargs = {}
        for f in fields(cls):
            value = _norm_hex(d.get(f.name)) if f.name in d else None
            kwargs[f.name] = value if value is not None else cls.DEFAULTS[f.name]
        return cls(**kwargs)


ROLE_GROUPS: list[tuple[str, list[str]]] = [
    (
        "Terminal",
        ["background", "foreground", "cursor", "selection_bg", "selection_fg"],
    ),
    ("Regular", [f"regular{i}" for i in range(8)]),
    ("Bright", [f"bright{i}" for i in range(8)]),
]

_ROLE_NAMES = {
    "background": "Background",
    "foreground": "Foreground",
    "cursor": "Cursor",
    "selection_bg": "Selection BG",
    "selection_fg": "Selection FG",
    "regular0": "Black",
    "regular1": "Red",
    "regular2": "Green",
    "regular3": "Yellow",
    "regular4": "Blue",
    "regular5": "Magenta",
    "regular6": "Cyan",
    "regular7": "White",
}
_ROLE_NAMES.update(
    {f"bright{i}": f"Bright {_ROLE_NAMES[f'regular{i}']}" for i in range(8)}
)

ROLE_LABELS: dict[str, str] = _ROLE_NAMES


# --------------------------------------------------------------------------
# hex parsing / formatting
# --------------------------------------------------------------------------

def _parse_hex(value: str) -> tuple[int, int, int, int]:
    """Parse '#rgb' / '#rrggbb' / '#rrggbbaa' (hash optional) to 0-255 ints.

    Raises ValueError on malformed input.
    """
    if not isinstance(value, str):
        raise ValueError(f"not a hex color: {value!r}")
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 6:
        s += "ff"
    if len(s) != 8:
        raise ValueError(f"not a hex color: {value!r}")
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = int(s[6:8], 16)
    except ValueError as exc:
        raise ValueError(f"not a hex color: {value!r}") from exc
    return r, g, b, a


def _norm_hex(value) -> str | None:
    """Normalize to lowercase '#rrggbb'; None when not a valid color."""
    try:
        r, g, b, _a = _parse_hex(value)
    except (ValueError, TypeError):
        return None
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------
# color math
# --------------------------------------------------------------------------

def mix(a: str, b: str, amount: float) -> str:
    """Mix hex ``a`` toward hex ``b`` by ``amount`` (0.0 = a, 1.0 = b).

    Mirrors Omarchy's ``mix_color`` (awk) exactly: per channel
    ``int(start * (1 - amount) + end * amount + 0.5)`` with amount clamped
    to 0..1.  Amounts > 1 are also treated like the awk fallback as a
    percentage (e.g. ``25`` means 0.25) to be lenient with callers.
    """
    ar, ag, ab, _ = _parse_hex(a)
    br, bg_, bb, _ = _parse_hex(b)
    t = float(amount)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        if t <= 100.0:
            t = t / 100.0
        else:
            t = 1.0
    r = int(ar * (1 - t) + br * t + 0.5)
    g = int(ag * (1 - t) + bg_ * t + 0.5)
    bl = int(ab * (1 - t) + bb * t + 0.5)
    return f"#{r:02x}{g:02x}{bl:02x}"


def relative_luminance(hex: str) -> float:
    """WCAG sRGB relative luminance, 0..1."""
    r, g, b, _ = _parse_hex(hex)

    def lin(c: int) -> float:
        c = c / 255.0
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def is_dark(hex: str) -> bool:
    """True when the color's relative luminance is below 0.5."""
    return relative_luminance(hex) < 0.5


def hex_to_rgba(s: str) -> tuple[float, float, float, float]:
    """Hex color (with or without '#', 3/6/8 digits) to floats 0..1."""
    r, g, b, a = _parse_hex(s)
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def rgba_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    """Floats 0..1 (any out-of-range values are clamped) to '#rrggbb'."""
    def ch(v: float) -> int:
        v = int(round(min(max(v, 0.0), 1.0) * 255.0))
        return min(max(v, 0), 255)

    return f"#{ch(r):02x}{ch(g):02x}{ch(b):02x}"


def ansi_index(role: str) -> int:
    """'regular0'->0 ... 'regular7'->7, 'bright0'->8 ... 'bright7'->15.

    Raises ValueError for anything else.
    """
    for i in range(8):
        if role == f"regular{i}":
            return i
        if role == f"bright{i}":
            return 8 + i
    raise ValueError(f"not an ANSI palette role: {role!r}")
