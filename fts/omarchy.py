"""Omarchy colors.toml: read, resolve, write, and apply themes.

The parser/resolver mirrors ``/usr/sbin/omarchy-theme-color`` (the
alias/fallback cascade, the mix integer math, and mode detection) for
every real theme.  For degenerate files the binary's awk fallbacks can
emit garbage shades; here unset derived keys simply stay unset, which is
the saner behaviour for library previews.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import paths
from .palette import Palette, mix

__all__ = [
    "load_colors_toml",
    "colors_toml_text",
    "save_user_theme",
    "apply_full_theme",
    "list_local_themes",
]


# --------------------------------------------------------------------------
# colors.toml parsing (mirrors parse_colors_file in omarchy-theme-color)
# --------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_VALUE_RE = re.compile(r"^[A-Za-z0-9#(),._+/% -]*$")


def _parse_colors_file(path: Path) -> dict[str, str]:
    """Raw key -> value pairs from a colors.toml, like the bash parser.

    Values quoted with ' or " are taken from between the quotes (dropping
    inline comments); unquoted values are whitespace-trimmed.  Keys with
    unsupported characters and values with unsupported characters are
    skipped.  An empty value behaves like an unset key downstream.
    """
    raw: dict[str, str] = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            # strip quotes and spaces from the key (same as bash: ${key//[\"\' ]/})
            key = re.sub(r"""["' ]""", "", key)
            if not key or key.startswith("#"):
                continue
            if not _KEY_RE.match(key):
                continue
            if any(q in value for q in "\"'"):
                # extract value between the first and last quote
                start = min(
                    (i for i in (value.find('"'), value.find("'")) if i != -1),
                    default=-1,
                )
                end = max(value.rfind('"'), value.rfind("'"))
                if end <= start:
                    continue
                value = value[start + 1 : end]
            else:
                value = value.strip()
            if not _VALUE_RE.match(value):
                continue
            raw[key] = value
    return raw


# --------------------------------------------------------------------------
# resolution cascade (mirrors resolve_theme_colors in omarchy-theme-color)
# --------------------------------------------------------------------------

# canonical -> legacy short name; canonical wins if both defined
_LEGACY_PALETTE_ALIAS = {
    "background": "bg",
    "dark_background": "dark_bg",
    "darker_background": "darker_bg",
    "lighter_background": "lighter_bg",
    "foreground": "fg",
    "dark_foreground": "dark_fg",
    "light_foreground": "light_fg",
    "bright_foreground": "bright_fg",
}

# canonical semantic name -> legacy ANSI name
_LEGACY_ANSI_ALIAS = {
    "red": "color1",
    "green": "color2",
    "yellow": "color3",
    "blue": "color4",
    "magenta": "color5",
    "cyan": "color6",
    "bright_red": "color9",
    "bright_green": "color10",
    "bright_yellow": "color11",
    "bright_blue": "color12",
    "bright_magenta": "color13",
    "bright_cyan": "color14",
}

# legacy ANSI name -> resolved semantic name (applied at the end)
_ANSI_ALIAS = {
    "color0": "background",
    "color1": "red",
    "color2": "green",
    "color3": "yellow",
    "color4": "blue",
    "color5": "magenta",
    "color6": "cyan",
    "color7": "foreground",
    "color8": "muted",
    "color9": "bright_red",
    "color10": "bright_green",
    "color11": "bright_yellow",
    "color12": "bright_blue",
    "color13": "bright_magenta",
    "color14": "bright_cyan",
    "color15": "bright_foreground",
}

_BRIGHT_DERIVED = (
    ("bright_red", "red"),
    ("bright_yellow", "yellow"),
    ("bright_green", "green"),
    ("bright_cyan", "cyan"),
    ("bright_blue", "blue"),
    ("bright_magenta", "magenta"),
)


def _resolve_colors(raw: dict[str, str], colors_dir: Path | None = None) -> dict[str, str]:
    """Apply the full omarchy-theme-color fallback cascade to raw pairs."""
    c = dict(raw)

    def has(key: str) -> bool:
        return bool(c.get(key))

    def alias(key: str, source: str) -> None:
        """Set key from source when key is unset and source is set."""
        if not has(key) and has(source):
            c[key] = c[source]

    def chain(key: str, *sources: str) -> None:
        """Set key from the first set source (the ?? chain)."""
        if has(key):
            return
        for source in sources:
            if has(source):
                c[key] = c[source]
                return

    # 1. legacy short-name palette aliases (canonical name wins)
    for canon, short in _LEGACY_PALETTE_ALIAS.items():
        alias(canon, short)

    # 2. ANSI-only themes: background<-color0 / foreground<-color7,
    #    then color0<-background / color7<-foreground (semantic wins).
    chain("background", "color0")
    chain("foreground", "color7")
    if has("background"):
        c["color0"] = c["background"]
    if has("foreground"):
        c["color7"] = c["foreground"]

    # 3. legacy ANSI aliases + purple aliases
    for canon, legacy in _LEGACY_ANSI_ALIAS.items():
        alias(canon, legacy)
    alias("magenta", "purple")
    alias("bright_magenta", "bright_purple")

    # 4. derived roles, in the script's exact order
    chain("light_foreground", "color7", "foreground")
    chain("bright_foreground", "color15", "foreground")
    if has("bright_foreground"):
        c["cursor"] = c["bright_foreground"]  # always overwritten
    chain("lighter_background", "color0", "background")
    chain("dark_foreground", "color8", "foreground")
    chain("muted", "color8", "dark_foreground")
    chain("selection", "selection_background", "color8", "color0", "background")
    alias("selection_background", "selection")
    alias("selection_foreground", "bright_foreground")
    alias("orange", "yellow")
    if not has("brown") and has("orange"):
        c["brown"] = mix(c["orange"], "#000000", 0.5)

    # 5. derived shades (derived when missing, like the bash script)
    if has("background"):
        if not has("dark_background"):
            c["dark_background"] = mix(c["background"], "#000000", 0.25)
        if not has("darker_background"):
            c["darker_background"] = mix(c["background"], "#000000", 0.5)
    for bright, base in _BRIGHT_DERIVED:
        if not has(bright) and has(base):
            c[bright] = mix(c[base], "#ffffff", 0.2)
    alias("purple", "magenta")
    alias("bright_purple", "bright_magenta")

    # 6. keep legacy ANSI names usable alongside semantic themes
    for legacy, canon in _ANSI_ALIAS.items():
        alias(legacy, canon)

    # 7. keep short palette names usable alongside canonical themes
    for canon, short in _LEGACY_PALETTE_ALIAS.items():
        if has(canon):
            c[short] = c[canon]

    # 8. mode
    if not has("mode"):
        alias("mode", "theme_type")
    if not has("mode") and colors_dir is not None:
        try:
            if (colors_dir / "light.mode").exists():
                c["mode"] = "light"
        except OSError:
            pass
    if not has("mode"):
        bg = c.get("background") or ""
        if re.match(r"^#[0-9A-Fa-f]{6}$", bg):
            lum = sum(int(bg[i : i + 2], 16) for i in (1, 3, 5))
            c["mode"] = "light" if lum > 382 else "dark"
        else:
            c["mode"] = "dark"
    c["theme_type"] = c["mode"]

    return c


# --------------------------------------------------------------------------
# Palette <-> colors.toml
# --------------------------------------------------------------------------

def load_colors_toml(path) -> Palette:
    """Load a colors.toml into a Palette, mirroring omarchy-theme-color.

    Raises FileNotFoundError when the file does not exist and ValueError
    when the file carries no palette data at all.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no such colors.toml: {path}")
    raw = _parse_colors_file(path)
    resolved = _resolve_colors(raw, colors_dir=path.parent)

    def val(key: str) -> str | None:
        v = resolved.get(key)
        return v or None

    roles = {
        "background": val("background"),
        "foreground": val("foreground"),
        "cursor": val("cursor"),
        "selection_bg": val("selection_background"),
        "selection_fg": val("selection_foreground"),
        "regular0": val("color0"),
        "regular1": val("color1") or val("red"),
        "regular2": val("color2") or val("green"),
        "regular3": val("color3") or val("yellow"),
        "regular4": val("color4") or val("blue"),
        "regular5": val("color5") or val("magenta"),
        "regular6": val("color6") or val("cyan"),
        "regular7": val("color7"),
        "bright0": val("color8"),
        "bright1": val("color9") or val("bright_red"),
        "bright2": val("color10") or val("bright_green"),
        "bright3": val("color11") or val("bright_yellow"),
        "bright4": val("color12") or val("bright_blue"),
        "bright5": val("color13") or val("bright_magenta"),
        "bright6": val("color14") or val("bright_cyan"),
        "bright7": val("color15"),
    }
    if all(v is None for v in roles.values()):
        raise ValueError(f"no palette data in {path}")

    return Palette.from_dict(roles)


def colors_toml_text(p: Palette, *, mode: str | None = None) -> str:
    """Render a full semantic colors.toml (values WITH leading '#').

    Emits every key Omarchy's pipeline expects, in the shape of the stock
    catppuccin theme, including the purple/bright_purple aliases and the
    derived orange/brown/dark_background/... keys.

    bright_foreground is the cursor role per SPEC, so on a full Omarchy
    apply slot 15 (bright7/OSC ]4;15) renders as the cursor color; the
    Foot-only apply keeps the distinct bright7 role.  The two modes differ
    at ]4;15 only when bright7 != cursor.
    """
    if mode not in ("dark", "light"):
        # omarchy-theme-color's auto-detect: light when r+g+b > 382.
        bg = p.background.lstrip("#")
        rgb_sum = sum(int(bg[i : i + 2], 16) for i in (0, 2, 4))
        mode = "light" if rgb_sum > 382 else "dark"

    muted = p.bright0
    lines = [
        f'mode = "{mode}"',
        "",
        f'accent = "{p.regular4}"',
        f'selection = "{p.selection_bg}"',
        f'selection_foreground = "{p.selection_fg}"',
        f'muted = "{muted}"',
        "",
        f'background = "{p.background}"',
        f'dark_background = "{mix(p.background, "#000000", 0.25)}"',
        f'darker_background = "{mix(p.background, "#000000", 0.5)}"',
        # omarchy's own fallback for lighter_background is just background;
        # a 15% mix toward white gives templates a usable lighter shade.
        f'lighter_background = "{mix(p.background, "#ffffff", 0.15)}"',
        "",
        f'foreground = "{p.foreground}"',
        f'dark_foreground = "{muted}"',
        f'light_foreground = "{p.foreground}"',
        f'bright_foreground = "{p.cursor}"',
        "",
        f'red = "{p.regular1}"',
        f'green = "{p.regular2}"',
        f'yellow = "{p.regular3}"',
        f'blue = "{p.regular4}"',
        f'magenta = "{p.regular5}"',
        f'purple = "{p.regular5}"',
        f'cyan = "{p.regular6}"',
        "",
        f'orange = "{p.regular3}"',
        f'brown = "{mix(p.regular3, "#000000", 0.5)}"',
        "",
        f'bright_red = "{p.bright1}"',
        f'bright_green = "{p.bright2}"',
        f'bright_yellow = "{p.bright3}"',
        f'bright_blue = "{p.bright4}"',
        f'bright_magenta = "{p.bright5}"',
        f'bright_purple = "{p.bright5}"',
        f'bright_cyan = "{p.bright6}"',
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# writing / applying
# --------------------------------------------------------------------------

def normalize_slug(slug: str) -> str:
    """Normalize a theme name like omarchy-theme-set does.

    Strips ``<...>`` groups, lowercases, turns spaces into dashes.  Raises
    ValueError for names that would be empty, start with '.', or contain
    '/'.
    """
    name = re.sub(r"<[^>]*>", "", slug or "")
    name = name.lower().replace(" ", "-")
    if not name or name.startswith(".") or "/" in name:
        raise ValueError(f"invalid theme name: {slug!r}")
    return name


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically (tmp file in the same dir + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def save_user_theme(p: Palette, slug: str) -> Path:
    """Write the palette as a user theme colors.toml; returns the path.

    Normalizes the slug like omarchy-theme-set and refuses dangerous names.
    """
    name = normalize_slug(slug)
    target = paths.omarchy_user_themes() / name / "colors.toml"
    _atomic_write(target, colors_toml_text(p))
    return target


def apply_full_theme(slug: str) -> None:
    """Run omarchy-theme-set for the given slug (full Omarchy apply).

    Raises RuntimeError with the command's stderr when it exits nonzero.
    """
    name = normalize_slug(slug)
    binary = shutil.which("omarchy-theme-set")
    if binary:
        cmd: list[str] = [binary, name]
    else:  # fall back to the user-facing CLI spelling
        cmd = ["omarchy", "theme", "set", name]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"omarchy-theme-set {name!r} failed "
            f"(exit {proc.returncode}): {proc.stderr.strip()}"
        )


def list_local_themes() -> "list[LibraryEntry]":  # noqa: F821
    """Scan system + user Omarchy theme dirs for colors.toml files.

    Directories without a colors.toml are skipped; unreadable/broken
    colors.toml files are skipped silently.  System entries carry
    ``source == "omarchy"``, user entries ``source == "user"``.
    """
    from .library import LibraryEntry  # deferred to avoid the import cycle

    entries: list[LibraryEntry] = []
    for source, root in (
        ("omarchy", paths.omarchy_system_themes()),
        ("user", paths.omarchy_user_themes()),
    ):
        try:
            theme_dirs = sorted(p for p in root.iterdir() if p.is_dir())
        except OSError:
            continue
        for theme_dir in theme_dirs:
            colors = theme_dir / "colors.toml"
            if not colors.is_file():
                continue
            try:
                palette = load_colors_toml(colors)
            except Exception:
                continue
            entries.append(
                LibraryEntry(
                    name=theme_dir.name,
                    source=source,
                    palette=palette,
                    origin=str(colors),
                )
            )
    return entries
