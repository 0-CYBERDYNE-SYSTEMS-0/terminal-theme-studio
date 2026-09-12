# Terminal Theme Studio

A GTK4/libadwaita app for authoring, previewing, and applying terminal
palettes to [Foot](https://codeberg.org/dnkl/foot) on
[Omarchy](https://omarchy.org).

It sits on top of Omarchy's existing palette pipeline instead of replacing
it: `colors.toml` is the source of truth, Foot renders via
`$OMARCHY_PATH/default/themed/foot.ini.tpl`, and live updates go through
OSC 10/11/12/17/19 + `]4;0–15` — the same mapping `omarchy-theme-osc`
uses.

## Layout

```
fts/
  paths.py        path indirection (FOOT_THEME_STUDIO_HOME / OMARCHY_PATH aware)
  palette.py      21-role Palette model + color math (mix matches omarchy byte-for-byte)
  omarchy.py      colors.toml parse/resolve/write, user themes, omarchy-theme-set apply
  foot_config.py  ~/.config/foot/palette.ini + marker-guarded include block in foot.ini
  osc.py          OSC sequence building + live push into running Foot (pure /proc)
  library.py      vendored community palettes + local Omarchy themes, with search
  quantize.py     median-cut image extraction (weighted, pure python) + role mapping
  colortest.py    ANSI/256/truecolor test text + self-contained POSIX sh script
  exporters.py    pure Palette -> theme-file renderers (foot, alacritty, ghostty,
                  kitty, wezterm, json) for the Export… button
  aesthetic.py    palette vibe phrases + wallpaper prompt building (pure math)
  providers.py    pluggable wallpaper providers: mflux (FLUX.2 Klein), Gemini
                  "Nano Banana 2 Lite", ComfyUI SDXL, OpenAI-compatible
                  /v1/images, and a custom-command escape hatch — all
                  transport-injected, stdlib-only
  main.py         Adw.Application entry point (com.omarchy.TerminalThemeStudio)
  ui/             GTK4/libadwaita UI (window, library, swatches, image well,
                  terminal preview, color test view + dialogs)
data/
  palettes.json   1229 vendored community palettes (from Gogh's themes.json; data only)
tests/            stdlib unittest suite
bin/
  terminal-theme-studio  executable launcher shim
```

## Run

```sh
python3 -m unittest discover -s tests   # 169 tests, no display needed
bin/terminal-theme-studio                   # GTK UI (or: python3 -m fts.main)
```

Requires Python 3.14 with PyGObject (GTK 4 + Adw + GdkPixbuf) at UI time;
the core modules above import without `gi`/display.

## How applying works

- **Foot only (default):** regenerate `~/.config/foot/palette.ini`
  (hex without `#`, `[colors-dark]`, same keys as Omarchy's tpl), ensure a
  `# >>> terminal-theme-studio >>>` guarded `[main] include=` block sits at the
  end of `foot.ini` (later parse wins; Omarchy refresh keeps working), then
  OSC-push into every PTY of running Foot processes. `omarchy theme set`
  is never called.
- **Full Omarchy theme (opt-in):** write
  `~/.config/omarchy/themes/<slug>/colors.toml` with the full semantic key
  set (mode, accent, selection, muted, purple/bright_purple aliases,
  derived dark/darker/lighter backgrounds, orange, brown …) and run
  `omarchy-theme-set <slug>`.
- **Export… (any terminal):** render the working palette to a theme file
  and save it wherever you choose — `foot.ini`, `alacritty.toml`,
  `ghostty.conf`, `kitty.conf`, a WezTerm colorscheme `.lua`, or a raw
  `.json` of all 21 roles. File-based only: nothing is ever written into
  another tool's config or Omarchy-managed state. Every format is the
  same 21-role palette in that terminal's shape (cursor text =
  background, ANSI = regular0–7/bright0–7), so exported files match what
  Omarchy itself generates. See SPEC.md for the full mapping.

## Wallpapers… → one-click Omarchy theme creation

The **Wallpapers…** button is the end-to-end flow: give it three or four
aesthetic words (or leave blank — the palette's vibe is derived
automatically), pick a provider, and hit **Create Theme**. That writes a
complete Omarchy theme and switches the whole desktop to it:

1. `~/.config/omarchy/themes/<name>/colors.toml` — the working palette
   (from an image, a library theme, or hand-edited) in the full semantic
   key set.
2. `~/.config/omarchy/themes/<name>/backgrounds/1-…png` — the generated
   wallpapers, shipped with the theme like Omarchy's own themes do.
3. `omarchy-theme-set <name>` — the theme applies everywhere (Foot,
   Ghostty, Alacritty, Hyprland, waybar, lock screen…).
4. `omarchy-theme-bg-set <first wallpaper>` — the generated image becomes
   the live desktop background.

Turn off **Create a full Omarchy theme** for the lighter mode: wallpapers
are only saved to `~/.config/omarchy/backgrounds/<theme>/`, joining the
current theme's wallpaper rotation without touching any theme.

Three built-in endpoints plus two bring-your-own routes, no new
dependencies (stdlib `urllib` only). Pick in the provider dropdown;
every route is also a subclass away for contributors (see
CONTRIBUTING.md):

- **Flux — Mac mini M2 (default, local)**: the photoLiquidity mflux
  bridge (LaunchAgent `com.photoliquidity.mflux`) serving FLUX.2 Klein
  4B in 4-bit MLX.  Step-distilled — 2 steps at ~720²-pixel budgets,
  about 20–35 s warm per wallpaper.  Free, no key.  Klein has no
  negative prompt; requests serialize (single-process bridge).
- **Gemini — Nano Banana 2 Lite** (`gemini-3.1-flash-lite-image`,
  ~$0.034 per 1K image).  Needs an API key: create one at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and
  persist it, e.g.
  `printf 'GEMINI_API_KEY=…\n' > ~/.config/environment.d/90-gemini.conf`
  (then log out and back in).  Optionally passes the source image along
  as a style reference.
- **ComfyUI — SDXL fallback** (separate backend; Flux jobs are never
  routed here): queues a minimal txt2img graph and polls until done —
  free, but about a minute per image.
- **OpenAI-compatible — /v1/images**: any server speaking the standard
  `POST <base>/images/generations` — LocalAI, SwarmUI, a gateway, or
  api.openai.com itself.
- **Custom command — anything**: if a route exists, a one-liner can use
  it (see below).

### Bring your own image route

Two env vars cover everything the built-ins don't:

| variable | meaning |
|---|---|
| `FTS_IMAGE_COMMAND` | Any shell command with `{prompt}`, `{width}`, `{height}` placeholders; its stdout is the wallpaper |
| `FTS_OPENAI_IMAGE_URL` | Base URL of any OpenAI-compatible images server (`POST <base>/images/generations`) |
| `FTS_OPENAI_IMAGE_MODEL` | Model id for that server (default `gpt-image-1`) |
| `FTS_OPENAI_IMAGE_SIZE` | Force a size (e.g. `auto` for api.openai.com; otherwise aspect-mapped 960x544-style buckets) |
| `FTS_OPENAI_API_KEY` | Key for that server (`OPENAI_API_KEY` also accepted; local servers usually need none) |

Examples:

```sh
# any tool that can print a picture
FTS_IMAGE_COMMAND='draw-things-cli --prompt {prompt} --width {width} --height {height}'
FTS_IMAGE_COMMAND='ssh gpu-box do-ai --prompt {prompt} | convert - png:-'

# any OpenAI-compatible server
FTS_OPENAI_IMAGE_URL=http://localhost:8080/v1  FTS_OPENAI_IMAGE_MODEL=flux.1-schnell
FTS_OPENAI_IMAGE_URL=https://api.openai.com/v1 FTS_OPENAI_IMAGE_SIZE=auto
```

All provider environment variables (optional):

| variable | default | meaning |
|---|---|---|
| `FTS_MFLUX_URL` | `http://100.72.41.118:4030` | mflux bridge (FLUX.2 Klein) |
| `GEMINI_API_KEY` | — | Gemini key (`GOOGLE_API_KEY` also accepted) |
| `FTS_COMFYUI_URL` | `http://100.72.41.118:8188` | ComfyUI SDXL fallback |
| `FTS_COMFYUI_CHECKPOINT` | `sd_xl_base_1.0.safetensors` | checkpoint to load |
| `FTS_IMAGE_COMMAND` | — | custom command template (stdout = image) |
| `FTS_OPENAI_IMAGE_URL` | — | OpenAI-compatible images base URL |

## Install as an Omarchy shell plugin

The repo doubles as an [Omarchy shell plugin](SPEC.md#distribution-as-an-omarchy-shell-plugin): a
single bar icon (right section) that opens the studio.

```sh
omarchy plugin add <this-repo-git-url>
omarchy plugin enable scrimwiggins.terminal-theme-studio right
```

Remove with `omarchy plugin remove scrimwiggins.terminal-theme-studio`. The
plugin folder passes `omarchy plugin validate` on its own.

Tests never touch real user config: they redirect everything with
`FOOT_THEME_STUDIO_HOME` / `OMARCHY_PATH` to a temp dir, and
`omarchy-theme-set` is only ever exercised via a mocked subprocess.

## Dependencies, privacy & security

- **Runtime deps:** Python 3.14 with PyGObject (GTK 4 + Adw +
  GdkPixbuf), an Omarchy install for the apply paths, and Omarchy's own
  public scripts (`omarchy-theme-set`, `omarchy-theme-bg-set`). No
  third-party Python packages; all HTTP is stdlib `urllib`.
- **Network:** the studio is offline until *you* press Generate.
  Requests go only to the image endpoint you selected — your local
  bridge/server, or a cloud API with your own key.
- **Writes:** your Foot override, your user themes
  (`~/.config/omarchy/themes/`), and your backgrounds folders. It never
  touches `~/.local/state/omarchy/` itself and never edits another
  tool's config beyond Omarchy's own apply scripts.
- **Plugin safety:** no download-and-execute paths, no sudo/pkexec, no
  bundled binaries — the marketplace's Automated Security Baseline
  greps clean. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full
  submission checklist and the provider-authoring guide.
