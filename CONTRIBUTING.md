# Contributing to Terminal Theme Studio

A GTK4/libadwaita app for authoring terminal palettes and generating
matching Omarchy themes + wallpapers. This guide covers the dev
workflow, the extension points (especially image providers), and what
it takes to keep the repo shippable as an Omarchy shell plugin.

## Quick start

```sh
python3 -m unittest discover -s tests   # full suite, no display needed
bin/terminal-theme-studio               # the GTK UI
omarchy-plugin-validate "$(pwd)"        # plugin manifest check
```

No third-party Python packages, ever: the app is stdlib-only
(`urllib`, not `requests`; no google-genai SDK). CI runs the suite on
Python 3.12–3.14 plus manifest and export smoke checks.

## Repo invariants (don't break these)

- **Core/UI split**: everything under `fts/` (except `fts/ui/`) must
  import without `gi` or a display. UI code lives in `fts/ui/` and
  never raises into the main loop — failures become toasts or
  `Adw.AlertDialog`.
- **Config through `fts/paths.py`**: every user-visible path and env
  var funnels through there so tests can redirect the world with
  `FOOT_THEME_STUDIO_HOME` / `OMARCHY_PATH`.
- **Writes are atomic** (tmp file + `os.replace`), and the studio never
  writes into Omarchy-managed state (`~/.local/state/omarchy/`) or
  another tool's config — it calls Omarchy's public scripts instead.
- **No network in tests**: providers take an injected transport; tests
  never open sockets. Omarchy scripts are exercised via `unittest.mock`
  only.
- Every module keeps an `__all__`, type hints, and a module docstring
  explaining why it exists.

## Adding an image provider (the main extension point)

The provider dropdown is built from the registry in
`fts/providers.py`; users can already reach *any* endpoint via the
OpenAI-compatible provider or a custom command (`FTS_IMAGE_COMMAND`).
Add a first-class provider like this:

1. **Write the class** in `fts/providers.py` with the shared shape:

   ```python
   class MyProvider:
       def __init__(self, ..., transport=None): ...   # transport-injected
       @property
       def name(self) -> str: return "myprovider"
       def generate(self, prompt, *, aspect="16:9", count=1,
                    reference=None) -> list[GeneratedImage]: ...
   ```

   Rules: raise `ProviderError` with a message a user can act on
   (include the env var to set); never block indefinitely (timeouts on
   everything); keep `gi` out; sequential requests only unless the
   backend is safe to parallelize.

2. **Register it**: add `(id, "Dropdown Label")` to `PROVIDERS`, a
   hint string to `provider_hint()` (the setup env vars, shown under
   the dropdown), and a branch to `make_provider()`. The dialog, its
   hints, and the registry test derive from these.

3. **Test + document**: `tests/test_providers.py` with a
   `FakeTransport` (request shape, response parsing, error paths —
   mirror the existing providers), plus one row each in the README
   provider list and env-var table, and a paragraph in SPEC.md.

Config accessors go in `fts/paths.py` (`FTS_<NAME>` env vars, sensible
defaults, `None` when unset).

## Packaging: the Omarchy shell plugin

The repo root doubles as a plugin: `manifest.json` (schemaVersion 1,
id `scrimwiggins.terminal-theme-studio`, kinds `["bar-widget"]`,
entry point `BarWidget.qml`) plus the QML launcher. Keep
`omarchy-plugin-validate "$(pwd)"` green. The plugin **id is a
permanent marketplace identifier** — never rename it casually; update
every doc that references it if you must.

**Versioning**: bump both `fts/__init__.py::__version__` and
`manifest.json::version` on every user-visible change, keep the test
count in README current, and update README/SPEC.md in the same PR.

## Committing

Conventional-commit subjects (`feat:`, `fix:`, `chore:`, `ci:`), a
body that explains the why, tests green before you push. Run the full
suite locally; CI mirrors it.

## Publishing to the Omarchy plugin marketplace

Listings go through [omacom/omarchy-plugin-marketplace]
(https://github.com/omacom/omarchy-plugin-marketplace) — the registry
behind the plugin browsing sites. Condensed checklist (full details in
that repo's `SUBMISSION.md` and `SECURITY.md#automated-security-baseline`):

- [ ] Public GitHub repo with `manifest.json`, a root README
      (**install AND removal** instructions), a root LICENSE, external
      dependencies documented, and optionally a root `preview.png`
      screenshot (used for the listing card).
- [ ] Plugin ID unique across the whole marketplace (ours:
      `scrimwiggins.terminal-theme-studio` — keep it stable).
- [ ] **Automated Security Baseline** self-check — the static scanner
      flags `curl|sh`, unpinned remote git execution, `NOPASSWD`
      sudoers, PID-from-/tmp + privileged process control; `sudo`,
      `pkexec`, `systemctl`, and package-manager references become
      review capabilities. Our repo currently greps clean:

      ```sh
      grep -rniE "curl.*\| *(ba)?sh|sudo|pkexec|systemctl|systemd-run|\
  cargo install --git|NOPASSWD" --exclude-dir=.git .
      ```

- [ ] Submission = one GitHub issue on the marketplace repo titled
      `[Plugin]: Terminal Theme Studio` with the exact six headings
      (Repository URL / Category / Tags / Suggest a missing tag /
      Maintainer notes / Submission checklist — copy the template
      verbatim from `SUBMISSION.md`). Category `Appearance`; tags from
      the allowed set (we fit `ai`, `bar`, `hyprland`).
- [ ] Approval binds to the **exact commit SHA** scanned. Submit at a
      commit you intend to stay put; every later release needs a
      *Plugin verification* request with the new full SHA, and the
      listing shows "Update unverified" until then.
- [ ] Maintainer notes worth including: the app shells out only to
      Omarchy's own public scripts (`omarchy-theme-set`,
      `omarchy-theme-bg-set`), writes only its own user-theme and
      backgrounds directories, and touches the network only when the
      user presses Generate, against endpoints the user configures.

Upstream watch: formal submission guidelines for Omarchy's own plugin
ecosystem are being discussed in
[basecamp/omarchy#8593](https://github.com/basecamp/omarchy/discussions/8593);
revisit if an official basecamp-run registry lands.
