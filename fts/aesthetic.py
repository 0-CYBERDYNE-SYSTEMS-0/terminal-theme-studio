"""Aesthetic derivation and wallpaper prompt building.

Pure color math only (no gi, no network).  :func:`derive_aesthetic`
summarizes a palette as a short aesthetic phrase for the wallpaper
generator when the user does not supply their own words;
:func:`build_prompt` composes the full text prompt that both image
providers receive.
"""

from __future__ import annotations

import colorsys
import math

from .palette import Palette, ROLE_LABELS, hex_to_rgba, is_dark

__all__ = ["derive_aesthetic", "build_prompt", "negative_prompt", "accent_swatches"]

_ASPECT_ROLES = tuple(
    [f"regular{i}" for i in range(1, 7)] + [f"bright{i}" for i in range(1, 7)]
)


# --------------------------------------------------------------------------
# palette statistics
# --------------------------------------------------------------------------

def _hsv(hexcolor: str) -> tuple[float, float, float]:
    """Hex color to colorsys HSV (h, s, v all 0..1)."""
    r, g, b = hex_to_rgba(hexcolor)[:3]
    return colorsys.rgb_to_hsv(r, g, b)


def _stats(palette: Palette) -> tuple[float, float, float]:
    """(circular mean hue in radians, mean saturation, hue resultant length).

    The resultant length R is 1 when every accent hue agrees (a narrow,
    single-hue look) and drops toward 0 as the hues spread around the
    wheel; saturation noise in near-gray palettes is ignored by the
    callers via the saturation bucketing.  A low resultant means wide
    hue spread.
    """
    hues: list[float] = []
    sats: list[float] = []
    for role in _ASPECT_ROLES:
        h, s, _v = _hsv(getattr(palette, role))
        hues.append(h * 2.0 * math.pi)
        sats.append(s)
    x = sum(math.cos(h) for h in hues) / len(hues)
    y = sum(math.sin(h) for h in hues) / len(hues)
    mean_hue = math.atan2(y, x) % (2.0 * math.pi)
    resultant = math.hypot(x, y)
    return mean_hue, sum(sats) / len(sats), resultant


# --------------------------------------------------------------------------
# aesthetic phrase
# --------------------------------------------------------------------------

def derive_aesthetic(palette: Palette) -> str:
    """Summarize a palette as a short aesthetic phrase.

    Deterministic buckets on background luminance, mean accent
    saturation, and hue spread -- the same axes a human glances at when
    naming a theme's vibe.  Used when the aesthetic field is blank.
    """
    dark = is_dark(palette.background)
    mean_hue, sat, resultant = _stats(palette)

    if sat <= 0.22:
        phrase = "dark moody monochrome" if dark else "clean minimal daylight"
    elif sat >= 0.5:
        if resultant <= 0.55:  # hues spread widely around the wheel
            phrase = (
                "vibrant neon nightscape" if dark else "vivid playful pop-art"
            )
        else:  # clustered around a single hue
            phrase = (
                "rich saturated neon dusk" if dark else "bold saturated pop"
            )
    else:
        if resultant <= 0.55:  # wide
            phrase = (
                "colorful midnight aurora" if dark else "gentle pastel daydream"
            )
        else:  # narrow
            phrase = (
                "deep atmospheric twilight" if dark else "soft hazy morning"
            )

    if sat > 0.3:
        degrees = mean_hue * 180.0 / math.pi
        if degrees <= 60.0 or degrees >= 300.0:
            return f"{phrase}, warm tones"
        if 130.0 <= degrees <= 260.0:
            return f"{phrase}, cool tones"
    return phrase


# --------------------------------------------------------------------------
# prompt building
# --------------------------------------------------------------------------

def accent_swatches(palette: Palette, n: int = 4) -> list[tuple[str, str]]:
    """The n most vivid, hue-distinct accent colors as (name, hex).

    Considers the twelve chromatic ANSI roles (regular1-6 / bright1-6),
    ranks them by saturation × brightness, and skips near-duplicate hues
    so the prompt describes genuinely different colors.
    """
    candidates: list[tuple[float, float, str, str]] = []  # (weight, hue, role, hex)
    for role in _ASPECT_ROLES:
        hexcolor = getattr(palette, role)
        h, s, v = _hsv(hexcolor)
        candidates.append((s * v, h * 360.0, role, hexcolor))
    candidates.sort(key=lambda item: (-item[0], item[2]))

    picked: list[tuple[float, str, str]] = []  # (hue, name, hex)
    for weight, hue, role, hexcolor in candidates:
        if weight <= 0.05:
            continue
        if any(min(abs(hue - h), 360.0 - abs(hue - h)) < 25.0 for h, _n, _x in picked):
            continue
        picked.append((hue, ROLE_LABELS[role], hexcolor))
        if len(picked) >= n:
            break
    return [(name, hexcolor) for _hue, name, hexcolor in picked]


def build_prompt(aesthetic: str, palette: Palette, aspect: str = "16:9") -> str:
    """Build the wallpaper generation prompt for the aesthetic + palette.

    One flowing paragraph: the requested aesthetic, the strict palette
    (with hex swatches), composition guidance that keeps the middle of
    the frame calm for terminal windows, and a baked-in negative (the
    Gemini API has no separate negative field; ComfyUI receives
    :func:`negative_prompt` as well).
    """
    tone = "dark" if is_dark(palette.background) else "light"
    accents = accent_swatches(palette)
    accent_text = ", ".join(f"{name.lower()} {hexcolor}" for name, hexcolor in accents)

    parts = [
        f"A {aspect} desktop wallpaper, {aesthetic}. {tone.capitalize()} overall tone.",
        (
            f"Strict color palette: background {palette.background}, "
            f"foreground {palette.foreground}"
            + (f", accents: {accent_text}" if accent_text else "")
            + ". Every element uses only these colors and lighter or darker "
            "tints and shades of them."
        ),
        (
            "Minimal abstract composition: smooth gradient field, soft glowing "
            "shapes, subtle film grain, calm and uncluttered, with the visual "
            "interest toward the edges so the center stays quiet for terminal "
            "windows."
        ),
        (
            "No text, no letters, no words, no numbers, no watermark, no logo, "
            "no signature, no border, no UI elements."
        ),
    ]
    return " ".join(parts)


def negative_prompt() -> str:
    """The ComfyUI negative prompt (Gemini bakes negatives into its prompt)."""
    return (
        "text, watermark, signature, logo, letters, words, numbers, ui elements, "
        "frame, border, jpeg artifacts, blurry, lowres, oversaturated, noise"
    )
