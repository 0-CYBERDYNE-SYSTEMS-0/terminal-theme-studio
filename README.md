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
python3 -m unittest discover -s tests   # 101 tests, no display needed
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
