"""OSC 4/10/11/12/17/19 sequence building and live push into Foot.

``push_to_running_foot`` replicates ``omarchy-theme-set-foot`` in pure
Python: find processes named ``foot`` by scanning /proc, walk to their
direct children (the shells inside foot's PTYs), resolve each child's
stdout, and write the OSC bytes to any /dev/pts/* terminal found.
"""

from __future__ import annotations

import os
import re
import subprocess
import warnings

from .palette import Palette, ansi_index

__all__ = ["osc_bytes", "push_to_running_foot"]


def osc_bytes(p: Palette) -> bytes:
    """BEL-terminated OSC sequences for the palette (hex WITH '#').

    10 foreground, 11 background, 12 cursor, 17 selection bg,
    19 selection fg, then ]4;0..15 for the 16 ANSI slots -- the same
    mapping omarchy-theme-osc emits.
    """
    out = bytearray()

    def emit(code: str, value: str) -> None:
        out.extend(f"\x1b]{code};{value}\x07".encode("ascii"))

    emit("10", p.foreground)
    emit("11", p.background)
    emit("12", p.cursor)
    emit("17", p.selection_bg)
    emit("19", p.selection_fg)

    roles = [f"regular{i}" for i in range(8)] + [f"bright{i}" for i in range(8)]
    for role in roles:
        emit(f"4;{ansi_index(role)}", getattr(p, role))

    return bytes(out)


# --------------------------------------------------------------------------
# process discovery (pure /proc, pgrep fallback)
# --------------------------------------------------------------------------

_NUMERIC = re.compile(r"^[0-9]+$")


def _comm(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/comm", "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _foot_pids_proc() -> list[int]:
    pids = []
    for entry in os.listdir("/proc"):
        if not _NUMERIC.match(entry):
            continue
        if _comm(int(entry)) == "foot":
            pids.append(int(entry))
    return pids


def _children_proc(parent: int) -> list[int]:
    children = []
    for entry in os.listdir("/proc"):
        if not _NUMERIC.match(entry):
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                stat = fh.read()
        except OSError:
            continue
        # comm (field 2) may contain spaces/parens: parse after the last ')'
        close = stat.rfind(b")")
        if close == -1:
            continue
        fields_after = stat[close + 2 :].split()
        # fields_after[0] is state (field 3); ppid is field 4
        if len(fields_after) < 2:
            continue
        try:
            ppid = int(fields_after[1])
        except ValueError:
            continue
        if ppid == parent:
            children.append(pid)
    return children


def _foot_pids_pgrep() -> list[int]:
    try:
        out = subprocess.run(
            ["pgrep", "-x", "foot"], capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    return [int(line) for line in out.stdout.split() if line.strip().isdigit()]


def _children_pgrep(parent: int) -> list[int]:
    try:
        out = subprocess.run(
            ["pgrep", "-P", str(parent)], capture_output=True, text=True, check=False
        )
    except OSError:
        return []
    return [int(line) for line in out.stdout.split() if line.strip().isdigit()]


def push_to_running_foot(p: Palette) -> int:
    """Push the palette OSC into every PTY of running Foot instances.

    Returns the number of ptys successfully written.  Individual failures
    are reported via :mod:`warnings` and never raised.
    """
    payload = osc_bytes(p)
    try:
        foot_pids = _foot_pids_proc()
        find_children = _children_proc
        if not foot_pids:  # cheap cross-check before falling back
            foot_pids = _foot_pids_pgrep()
            find_children = _children_pgrep
    except Exception as exc:  # /proc unavailable -> pgrep fallback
        warnings.warn(f"terminal-theme-studio: /proc scan failed ({exc}); using pgrep")
        foot_pids = _foot_pids_pgrep()
        find_children = _children_pgrep

    written = 0
    for foot_pid in foot_pids:
        try:
            children = find_children(foot_pid)
        except Exception as exc:
            warnings.warn(f"terminal-theme-studio: cannot list children of {foot_pid}: {exc}")
            continue
        for child in children:
            try:
                tty = os.readlink(f"/proc/{child}/fd/1")
            except OSError as exc:
                warnings.warn(f"terminal-theme-studio: cannot read fd/1 of {child}: {exc}")
                continue
            if not tty.startswith("/dev/pts/"):
                continue
            try:
                fd = os.open(tty, os.O_WRONLY)
                try:
                    os.write(fd, payload)
                finally:
                    os.close(fd)
                written += 1
            except OSError as exc:
                warnings.warn(f"terminal-theme-studio: cannot write to {tty}: {exc}")
    return written
