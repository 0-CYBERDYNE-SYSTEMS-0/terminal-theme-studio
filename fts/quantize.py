"""Palette extraction from images: median-cut + role mapping.

``median_cut`` is pure Python (testable without GTK).  Only
``extract_palette`` touches a GdkPixbuf, duck-typed so importing this
module never requires gi.
"""

from __future__ import annotations

import colorsys

from .palette import Palette, is_dark, mix, relative_luminance, rgba_to_hex

__all__ = ["extract_palette", "median_cut", "palette_from_colors"]

_MAX_SAMPLES = 60_000


# --------------------------------------------------------------------------
# median cut
# --------------------------------------------------------------------------

def _bounds(items: list[tuple[tuple[int, int, int], int]]) -> tuple[int, int]:
    """(widest channel index, range) over the unique colors of a bucket."""
    ranges = []
    for ch in range(3):
        values = [rgb[ch] for rgb, _ in items]
        ranges.append(max(values) - min(values))
    widest = max(range(3), key=lambda i: (ranges[i], -i))
    return widest, ranges[widest]


def _bucket_mean(items: list[tuple[tuple[int, int, int], int]]) -> tuple[int, int, int]:
    """Pixel-count-weighted mean of a bucket, rounded like omarchy."""
    total = sum(c for _, c in items)
    if total == 0:
        total = 1
    return tuple(
        int(sum(rgb[ch] * c for rgb, c in items) / total + 0.5) for ch in range(3)
    )


def _split_bucket(items: list[tuple[tuple[int, int, int], int]], ch: int):
    """Split a bucket on channel ch at the pixel-count weighted median.

    The cut is adjusted to a value boundary so a run of equal channel
    values is never cut in half (which would leave the same color on both
    sides and eventually merge distinct regions).
    """
    items.sort(key=lambda item: item[0][ch])
    total = sum(c for _, c in items)
    acc = 0
    mid = len(items) // 2
    for i, (_rgb, c) in enumerate(items):
        acc += c
        if acc * 2 >= total:
            mid = i + 1
            break

    # never cut inside a run of equal channel values: advance to the end
    # of the run, or retreat to its start when the run reaches the tail
    while mid < len(items) and items[mid][0][ch] == items[mid - 1][0][ch]:
        mid += 1
    if mid == len(items):
        mid -= 1
        while mid > 0 and items[mid][0][ch] == items[mid - 1][0][ch]:
            mid -= 1
    if mid == 0 or mid == len(items):
        return None  # cannot separate on this channel
    return items[:mid], items[mid:]


def median_cut(
    pixels: list[tuple[int, int, int]], k: int
) -> list[tuple[int, int, int]]:
    """Median-cut quantization of RGB samples into k cluster means.

    Duplicate samples are folded into per-color pixel counts, so the
    result is weighted by pixel count without letting scanline
    interleaving confuse the splits.  Buckets are split along their widest
    channel at the weighted median until k buckets exist or nothing is
    splittable.  Results are sorted dark -> light by relative luminance
    for determinism.
    """
    if k <= 0 or not pixels:
        return []

    counts: dict[tuple[int, int, int], int] = {}
    for px in pixels:
        counts[px] = counts.get(px, 0) + 1
    unique = list(counts.items())

    buckets: list[list[tuple[tuple[int, int, int], int]]] = [unique]
    while len(buckets) < k:
        # split the bucket with the widest channel range
        best_i, best_ch, best_range = -1, 0, 0
        for i, bucket in enumerate(buckets):
            if len(bucket) < 2:
                continue
            ch, rng = _bounds(bucket)
            if rng > best_range:
                best_i, best_ch, best_range = i, ch, rng
        if best_i < 0 or best_range == 0:
            break  # nothing splittable left (all buckets are single colors)
        halves = _split_bucket(buckets[best_i], best_ch)
        if halves is None:  # unreachable when best_range > 0; stay safe
            break
        left, right = halves
        buckets.pop(best_i)
        buckets.append(left)
        buckets.append(right)

    means = [_bucket_mean(b) for b in buckets if b]
    means.sort(key=lambda rgb: relative_luminance(rgba_to_hex(*_byte(rgb))))
    return means


def _byte(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


# --------------------------------------------------------------------------
# pixbuf extraction
# --------------------------------------------------------------------------

def extract_palette(pixbuf, k: int = 16) -> list[str]:
    """Extract k hex colors from a GdkPixbuf.Pixbuf via median cut.

    The pixbuf API is duck-typed (get_width/get_height/get_pixels/
    get_rowstride/get_n_channels), so no gi import is needed.  Large
    images are stride-sampled down to ~_MAX_SAMPLES pixels.
    """
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    n_channels = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    data = pixbuf.get_pixels()

    total = width * height
    step = max(1, int((total / _MAX_SAMPLES) ** 0.5))
    has_alpha = n_channels == 4

    pixels: list[tuple[int, int, int]] = []
    for y in range(0, height, step):
        row = y * rowstride
        for x in range(0, width, step):
            off = row + x * n_channels
            if has_alpha and data[off + 3] < 128:
                continue  # ignore transparent pixels
            pixels.append((data[off], data[off + 1], data[off + 2]))

    return [rgba_to_hex(*_byte(rgb)) for rgb in median_cut(pixels, k)]


# --------------------------------------------------------------------------
# extracted colors -> Palette
# --------------------------------------------------------------------------

def _hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = _byte(rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # hue 0..1, light, sat
    return (h * 360.0, s, l)


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def palette_from_colors(colors: list[str]) -> Palette:
    """Map extracted hex colors onto the 21 palette roles.

    - darkest -> background & regular0; lightest -> foreground,
      regular7, cursor.
    - red/yellow/green/cyan/blue/magenta (regular1/3/2/6/4/5) pick the
      unused color with the best saturation-weighted hue match.
    - any remaining regular slots are filled by luminance (dark->light).
    - brights: distinct leftover extracted colors first, else
      mix(regularN, #ffffff, 0.2); bright0 is a muted background mix;
      bright7 = lightest; selection_bg = mix(bg, fg, 0.25).
    """
    parsed = [rgba_to_hex(*_byte(rgb)) for rgb in _parse_all(colors)]
    if not parsed:
        return Palette.from_dict({})

    parsed.sort(key=relative_luminance)
    darkest, lightest = parsed[0], parsed[-1]
    pool = parsed[1:-1]  # unused intermediate colors, luminance order

    regulars: dict[int, str] = {}
    used: set[str] = set()

    def take(color: str) -> None:
        used.add(color)

    take(darkest)
    take(lightest)

    # hue-targeted accent slots
    hue_targets = (
        (1, 0.0),    # red
        (3, 60.0),   # yellow
        (2, 120.0),  # green
        (6, 180.0),  # cyan
        (4, 240.0),  # blue
        (5, 300.0),  # magenta
    )
    available = [c for c in pool if c not in used]
    scores = {c: _hsl(_to_rgb(c)) for c in available}
    for slot, hue in hue_targets:
        best, best_score = None, -1.0
        for color in available:
            if color in used:
                continue
            h, s, _l = scores[color]
            score = s * (1.0 - _hue_distance(h, hue) / 180.0)
            if score > best_score:
                best, best_score = color, score
        if best is not None:
            regulars[slot] = best
            take(best)

    # fill remaining regular slots by luminance order (dark -> light)
    for slot in range(1, 7):
        if slot in regulars:
            continue
        fill = None
        for color in pool:
            if color not in used:
                fill = color
                break
        if fill is None:
            fill = mix(darkest, lightest, slot / 7.0)
        regulars[slot] = fill
        take(fill)

    regular = [darkest] + [regulars[i] for i in range(1, 7)] + [lightest]

    # brights: prefer distinct unused extracted colors, then mixes
    bright: list[str] = []
    leftover = [c for c in pool if c not in used]
    for i in range(1, 7):
        if leftover:
            bright.append(leftover.pop(0))
        else:
            bright.append(mix(regular[i], "#ffffff", 0.2))

    muted = mix(darkest, "#ffffff", 0.35) if is_dark(darkest) else mix(
        darkest, "#000000", 0.35
    )

    return Palette(
        background=darkest,
        foreground=lightest,
        cursor=lightest,
        selection_bg=mix(darkest, lightest, 0.25),
        selection_fg=lightest,
        regular0=darkest,
        regular1=regular[1],
        regular2=regular[2],
        regular3=regular[3],
        regular4=regular[4],
        regular5=regular[5],
        regular6=regular[6],
        regular7=lightest,
        bright0=muted,
        bright1=bright[0],
        bright2=bright[1],
        bright3=bright[2],
        bright4=bright[3],
        bright5=bright[4],
        bright6=bright[5],
        bright7=lightest,
    )


def _parse_all(colors: list[str]) -> list[tuple[int, int, int]]:
    out = []
    for c in colors:
        s = str(c).strip().lstrip("#")
        if len(s) == 3:
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6:
            continue
        try:
            out.append((int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)))
        except ValueError:
            continue
    return out


def _to_rgb(hexcolor: str) -> tuple[int, int, int]:
    s = hexcolor.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
