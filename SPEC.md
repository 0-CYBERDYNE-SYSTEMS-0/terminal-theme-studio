# Terminal Theme Studio

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
~/Projects/terminal-theme-studio/
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
- ~~Wallpaper set from the source image~~ — shipped as **Wallpapers… (v1.2)**, below
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

- `manifest.json` — schemaVersion 1, id `scrimwiggins.terminal-theme-studio`,
  `kinds: ["bar-widget"]`, `entryPoints.barWidget: "BarWidget.qml"`,
  `barWidget.defaultSection: "right"`.
- `BarWidget.qml` — one `WidgetButton` (Nerd Font paint-brush glyph) that
  `Quickshell.execDetached`es `<sourceDir>/bin/terminal-theme-studio`,
  resolving the directory from the registry-injected
  `manifest.__sourceDir` (PATH fallback).
- Install: `omarchy plugin add <repo-url>` then
  `omarchy plugin enable scrimwiggins.terminal-theme-studio right`.

## AI wallpaper generation (v1.2 spec)

From any working palette — image-derived, library, or hand-edited — the
**Wallpapers…** header button opens a dialog that generates matching
desktop wallpapers.  An optional aesthetic field takes three or four
words; when blank the vibe is **derived from the palette**
(`fts.aesthetic.derive_aesthetic`: background luminance × mean accent
saturation × hue-spread buckets, e.g. "rich saturated neon dusk, warm
tones").  The prompt (`fts.aesthetic.build_prompt`) states the
aesthetic, the strict palette with hex swatches (background/foreground +
the four most vivid, hue-distinct accents), calm-center composition
guidance, and a baked-in negative.

### Providers (`fts/providers.py`)

All return `GeneratedImage(bytes, mime, provider, prompt, meta)`, share
the call shape `generate(prompt, *, aspect, count, reference)`, and take
an injected transport (stdlib `urllib` by default — no new
dependencies); all failures raise `ProviderError` with a
user-presentable message.  The UI builds its dropdown from
`providers.PROVIDERS` and instantiates via `providers.make_provider` —
contributing a provider is one class plus those two registrations.

- **`MfluxProvider`** (the default local provider) — the photoLiquidity
  mflux bridge on the Mac mini M2 (LaunchAgent
  `com.photoliquidity.mflux`, binds 0.0.0.0 for Tailnet reach):
  `POST /generate` with `{prompt, width, height, steps, seed}` returns
  base64 PNG in JSON (no file endpoint).  FLUX.2 Klein 4B is
  step-distilled (1–4 steps, 2 is the measured sweet spot, ~20–35 s
  warm) with no negative prompt and guidance pinned at 1.0; prompts
  cap around 512 tokens.  Dimensions per aspect hold the ~720² pixel
  budget snapped to multiples of 16 (16:9 → 960×544, 21:9 →
  1104×464 …).  The bridge is single-process, so batches serialize;
  its `/shutdown` route is shared infrastructure and is never called.
  Endpoint: `FTS_MFLUX_URL` (default `http://100.72.41.118:4030`).
- **`GeminiProvider`** — Gemini Interactions API
  (`POST https://generativelanguage.googleapis.com/v1beta/interactions`,
  `x-goog-api-key` header) with `gemini-3.1-flash-lite-image`
  ("Nano Banana 2 Lite"), `response_format` fixed at
  `{"type": "image", "aspect_ratio": …, "image_size": "1K"}` (~$0.034
  per image).  Reference images (the palette's source image) go inline
  as base64 `{"type": "image", …}` blocks; the image comes back base64
  in `interaction.output_image.data` (steps/`model_output` blocks as
  fallback).  Key: `GEMINI_API_KEY` or `GOOGLE_API_KEY`
  (`fts.paths.gemini_api_key`).
- **`ComfyUIProvider`** (SDXL fallback backend, separate service from
  the mflux bridge — never route Flux jobs there) — queues a minimal
  txt2img API-format graph (CheckpointLoaderSimple → CLIPTextEncode×2 →
  EmptyLatentImage → KSampler → VAEDecode → SaveImage) at
  `POST /prompt`, polls `GET /history/<id>` for outputs/errors,
  downloads bytes from `GET /view`.  Latent dims use SDXL's trained
  buckets per aspect (16:9 → 1344×768, 21:9 → 1536×640 …).
  `FTS_COMFYUI_URL` (default `http://100.72.41.118:8188`) and
  `FTS_COMFYUI_CHECKPOINT` (default `sd_xl_base_1.0.safetensors`).
- **`OpenAIImageProvider`** (bring your own endpoint) — any server
  speaking the standard `POST <base>/images/generations` with
  `{model, prompt, size, n}`; `b64_json` primary, `url` responses are
  fetched.  `FTS_OPENAI_IMAGE_URL` (+ `FTS_OPENAI_IMAGE_MODEL`,
  `FTS_OPENAI_IMAGE_SIZE`, `FTS_OPENAI_API_KEY`/`OPENAI_API_KEY`).
- **`CustomCommandProvider`** (bring your own anything) — runs
  `FTS_IMAGE_COMMAND` under `/bin/sh -c` with `{prompt}` (shell-quoted),
  `{width}`, `{height}` substituted; stdout is the image, sniffed via
  magic bytes.  The universal escape hatch: any CLI, API, or ssh
  one-liner becomes a provider.

### Omarchy integration (`fts/omarchy.py`)

The default flow creates a **complete theme**: `save_user_theme` writes
`~/.config/omarchy/themes/<slug>/colors.toml` first (so a mid-generation
failure still leaves a valid, appliable theme), then each generated
image lands as `<n>-<stem>.<ext>` in that theme's `backgrounds/` — the
same shape Omarchy's own themes ship.  Finishing runs
`omarchy-theme-set <slug>` (full desktop apply) and
`omarchy-theme-bg-set <first wallpaper>` (live background).  The studio
only ever writes its own user-theme directory and calls Omarchy's
public scripts — it never touches `~/.local/state/omarchy/` itself.

Opting out of theme creation saves to
`~/.config/omarchy/backgrounds/<slug>/` instead — the per-theme *user*
backgrounds folder that `omarchy-theme-set` merges into the theme's
wallpaper rotation.

### UI `WallpaperDialog` (`fts/ui/wallpaper_dialog.py`)

- Aesthetic `Adw.EntryRow` with a live "auto-detected" caption;
  provider/aspect `Adw.ComboRow`s; count `Adw.SpinRow` (1–4);
  "let the source image guide the look" switch (Gemini + source image
  only).
- Theme-creation controls: new-theme-name entry + **Create a full
  Omarchy theme** switch (default on, button relabels to
  "Create Theme") + **Apply it when done** switch.
- **Generate/Create Theme** runs the whole sequence on a worker thread
  (colors.toml → wallpapers → apply → set background), per-image and
  cancel-aware between images, marshalled back via `GLib.idle_add`;
  spinner + progress status; results as thumbnail cards with per-image
  **Set as Wallpaper**.  The created theme refreshes the library via
  the `on_theme_created` callback.  Failures → toast /
  `Adw.AlertDialog`, never raised into the main loop.
