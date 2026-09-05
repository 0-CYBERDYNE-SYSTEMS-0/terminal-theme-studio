"""Foot-only override: palette.ini plus the foot.ini include block.

The studio owns ``~/.config/foot/palette.ini`` (regenerated on every
apply, hex WITHOUT '#', matching Omarchy's foot.ini.tpl) and keeps a
marker-guarded ``[main] include=`` block at the end of foot.ini so the
studio's palette wins over Omarchy's themed include (foot merges repeated
sections; the later parse wins) without destroying Omarchy's refresh path.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from . import osc, paths
from .palette import Palette

__all__ = [
    "MARK_BEGIN",
    "MARK_END",
    "palette_ini_text",
    "write_palette_override",
    "ensure_include",
    "clear_palette_override",
    "push_override_live",
]

MARK_BEGIN = "# >>> terminal-theme-studio >>>"
MARK_END = "# <<< terminal-theme-studio <<<"

_HEADER = (
    "# ~/.config/foot/palette.ini -- owned by Terminal Theme Studio.\n"
    "# Regenerated on every apply; hand-edits will be lost.\n"
    "# Remove via the studio (or delete this file and strip the marked block\n"
    "# in foot.ini) to fall back to the Omarchy theme.\n"
)


def palette_ini_text(p: Palette) -> str:
    """Render palette.ini: [colors-dark], hex WITHOUT '#', tpl key set."""
    def raw(hexcolor: str) -> str:
        return hexcolor.lstrip("#")

    lines = [
        _HEADER,
        "[colors-dark]",
        f"foreground={raw(p.foreground)}",
        f"background={raw(p.background)}",
        f"selection-foreground={raw(p.selection_fg)}",
        f"selection-background={raw(p.selection_bg)}",
        "",
        f"cursor={raw(p.background)} {raw(p.cursor)}",
        "",
        f"regular0={raw(p.regular0)}",
        f"regular1={raw(p.regular1)}",
        f"regular2={raw(p.regular2)}",
        f"regular3={raw(p.regular3)}",
        f"regular4={raw(p.regular4)}",
        f"regular5={raw(p.regular5)}",
        f"regular6={raw(p.regular6)}",
        f"regular7={raw(p.regular7)}",
        f"bright0={raw(p.bright0)}",
        f"bright1={raw(p.bright1)}",
        f"bright2={raw(p.bright2)}",
        f"bright3={raw(p.bright3)}",
        f"bright4={raw(p.bright4)}",
        f"bright5={raw(p.bright5)}",
        f"bright6={raw(p.bright6)}",
        f"bright7={raw(p.bright7)}",
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_palette_override(p: Palette) -> None:
    """Write palette.ini atomically and make sure foot.ini includes it."""
    _atomic_write(paths.palette_ini(), palette_ini_text(p))
    ensure_include()


def include_block() -> str:
    """The marker-guarded [main] include block (ends with a newline)."""
    return (
        f"{MARK_BEGIN}\n"
        f"[main]\n"
        f"include={paths.palette_ini()}\n"
        f"{MARK_END}\n"
    )


def _read_text(path: Path) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _strip_blocks(lines: list[str]) -> list[str]:
    """Remove every marker block (and its prepended blank line)."""
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if not skipping and stripped.startswith(MARK_BEGIN):
            skipping = True
            # also drop the single blank line we prepend when appending
            if out and out[-1].strip() == "":
                out.pop()
            continue
        if skipping:
            if stripped.startswith(MARK_END):
                skipping = False
            continue
        out.append(line)
    return out


def ensure_include() -> None:
    """Idempotently place the include block at the end of foot.ini.

    The block is always (re)written at the very end: foot honours the
    last-parsed value, so a block that ended up before Omarchy's themed
    include (user reordering, editor tooling) would silently lose.
    Multiple stale blocks are collapsed into one.

    - foot.ini missing: created containing just the block.
    - block present: relocated/replaced (picks up path changes).
    - block absent: appended at the end, preceded by one blank line.
    All other content is preserved byte-for-byte.  Before the first
    modification of an existing foot.ini, a one-time .bak copy is kept.
    """
    ini = paths.foot_config()
    original = _read_text(ini)
    block = include_block()

    if original is None:
        _atomic_write(ini, block)
        return

    lines = _strip_blocks(original.splitlines(keepends=True))
    text = "".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    new_text = text + "\n" + block

    if new_text != original:
        backup = ini.with_name(ini.name + ".bak")
        if not backup.exists():
            shutil.copy2(ini, backup)
        _atomic_write(ini, new_text)


def clear_palette_override() -> None:
    """Delete palette.ini and strip every marker block from foot.ini."""
    try:
        paths.palette_ini().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass

    ini = paths.foot_config()
    original = _read_text(ini)
    if original is None or MARK_BEGIN not in original:
        return
    new_text = "".join(_strip_blocks(original.splitlines(keepends=True)))
    if new_text != original:
        _atomic_write(ini, new_text)


def push_override_live(p: Palette) -> int:
    """Persist the override and OSC-push it into running Foot terminals."""
    write_palette_override(p)
    return osc.push_to_running_foot(p)
