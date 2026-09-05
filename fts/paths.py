"""Path indirection for Foot Theme Studio.

All user-visible locations funnel through here so tests can redirect the
world with ``FOOT_THEME_STUDIO_HOME`` (and ``OMARCHY_PATH`` for the system
theme directory).
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "home",
    "foot_config",
    "palette_ini",
    "omarchy_user_themes",
    "omarchy_system_themes",
    "current_theme_colors",
]


def home() -> Path:
    """The user's home directory.

    ``Path(env FOOT_THEME_STUDIO_HOME)`` when that env var is set (used by
    tests and sandboxed runs), else :func:`pathlib.Path.home`.
    """
    override = os.environ.get("FOOT_THEME_STUDIO_HOME")
    if override:
        return Path(override)
    return Path.home()


def foot_config() -> Path:
    """~/.config/foot/foot.ini"""
    return home() / ".config" / "foot" / "foot.ini"


def palette_ini() -> Path:
    """~/.config/foot/palette.ini (studio-owned Foot-only override)."""
    return home() / ".config" / "foot" / "palette.ini"


def omarchy_user_themes() -> Path:
    """~/.config/omarchy/themes"""
    return home() / ".config" / "omarchy" / "themes"


def omarchy_system_themes() -> Path:
    """/usr/share/omarchy/themes ($OMARCHY_PATH/themes when set)."""
    base = os.environ.get("OMARCHY_PATH") or "/usr/share/omarchy"
    return Path(base) / "themes"


def current_theme_colors() -> Path:
    """~/.local/state/omarchy/current/theme/colors.toml"""
    return home() / ".local" / "state" / "omarchy" / "current" / "theme" / "colors.toml"
