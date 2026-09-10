"""Wallpaper studio dialog: palette + aesthetic words → a full Omarchy theme.

The generation runs on a worker thread (providers are plain blocking
HTTP); results are marshalled back with ``GLib.idle_add``.  By default
the dialog performs the complete end-to-end flow: it writes the working
palette as ``~/.config/omarchy/themes/<name>/colors.toml``, generates
the wallpapers straight into that theme's ``backgrounds/`` directory,
applies the theme with ``omarchy-theme-set``, and sets the first
wallpaper the Omarchy way (omarchy-theme-bg-set).  Opting out of
"Create a full Omarchy theme" keeps the lighter behaviour: generated
images just join the current theme's user-backgrounds rotation.
Failures surface as alerts/toasts and never raise into the main loop.
"""

from __future__ import annotations

import mimetypes
import threading
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from .. import aesthetic, omarchy, paths, providers  # noqa: E402

__all__ = ["WallpaperDialog"]

_PROVIDERS = (
    ("mflux", "Flux — Mac mini M2 (local)"),
    ("gemini", "Gemini — Nano Banana 2 Lite (cloud)"),
    ("comfyui", "ComfyUI — SDXL (local fallback)"),
)

_ASPECTS = (
    ("16:9", "16:9 — desktop"),
    ("16:10", "16:10 — laptop"),
    ("21:9", "21:9 — ultrawide"),
)


class WallpaperDialog(Adw.Dialog):
    """Generate wallpapers for the working palette with one click."""

    def __init__(
        self,
        get_palette,
        default_name,
        toast,
        source_path: str | None = None,
        on_theme_created=None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._get_palette = get_palette
        self._default_name = default_name or "wallpaper"
        self._toast = toast
        self._source_path = source_path
        self._on_theme_created = on_theme_created
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()

        self.set_title("Wallpapers")
        self.set_content_width(680)
        self.set_content_height(680)

        generate_btn = Gtk.Button(label="Generate")
        generate_btn.add_css_class("suggested-action")
        generate_btn.set_tooltip_text("Generate wallpapers for the working palette")
        generate_btn.connect("clicked", self._on_generate)
        self._generate_btn = generate_btn

        header = Adw.HeaderBar()
        header.pack_end(generate_btn)
        header.set_title_widget(
            Adw.WindowTitle(
                title="Generate wallpapers",
                subtitle="from the working palette",
            )
        )

        # ---- options -----------------------------------------------------
        self._entry = Adw.EntryRow(title="Aesthetic — a few words")
        self._entry.set_tooltip_text(
            "Three or four words for the look you want; leave blank to let "
            "the palette decide"
        )
        self._auto = Gtk.Label(xalign=0.0, wrap=True)
        self._auto.add_css_class("caption")
        self._auto.add_css_class("dim-label")

        self._dest = Gtk.Label(xalign=0.0, wrap=True)
        self._dest.add_css_class("caption")
        self._dest.add_css_class("dim-label")

        self._provider = Adw.ComboRow(title="Provider")
        provider_list = Gtk.StringList()
        for _pid, label in _PROVIDERS:
            provider_list.append(label)
        self._provider.set_model(provider_list)
        self._provider.set_selected(0)
        self._provider.connect("notify::selected", self._on_provider_changed)

        self._aspect = Adw.ComboRow(title="Aspect ratio")
        aspect_list = Gtk.StringList()
        for _aid, label in _ASPECTS:
            aspect_list.append(label)
        self._aspect.set_model(aspect_list)
        self._aspect.set_selected(0)

        self._count = Adw.SpinRow.new_with_range(1, 4, 1)
        self._count.set_title("How many")
        self._count.set_value(2)

        # ---- end-to-end theme creation (the default) ----------------------
        self._theme_entry = Adw.EntryRow(title="New theme name")
        self._theme_entry.set_text(self._default_name)

        self._create_theme = Adw.SwitchRow(
            title="Create a full Omarchy theme",
            subtitle=(
                "Write the palette as colors.toml + these wallpapers as a "
                "new theme under ~/.config/omarchy/themes"
            ),
        )
        self._create_theme.set_active(True)
        self._create_theme.connect("notify::active", self._on_mode_changed)

        self._apply_theme = Adw.SwitchRow(
            title="Apply it when done",
            subtitle=(
                "Run omarchy-theme-set and set the first wallpaper — "
                "the whole desktop switches to the new theme"
            ),
        )
        self._apply_theme.set_active(True)

        self._reference = Adw.SwitchRow(
            title="Let the source image guide the look",
            subtitle="Pass the image the palette came from to Gemini as a reference",
        )
        self._reference.set_sensitive(self._source_path is not None)

        options = Adw.PreferencesGroup()
        options.add(self._entry)
        options.add(self._provider)
        options.add(self._aspect)
        options.add(self._count)
        options.add(self._theme_entry)
        options.add(self._create_theme)
        options.add(self._apply_theme)
        options.add(self._reference)

        # ---- progress + results -------------------------------------------
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        self._status = Gtk.Label(xalign=0.0, wrap=True)
        self._status.add_css_class("caption")
        self._status.add_css_class("dim-label")
        status_box.append(self._spinner)
        status_box.append(self._status)

        self._results = Gtk.FlowBox()
        self._results.set_selection_mode(Gtk.SelectionMode.NONE)
        self._results.set_homogeneous(True)
        self._results.set_min_children_per_line(1)
        self._results.set_max_children_per_line(2)
        self._results.set_column_spacing(12)
        self._results.set_row_spacing(12)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(24)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.append(options)
        content.append(self._auto)
        content.append(self._dest)
        content.append(status_box)
        content.append(self._results)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(content)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

        self.connect("closed", self._on_closed)
        self._entry.connect("changed", self._on_entry_changed)
        self._theme_entry.connect("changed", self._update_save_hint)
        self._apply_theme.connect("notify::active", self._update_save_hint)
        self._update_auto()
        self._update_provider_hint()
        self._update_save_hint()
        self._apply_theme.set_sensitive(self._creating())

    # ------------------------------------------------------------------
    # option state
    # ------------------------------------------------------------------

    def _selected_provider(self) -> str:
        return _PROVIDERS[self._provider.get_selected()][0]

    def _selected_aspect(self) -> str:
        return _ASPECTS[self._aspect.get_selected()][0]

    def _creating(self) -> bool:
        return self._create_theme.get_active()

    def _theme_slug_or_none(self) -> str | None:
        try:
            return omarchy.normalize_slug(self._theme_entry.get_text().strip())
        except ValueError:
            return None

    def _target_slug(self) -> tuple[str | None, str | None]:
        """(slug, error) for the active mode: the new theme's name, or the
        current theme whose rotation the wallpapers join."""
        if self._creating():
            slug = self._theme_slug_or_none()
            if slug is None:
                return None, (
                    "Invalid theme name: "
                    f"{self._theme_entry.get_text().strip()!r} (must not be "
                    "empty, start with '.', or contain '/')"
                )
            return slug, None
        theme = omarchy.current_theme_name()
        if theme:
            return theme, None
        try:
            return omarchy.normalize_slug(self._default_name), None
        except ValueError:
            return "wallpaper", None

    def _update_auto(self, *args) -> None:
        words = self._entry.get_text().strip()
        if words:
            self._auto.set_text(f"Using your words: “{words}”")
            return
        detected = aesthetic.derive_aesthetic(self._get_palette())
        self._auto.set_text(f"Auto-detected aesthetic: {detected}")

    def _on_entry_changed(self, *args) -> None:
        self._update_auto()

    def _on_provider_changed(self, *args) -> None:
        gemini = self._selected_provider() == "gemini"
        self._reference.set_sensitive(gemini and self._source_path is not None)
        self._update_provider_hint()

    def _on_mode_changed(self, *args) -> None:
        self._apply_theme.set_sensitive(self._creating())
        self._generate_btn.set_label("Create Theme" if self._creating() else "Generate")
        self._update_save_hint()

    def _update_save_hint(self, *args) -> None:
        if self._creating():
            slug = self._theme_slug_or_none()
            if slug is None:
                self._dest.set_text(
                    "Enter a valid theme name (not empty, no leading '.', no '/')"
                )
                return
            applied = (
                " — then applied to the whole desktop"
                if self._apply_theme.get_active()
                else ""
            )
            self._dest.set_text(
                f"Creates ~/.config/omarchy/themes/{slug}/ "
                f"(colors.toml + backgrounds/){applied}"
            )
        else:
            theme = omarchy.current_theme_name() or self._default_name
            self._dest.set_text(
                f"Wallpapers join “{theme}” in "
                "~/.config/omarchy/backgrounds/ (rotation only, no theme write)"
            )

    def _update_provider_hint(self) -> None:
        if self._selected_provider() == "gemini":
            self._provider.set_subtitle(
                "Cloud: ~$0.03 per 1K wallpaper on the key's Google account"
            )
        elif self._selected_provider() == "mflux":
            self._provider.set_subtitle(
                f"Local and free: FLUX.2 Klein at {paths.mflux_url()} "
                "(about 20–30 s per image)"
            )
        else:
            self._provider.set_subtitle(
                f"Local and free: ComfyUI (SDXL fallback) at "
                f"{paths.comfyui_url()} — slower, about a minute per image"
            )

    # ------------------------------------------------------------------
    # generation
    # ------------------------------------------------------------------

    def _alert(self, heading: str, body: str) -> None:
        alert = Adw.AlertDialog(heading=heading, body=body)
        alert.add_response("close", "OK")
        alert.set_close_response("close")
        alert.present(self)

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._generate_btn.set_sensitive(not busy)
        self._spinner.set_visible(busy)
        if busy:
            self._spinner.start()
        else:
            self._spinner.stop()
        self._status.set_text(status)

    def _on_generate(self, button) -> None:
        if self._thread is not None:
            return

        palette = self._get_palette()
        slug, slug_error = self._target_slug()
        if slug is None:
            self._toast(slug_error or "Invalid theme name")
            return
        creating = self._creating()
        apply_after = creating and self._apply_theme.get_active()

        words = self._entry.get_text().strip()
        phrase = words or aesthetic.derive_aesthetic(palette)
        aspect = self._selected_aspect()
        count = int(self._count.get_value())
        provider = self._make_provider()
        prompt = aesthetic.build_prompt(phrase, palette, aspect)
        negative = aesthetic.negative_prompt()

        reference = None
        if (
            provider.name == "gemini"
            and self._reference.get_sensitive()
            and self._reference.get_active()
        ):
            mime = mimetypes.guess_type(self._source_path)[0] or "image/png"
            try:
                with open(self._source_path, "rb") as fh:
                    reference = (fh.read(), mime)
            except OSError as exc:
                self._toast(f"Could not read the source image: {exc}")
                return

        self._cancel.clear()
        self._set_busy(True, f"Generating 1 of {count}…")
        self._thread = threading.Thread(
            target=self._worker,
            args=(provider, prompt, negative, aspect, count, reference,
                  palette, creating, slug, apply_after),
            daemon=True,
        )
        self._thread.start()

    def _make_provider(self):
        provider_id = self._selected_provider()
        if provider_id == "comfyui":
            return providers.ComfyUIProvider()
        if provider_id == "gemini":
            return providers.GeminiProvider()
        return providers.MfluxProvider()

    def _worker(
        self, provider, prompt, negative, aspect, count, reference,
        palette, creating, slug, apply_after,
    ) -> None:
        """The end-to-end sequence: colors.toml → wallpapers into the
        theme → apply → set wallpaper.  All filesystem/apply work happens
        here on the worker thread; UI updates go through idle_add."""
        saved: list[tuple[str, object]] = []
        colors_path = None
        error = None
        apply_error = None
        try:
            if creating:
                colors_path = omarchy.save_user_theme(palette, slug)
            for index in range(count):
                if self._cancel.is_set():
                    break
                GLib.idle_add(
                    self._set_busy, True, f"Generating {index + 1} of {count}…"
                )
                if provider.name == "comfyui":
                    images = provider.generate(
                        prompt, negative=negative, aspect=aspect, count=1
                    )
                else:
                    images = provider.generate(
                        prompt, aspect=aspect, count=1, reference=reference
                    )
                image = images[0]
                path = omarchy.save_wallpaper(
                    image.data,
                    slug,
                    omarchy.normalize_slug(self._default_name),
                    providers.ext_for_mime(image.mime),
                    into_theme=creating,
                )
                saved.append((str(path), image))
                GLib.idle_add(self._add_result, str(path), image)

            if creating and saved and apply_after and not self._cancel.is_set():
                GLib.idle_add(self._set_busy, True, "Applying the theme…")
                try:
                    omarchy.apply_full_theme(slug)
                    omarchy.set_wallpaper(saved[0][0])
                except Exception as exc:
                    print(
                        f"terminal-theme-studio: apply_full_theme failed: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    apply_error = str(exc)
        except Exception as exc:
            print(
                f"terminal-theme-studio: wallpaper generation failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            error = str(exc)
        GLib.idle_add(
            self._on_finished, saved, colors_path,
            slug if creating else None, error, apply_error,
        )

    def _add_result(self, path_str: str, image) -> None:
        picture = Gtk.Picture.new_for_bytes(GLib.Bytes.new(image.data))
        picture.set_size_request(300, 168)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)

        caption = Gtk.Label(label=path_str.rsplit("/", 1)[-1], wrap=True)
        caption.add_css_class("caption")
        caption.add_css_class("dim-label")

        set_btn = Gtk.Button(label="Set as Wallpaper")
        set_btn.connect("clicked", self._on_set_wallpaper, path_str)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.set_margin_top(6)
        card.set_margin_bottom(6)
        card.set_margin_start(6)
        card.set_margin_end(6)
        card.append(picture)
        card.append(caption)
        card.append(set_btn)

        frame = Gtk.Frame()
        frame.add_css_class("card")
        frame.set_child(card)
        self._results.append(frame)

    def _on_finished(self, saved, colors_path, created_slug, error, apply_error) -> None:
        self._thread = None
        self._set_busy(False)

        if created_slug and colors_path is not None:
            if self._on_theme_created is not None:
                self._on_theme_created(created_slug, colors_path)

        directory = saved[0][0].rsplit("/", 1)[0] if saved else ""
        if error is None and saved:
            if created_slug and apply_error is None:
                self._toast(
                    f"Theme “{created_slug}” created and applied — "
                    f"{len(saved)} wallpaper(s) in {directory}"
                )
            elif created_slug:
                # The theme exists; only the desktop switch failed.
                self._alert(
                    "Theme created, but the full apply failed",
                    f"“{created_slug}” is saved under ~/.config/omarchy/themes "
                    f"with {len(saved)} wallpaper(s).\n\n"
                    f"omarchy-theme-set failed: {apply_error}",
                )
            else:
                self._toast(f"Saved {len(saved)} wallpaper(s) to {directory}")
        elif error is not None:
            body = error
            if created_slug and colors_path is not None:
                body = (
                    f"The theme “{created_slug}” was created, but generation "
                    f"failed partway:\n\n{error}"
                )
            self._alert("Wallpaper generation failed", body)

    def _on_set_wallpaper(self, button, path_str: str) -> None:
        try:
            omarchy.set_wallpaper(path_str)
        except Exception as exc:
            print(
                f"terminal-theme-studio: set_wallpaper failed: {exc}",
                file=sys.stderr,
                flush=True,
            )
            self._alert("Could not set the wallpaper", str(exc))
            return
        self._toast(f"Wallpaper set: {path_str.rsplit('/', 1)[-1]}")

    def _on_closed(self, dialog) -> None:
        self._cancel.set()
