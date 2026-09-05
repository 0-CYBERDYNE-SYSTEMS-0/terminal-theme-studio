"""Color test generators: in-app text and a self-contained shell script.

Both render the same battery: the 16 ANSI slots (as truecolor blocks taken
from the working palette), the 6x6x6 cube, the 232-255 grayscale ramp, and
a truecolor gradient.  Output is plain text with ANSI SGR escapes.
"""

from __future__ import annotations

from .palette import Palette

__all__ = ["full_test_text", "script_text"]

_ANSI_NAMES = (
    "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
)


def _rgb(hexcolor: str) -> tuple[int, int, int]:
    s = hexcolor.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _bg(rgb: tuple[int, int, int], text: str = "  g0  ") -> str:
    r, g, b = rgb
    return f"\x1b[48;2;{r};{g};{b}m{text}\x1b[0m"


def _cube_rgb(i: int) -> tuple[int, int, int]:
    """Truecolor value of 256-color cube cell 16..231."""
    v = i - 16
    r, g, b = v // 36, (v // 6) % 6, v % 6
    conv = lambda x: 0 if x == 0 else 55 + 40 * x
    return (conv(r), conv(g), conv(b))


def _gray_rgb(i: int) -> tuple[int, int, int]:
    """Truecolor value of 256-color grayscale cell 232..255."""
    v = 8 + 10 * (i - 232)
    return (v, v, v)


def _ansi_palette(p: Palette) -> list[tuple[int, int, int]]:
    roles = [f"regular{i}" for i in range(8)] + [f"bright{i}" for i in range(8)]
    return [_rgb(getattr(p, role)) for role in roles]


def full_test_text(p: Palette) -> str:
    """The whole battery as plain text with escapes (for in-app preview)."""
    lines: list[str] = []
    lines.append("Terminal Theme Studio color test")
    lines.append(f"background {p.background}  foreground {p.foreground}")
    lines.append("")

    lines.append("== 16 ANSI colors (truecolor from the working palette) ==")
    ansi = _ansi_palette(p)
    for i, rgb in enumerate(ansi):
        name = _ANSI_NAMES[i % 8] + ("/bright" if i >= 8 else "")
        hexlabel = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        lines.append(f"[{i:>2}] {name:<14} {hexlabel}  {_bg(rgb)}  {_bg(_rgb(p.foreground), '  fg  ')}")
    lines.append("")

    lines.append("== 6x6x6 color cube (cells 16-231) ==")
    for r in range(6):
        row = []
        for g in range(6):
            for b in range(6):
                row.append(_bg(_cube_rgb(16 + 36 * r + 6 * g + b)))
        lines.append(f"r={r} |" + "".join(row) + "|")
    lines.append("")

    lines.append("== grayscale ramp (cells 232-255) ==")
    for start in range(232, 256, 12):
        row = [_bg(_gray_rgb(i)) for i in range(start, min(start + 12, 256))]
        lines.append(f"{start:>3} |" + "".join(row) + "|")
    lines.append("")

    lines.append("== truecolor gradient (background -> accent -> foreground) ==")
    accent = _rgb(p.regular4)
    start_rgb = _rgb(p.background)
    end_rgb = _rgb(p.foreground)
    steps = 24
    row = []
    for i in range(steps):
        t1 = i / (steps - 1)
        if t1 < 0.5:
            t = t1 / 0.5
            rgb = tuple(
                int(round(a * (1 - t) + b * t)) for a, b in zip(start_rgb, accent)
            )
        else:
            t = (t1 - 0.5) / 0.5
            rgb = tuple(
                int(round(a * (1 - t) + b * t)) for a, b in zip(accent, end_rgb)
            )
        row.append(_bg(rgb))
    lines.append("".join(row))
    lines.append("")
    return "\n".join(lines)


def script_text(p: Palette) -> str:
    """Self-contained POSIX sh script printing the same tests.

    No dependencies beyond /bin/sh and printf; safe to pipe into any
    terminal (e.g. the Foot instance under test).
    """
    ansi = _ansi_palette(p)

    def sh_rgb(rgb: tuple[int, int, int]) -> str:
        return f"{rgb[0]} {rgb[1]} {rgb[2]}"

    out: list[str] = []
    out.append("#!/bin/sh")
    out.append("# Terminal Theme Studio color test -- generated, POSIX sh, no deps.")
    out.append("# 16 ANSI slots are printed with truecolor values from the")
    out.append(f"# working palette (background {p.background}, foreground {p.foreground}).")
    out.append("")
    out.append("bg() { printf '\\033[48;2;%s;%s;%sm%s\\033[0m' \"$1\" \"$2\" \"$3\" \"$4\"; }")
    out.append("")
    out.append("echo '== 16 ANSI colors =='")
    for i, rgb in enumerate(ansi):
        name = _ANSI_NAMES[i % 8] + ("-bright" if i >= 8 else "")
        r, g, b = rgb
        out.append(f'printf "[{i:>2}] {_ANSI_NAMES[i % 8]:<7} "')
        out.append(f"bg {r} {g} {b} ' {name} '")
        out.append("printf '\\n'")
    out.append("")
    out.append("echo '== 6x6x6 color cube (16-231) =='")
    out.append("r=0")
    out.append("while [ \"$r\" -lt 6 ]; do")
    out.append("  printf 'r=%s |' \"$r\"")
    out.append("  g=0")
    out.append("  while [ \"$g\" -lt 6 ]; do")
    out.append("    b=0")
    out.append("    while [ \"$b\" -lt 6 ]; do")
    out.append("      n=$((16 + 36 * r + 6 * g + b))")
    out.append("      v=$((n - 16))")
    out.append("      cr=$((v / 36)); cg=$(( (v / 6) % 6 )); cb=$((v % 6))")
    out.append("      conv() { [ \"$1\" -eq 0 ] && echo 0 || echo $((55 + 40 * $1)); }")
    out.append("      rr=$(conv \"$cr\"); gg=$(conv \"$cg\"); bb=$(conv \"$cb\")")
    out.append("      bg \"$rr\" \"$gg\" \"$bb\" '  '")
    out.append("      b=$((b + 1))")
    out.append("    done")
    out.append("    g=$((g + 1))")
    out.append("  done")
    out.append("  printf '|\\n'")
    out.append("  r=$((r + 1))")
    out.append("done")
    out.append("")
    out.append("echo '== grayscale ramp (232-255) =='")
    out.append("i=232")
    out.append("while [ \"$i\" -lt 256 ]; do")
    out.append("  v=$((8 + 10 * (i - 232)))")
    out.append("  bg \"$v\" \"$v\" \"$v\" '  '")
    out.append("  i=$((i + 1))")
    out.append("done")
    out.append("printf '\\n'")
    out.append("")
    out.append("echo '== truecolor gradient =='")
    out.append(f"sr={_rgb(p.background)[0]}; sg={_rgb(p.background)[1]}; sb={_rgb(p.background)[2]}")
    out.append(f"er={_rgb(p.foreground)[0]}; eg={_rgb(p.foreground)[1]}; eb={_rgb(p.foreground)[2]}")
    out.append("n=0")
    out.append("while [ \"$n\" -lt 24 ]; do")
    out.append("  t=$((n * 100 / 23))")
    out.append("  rr=$(( (sr * (100 - t) + er * t) / 100 ))")
    out.append("  gg=$(( (sg * (100 - t) + eg * t) / 100 ))")
    out.append("  bb=$(( (sb * (100 - t) + eb * t) / 100 ))")
    out.append("  bg \"$rr\" \"$gg\" \"$bb\" '  '")
    out.append("  n=$((n + 1))")
    out.append("done")
    out.append("printf '\\n'")
    out.append("")
    return "\n".join(out) + "\n"
