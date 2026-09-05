# Foot Theme Studio

A native GTK4/libadwaita app for authoring, previewing, and applying
terminal palettes to **Foot** on Omarchy.

Do not fork Foot. Do not rewrite a terminal emulator. This studio sits on
top of Omarchy’s existing palette pipeline:

- source of truth: `colors.toml`
- Foot render: `foot.ini` via `$OMARCHY_PATH/default/themed/foot.ini.tpl`
- live push into running Foot: `omarchy-theme-osc` / `omarchy-theme-set-foot`

## Goals

Give the user end-to-end aesthetic control of Foot:

1. Drop or open an image and extract a palette.
2. Click any extracted or assigned color and edit it with a color wheel.
3. Browse hundreds of preexisting palettes (iTerm2-color-schemes, base16,
   and local Omarchy themes).
4. Run a color test (16 / 256 / truecolor spectrum).
5. See a terminal color-block preview in the app.
6. Apply live to Foot, persist Foot-only, or save as an Omarchy user theme.

## Non-goals

- Patching Foot’s C sources or adding GUI code to Foot.
- Replacing Omarchy’s theme engine.
- Restyling Hyprland / the bar unless the user explicitly chooses
  **Full Omarchy theme**.
- AI inside the picker.
- Supporting Ghostty / Alacritty / Kitty as first-class targets in v1
  (the `colors.toml` save path will theme them as a side effect of a full
  Omarchy apply).

## Location

```
~/Projects/foot-theme-studio/
```

User-safe outputs only:

- `~/.config/foot/palette.ini` — Foot-only override
- `~/.config/omarchy/themes/<slug>/` — named user themes
- never `/usr/share/omarchy/`

## Apply modes

### Foot only (default)

1. Write `~/.config/foot/palette.ini` in Foot’s `[colors]` / `[colors-dark]`
   form (hex without `#`, matching Omarchy’s `foot.ini.tpl`).
2. Ensure `~/.config/foot/foot.ini` includes that file *after* the Omarchy
   theme include so the studio wins without destroying Omarchy refresh.
3. Push OSC sequences into running Foot PTYs (same mapping as
   `omarchy-theme-osc`: 10 fg, 11 bg, 12 cursor, 17 selection bg,
   19 selection fg, `]4;0–15` ANSI).
4. New Foot windows pick up `palette.ini` from config; running ones update
   via OSC.

Do not call `omarchy theme set` in this mode.

### Full Omarchy theme (opt-in)

1. Write `~/.config/omarchy/themes/<slug>/colors.toml` with the semantic
   keys Omarchy already understands (`mode`, `accent`, `selection`,
   `muted`, `background`, `foreground`, ANSI red…magenta, brights, etc.).
2. Magenta aliases purple, matching `omarchy-theme-color`.
3. Apply with `omarchy theme set <slug>` so templates regenerate Foot,
   Ghostty, Hyprland, etc.

## Palette model

Internal working palette (hex `#rrggbb`):

| Role | Foot | OSC | colors.toml |
| --- | --- | --- | --- |
| background | background, regular0 | 11 | background |
| foreground | foreground, regular7 | 10 | foreground |
| cursor | cursor (bg + fg pair) | 12 | bright_foreground (cursor fg) |
| selection bg | selection-background | 17 | selection |
| selection fg | selection-foreground | 19 | selection_foreground or bright_foreground |
| regular 0–7 | regular0–7 | 4;0–7 | bg, red, green, yellow, blue, magenta/purple, cyan, fg |
| bright 0–7 | bright0–7 | 4;8–15 | muted, bright_red…bright_magenta, bright_cyan, bright_foreground |

Derived Omarchy keys when saving a full theme (do not require extra
swatches in v1): `dark_background`, `darker_background`,
`lighter_background`, `dark_foreground`, `light_foreground`, `orange`,
`brown`, `accent` — mix from bg/fg/yellow/red as `omarchy-theme-color`
does.

## UI (v1)

GTK4 + libadwaita, Python 3, `python-gobject`. No extra GUI toolkit.

Layout:

- **Left — Library.** Searchable list: bundled community palettes +
  Omarchy themes from `/usr/share/omarchy/themes` and
  `~/.config/omarchy/themes`. Click loads into the working palette.
- **Center — Swatches.** Color-block grid for bg, fg, cursor, selection,
  regular 0–7, bright 0–7. Each block shows the hex. Click opens
  `Gtk.ColorDialog` (color wheel). Edits update preview immediately.
- **Right / bottom — Preview.** Fake terminal chrome drawing the 16-color
  blocks, a sample prompt, and ls-style file colors on the working
  palette.
- **Image well.** Drop or file-chooser an image. Quantize to ~16 colors
  (GdkPixbuf sample; k-means or median-cut in-process; Pillow optional).
  Map by luminance (darkest → bg, lightest → fg) and hue (reddest → red,
  etc.). User can then click any slot and reassign.
- **Toolbar.** Open image, load library theme, revert, Foot-only apply,
  save as Omarchy theme, run color test.

## Color test

Two surfaces:

1. In-app spectrum: 16 ANSI blocks, 6×6×6 cube, grayscale ramp,
   truecolor gradient — painted with the working palette where 0–15
   apply, and with raw 256/truecolor for the rest.
2. In Foot: spawn `xdg-terminal-exec` / Foot running a small script that
   prints the same tests, so the user sees the real emulator.

## Theme library

v1 vendors a JSON snapshot of community palettes (iTerm2-color-schemes
and/or base16), converted to the internal palette model. Also scan local
Omarchy `colors.toml` files. Hundreds of entries, client-side search,
no network required at runtime.

Do not execute theme repo scripts. Data only.

## File formats

**Foot palette.ini** (studio-owned override):

```ini
[colors]
foreground=cdd6f4
background=1e1e2e
selection-foreground=cdd6f4
selection-background=45475a
cursor=1e1e2e cdd6f4
regular0=1e1e2e
regular1=f38ba8
; … regular2–7, bright0–7
```

**Omarchy colors.toml** when saving a named theme: same keys as
`/usr/share/omarchy/themes/catppuccin/colors.toml`.

## Stack

- Python 3
- GTK 4 + libadwaita (`gi`)
- GdkPixbuf for images
- Optional: `python-pillow` if quantization quality needs it
- Shell out only to `omarchy-theme-set` (full apply) and Foot/OSC (live)

## v1 acceptance

- Open the app on this Omarchy box.
- Drop an image → 16 roles fill → click a swatch → color wheel changes it.
- Search the library, load a named palette, see blocks + fake terminal
  update.
- Run color test in-app and in Foot.
- **Apply to Foot** changes the running Foot via OSC and survives new
  Foot windows via `palette.ini`.
- **Save as Omarchy theme** writes a user theme under
  `~/.config/omarchy/themes/` and can be selected with `omarchy theme set`.
- Omarchy `theme set` of a *different* stock theme does not crash; Foot-only
  override remains until the user clears it.

## Later (not v1)

- Per-terminal **live apply** beyond Foot (OSC/reload per emulator)
- Wallpaper set from the source image
- Contrast / WCAG warnings
- Import (round-trip) of foreign theme files
- Plugin or `omarchy` CLI subcommand

## Export to any terminal (v1.1 spec)

The working palette is terminal-agnostic (21 roles ≙ ANSI 0–15 + five
semantic roles).  Every terminal theme format is therefore a pure text
render over the same `Palette`.  Export is file-based: the studio
**renders and saves a file wherever the user chooses**; pointing a
terminal at it stays the user's call.  The studio never writes into
another tool's config or into Omarchy-managed state
(`~/.local/state/omarchy/…` would be clobbered by the next
`omarchy theme set`).

### Module `fts/exporters.py`

Pure functions `render(palette, title) -> str` (trailing newline,
deterministic, no I/O, no `gi` import) plus an ordered registry:

| id | file | shape (source of truth) |
| --- | --- | --- |
| `foot` | `<name>.ini` | `[colors-dark]`, hex WITHOUT `#`, key set of Omarchy's `foot.ini.tpl` |
| `alacritty` | `<name>.toml` | `[colors.primary]`, `[colors.cursor]` + `[colors.vi_mode_cursor]` (text = background), `[colors.selection]`, `[colors.normal]`, `[colors.bright]` — same shape Omarchy generates |
| `ghostty` | `<name>.conf` | `background`, `foreground`, `cursor-color`, `selection-background/-foreground`, `palette = 0…15` — same shape Omarchy generates |
| `kitty` | `<name>.conf` | `foreground`, `background`, `cursor`, `cursor_text_color` (= background), `selection_foreground/background`, `color0…15` |
| `wezterm` | `<name>.lua` | WezTerm color-scheme table (`foreground`, `background`, `cursor_bg/fg/border`, `selection_fg/bg`, `ansi[8]`, `brights[8]`), `return`ed so it can be `require`d or pasted into `config.color_schemes` |
| `json` | `<name>.json` | all 21 roles flat, plus `"name"` |

Role mapping (matches the Omarchy pipeline everywhere): cursor block =
`cursor`, cursor text = `background`; selection = `selection_bg` /
`selection_fg`; ANSI = `regular0–7`, `bright0–7`.  Hex conventions per
format: foot bare, all others `#rrggbb`.

### UI `ExportDialog` (`fts/ui/dialogs.py`)

- Checkable `Adw.ActionRow` per format (foot preselected), label +
  suggested filename.
- **Export…** (suggested-action) → `Gtk.FileDialog.save` with suggested
  basename `<slug>.<ext>`; write only to the chosen path; toast on
  success, `Adw.AlertDialog` on failure; cancelled dialog = no-op.
- Header button **Export…** in `FtsWindow`, packed next to
  "Save as Omarchy Theme…".

### Distribution as an Omarchy shell plugin

Omarchy's OS packages are curated; third-party apps ship as **shell
plugins** installed from git.  The repo root doubles as a plugin folder
(passes `omarchy plugin validate`):

- `manifest.json` — schemaVersion 1, id `scrimwiggins.foot-theme-studio`,
  `kinds: ["bar-widget"]`, `entryPoints.barWidget: "BarWidget.qml"`,
  `barWidget.defaultSection: "right"`.
- `BarWidget.qml` — one `WidgetButton` (Nerd Font paint-brush glyph) that
  `Quickshell.execDetached`es `<sourceDir>/bin/foot-theme-studio`,
  resolving the directory from the registry-injected
  `manifest.__sourceDir` (PATH fallback).
- Install: `omarchy plugin add <repo-url>` then
  `omarchy plugin enable scrimwiggins.foot-theme-studio right`.
