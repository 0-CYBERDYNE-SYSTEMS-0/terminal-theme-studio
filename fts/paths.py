"""Path indirection for Terminal Theme Studio.

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
    "current_theme_name",
    "current_background_link",
    "user_backgrounds",
    "gemini_api_key",
    "mflux_url",
    "comfyui_url",
    "comfyui_checkpoint",
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


def current_theme_name() -> Path:
    """~/.local/state/omarchy/current/theme.name (written by omarchy-theme-set)."""
    return home() / ".local" / "state" / "omarchy" / "current" / "theme.name"


def current_background_link() -> Path:
    """~/.local/state/omarchy/current/background (symlink; omarchy-theme-bg-set)."""
    return home() / ".local" / "state" / "omarchy" / "current" / "background"


def user_backgrounds(slug: str) -> Path:
    """~/.config/omarchy/backgrounds/<slug> (per-theme user wallpapers).

    omarchy-theme-set merges this directory with the active theme's own
    backgrounds/ when it cycles wallpapers, so dropping generated images
    here makes them part of the current theme's rotation.
    """
    return home() / ".config" / "omarchy" / "backgrounds" / slug


# --------------------------------------------------------------------------
# image-generation endpoints (wallpaper studio)
# --------------------------------------------------------------------------

def gemini_api_key() -> str | None:
    """The Gemini API key (``GEMINI_API_KEY``, falling back to
    ``GOOGLE_API_KEY``); None when neither is set."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def mflux_url() -> str:
    """The mflux bridge endpoint (``FTS_MFLUX_URL``).

    The photoLiquidity bridge on the Mac mini M2 serving FLUX.2 Klein 4B
    (4-bit MLX) as a LaunchAgent; it binds 0.0.0.0 so every Tailnet peer
    can reach it.
    """
    return os.environ.get("FTS_MFLUX_URL") or "http://100.72.41.118:4030"


def comfyui_url() -> str:
    """The ComfyUI HTTP endpoint (``FTS_COMFYUI_URL``), the SDXL fallback
    backend.

    Separate service from the mflux bridge (never route Flux jobs here).
    Defaults to the Mac mini M2 on the tailnet, which runs ComfyUI bound
    to all interfaces (verified reachable over Tailscale).
    """
    return os.environ.get("FTS_COMFYUI_URL") or "http://100.72.41.118:8188"


def comfyui_checkpoint() -> str:
    """The ComfyUI checkpoint name (``FTS_COMFYUI_CHECKPOINT``).

    The M2 currently only carries ``sd_xl_base_1.0.safetensors``; pointing
    this at a Flux checkpoint once one is installed switches the local
    provider to Flux with no code change.
    """
    return os.environ.get("FTS_COMFYUI_CHECKPOINT") or "sd_xl_base_1.0.safetensors"
