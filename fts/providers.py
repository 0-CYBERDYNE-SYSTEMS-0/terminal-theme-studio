"""Wallpaper image providers: Gemini (Nano Banana), mflux (Flux), ComfyUI.

The studio's first networked module, kept ``gi``-free and transport-
injected so tests never touch the network.  All providers return
:class:`GeneratedImage` blobs; saving and applying them is Omarchy's
job (:mod:`fts.omarchy`), not theirs.

* ``GeminiProvider`` calls the Gemini Interactions API
  (``https://generativelanguage.googleapis.com/v1beta/interactions``)
  with the cheap image model ``gemini-3.1-flash-lite-image``
  ("Nano Banana 2 Lite"), ``image_size`` fixed at ``1K`` (~$0.034 per
  image).  The key comes from ``GEMINI_API_KEY`` (or
  ``GOOGLE_API_KEY``) via :func:`fts.paths.gemini_api_key`.

* ``MfluxProvider`` (the default local provider) talks to the
  photoLiquidity mflux bridge on the Mac mini M2 — a FastAPI service
  (LaunchAgent ``com.photoliquidity.mflux``) serving FLUX.2 Klein 4B in
  4-bit MLX at ``POST /generate`` (base64 PNG back in JSON — there is
  no file endpoint).  Klein is step-distilled (1–4 steps, 2 is the
  measured sweet spot) and has no negative prompt, with guidance pinned
  at 1.0.  The bridge is single-process: requests serialize, so batches
  are strictly sequential.  Its ``/shutdown`` route is shared
  infrastructure and is never called.

* ``ComfyUIProvider`` (SDXL fallback backend, separate from the mflux
  bridge — never route Flux jobs there) drives a ComfyUI server's
  ``/prompt`` queue with a minimal txt2img graph, polls
  ``/history/<id>`` and downloads the result from ``/view``.  The
  endpoint and checkpoint default to the Mac mini M2
  (``FTS_COMFYUI_URL`` / ``FTS_COMFYUI_CHECKPOINT``).
"""

from __future__ import annotations

import base64
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field

from . import paths

__all__ = [
    "ProviderError",
    "GeneratedImage",
    "GeminiProvider",
    "MfluxProvider",
    "ComfyUIProvider",
    "latents_for_aspect",
    "flux_dimensions",
    "ext_for_mime",
]

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_DEFAULT_MODEL = "gemini-3.1-flash-lite-image"


class ProviderError(RuntimeError):
    """A wallpaper provider failed; the message is user-presentable."""


@dataclass(frozen=True)
class GeneratedImage:
    """One generated wallpaper: raw image bytes plus provenance."""

    data: bytes
    mime: str
    provider: str  # "gemini" | "comfyui"
    prompt: str
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# shared plumbing
# --------------------------------------------------------------------------

def _urllib_transport(timeout: float):
    """Default transport: urllib with the given per-request timeout.

    HTTP error statuses are returned as ``(status, body)`` so callers
    can format them; transport-level failures (DNS, refused, timeout)
    raise and are wrapped by the provider.
    """

    def transport(method: str, url: str, body: bytes | None, headers: dict):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    return transport


def ext_for_mime(mime: str) -> str:
    """File extension for an image mime type ('.png' fallback)."""
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }.get((mime or "").lower(), ".png")


def latents_for_aspect(aspect: str) -> tuple[int, int]:
    """SDXL-friendly latent dimensions (multiples of 64) for an aspect.

    The buckets are the ones SDXL was trained on, so the local ComfyUI
    provider generates at native quality; Gemini receives the aspect
    string directly instead.
    """
    buckets = {
        "16:9": (1344, 768),
        "16:10": (1216, 768),
        "21:9": (1536, 640),
        "4:3": (1152, 896),
        "1:1": (1024, 1024),
    }
    try:
        return buckets[aspect]
    except KeyError:
        raise ValueError(f"unsupported aspect ratio: {aspect!r}") from None


# --------------------------------------------------------------------------
# Gemini (Nano Banana)
# --------------------------------------------------------------------------

class GeminiProvider:
    """Nano Banana 2 Lite via the Gemini Interactions API (1K images)."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = _DEFAULT_MODEL,
        image_size: str = "1K",
        timeout: float = 120.0,
        transport=None,
    ) -> None:
        self._api_key = api_key if api_key is not None else paths.gemini_api_key()
        self._model = model
        self._image_size = image_size
        self._timeout = timeout
        self._transport = transport or _urllib_transport(timeout)

    @property
    def name(self) -> str:
        return "gemini"

    def generate(
        self,
        prompt: str,
        *,
        aspect: str = "16:9",
        count: int = 1,
        reference: tuple[bytes, str] | None = None,
    ) -> list[GeneratedImage]:
        """Generate ``count`` images for the prompt.

        ``reference`` is an optional ``(bytes, mime)`` source image (the
        image the palette was extracted from) passed to the model so the
        wallpapers stay true to the original look.  Raises
        :class:`ProviderError` with a user-presentable message.
        """
        if not self._api_key:
            raise ProviderError(
                "No Gemini API key found. Create one at "
                "https://aistudio.google.com/apikey, then set GEMINI_API_KEY — "
                "e.g. save “GEMINI_API_KEY=…” to "
                "~/.config/environment.d/90-gemini.conf and log out and back in."
            )

        input_blocks: list[dict] = []
        if reference is not None:
            data, mime = reference
            input_blocks.append(
                {
                    "type": "image",
                    "mime_type": mime,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )
        input_blocks.append({"type": "text", "text": prompt})

        body = {
            "model": self._model,
            "input": input_blocks,
            "response_format": {
                "type": "image",
                "aspect_ratio": aspect,
                "image_size": self._image_size,
            },
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}

        images: list[GeneratedImage] = []
        for _ in range(max(1, count)):
            raw = json.dumps(body).encode("utf-8")
            try:
                status, payload = self._transport(
                    "POST", _GEMINI_URL, raw, headers
                )
            except Exception as exc:
                raise ProviderError(f"Gemini request failed: {exc}") from exc
            document = _parse_json(status, payload, "Gemini")
            data, mime = _extract_image(document)
            images.append(
                GeneratedImage(
                    data=data,
                    mime=mime,
                    provider=self.name,
                    prompt=prompt,
                    meta={"model": self._model, "aspect": aspect, "size": self._image_size},
                )
            )
        return images


def _parse_json(status: int, payload: bytes, who: str) -> dict:
    """Decode a provider JSON response, mapping failures to ProviderError."""
    text = payload.decode("utf-8", errors="replace")
    try:
        document = json.loads(text)
    except ValueError:
        document = None
    if status != 200:
        detail = ""
        if isinstance(document, dict):
            err = document.get("error")
            if isinstance(err, dict):
                detail = str(err.get("message") or "")
            if not detail and document.get("detail"):
                detail = str(document["detail"])  # FastAPI-style errors
        raise ProviderError(
            f"{who} returned HTTP {status}: {detail or text[:300] or '(no body)'}"
        )
    if not isinstance(document, dict):
        raise ProviderError(f"{who} returned a non-JSON response")
    return document


def _extract_image(document: dict) -> tuple[bytes, str]:
    """Pull (bytes, mime) out of an Interactions API response.

    Primary shape is ``interaction.output_image.data``; interleaved
    responses instead carry image blocks under ``steps[].content`` of the
    last ``model_output`` -- the newest image wins.
    """
    img = document.get("output_image")
    if isinstance(img, dict) and img.get("data"):
        return base64.b64decode(img["data"]), img.get("mime_type") or "image/png"

    fallback: tuple[bytes, str] | None = None
    for step in document.get("steps") or []:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        blocks = content if isinstance(content, list) else [content]
        for block in blocks:
            if (
                isinstance(block, dict)
                and block.get("type") == "image"
                and block.get("data")
            ):
                fallback = (
                    base64.b64decode(block["data"]),
                    block.get("mime_type") or "image/png",
                )
    if fallback is not None:
        return fallback
    raise ProviderError(
        "Gemini's response carried no image (the prompt may have been "
        "refused; try rephrasing the aesthetic)"
    )


# --------------------------------------------------------------------------
# mflux bridge (FLUX.2 Klein, the default local provider)
# --------------------------------------------------------------------------

def flux_dimensions(aspect: str) -> tuple[int, int]:
    """Dimensions for the mflux bridge, per aspect ratio.

    720x720 @ 2 steps is the measured sweet spot on the M2 (~20-34 s
    warm); each bucket redistributes that pixel budget to the requested
    aspect, snapped to multiples of 16 (FLUX VAE/patch alignment), so
    timing and quality hold across aspect ratios.
    """
    buckets = {
        "16:9": (960, 544),
        "16:10": (912, 576),
        "21:9": (1104, 464),
        "4:3": (832, 624),
        "1:1": (720, 720),
    }
    try:
        return buckets[aspect]
    except KeyError:
        raise ValueError(f"unsupported aspect ratio: {aspect!r}") from None


class MfluxProvider:
    """FLUX.2 Klein 4B (4-bit MLX) via the photoLiquidity mflux bridge."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        steps: int = 2,
        seed: int | None = None,
        request_timeout: float = 300.0,
        transport=None,
    ) -> None:
        self._base = (base_url or paths.mflux_url()).rstrip("/")
        # Klein is step-distilled; 1-4 is the useful range, 2 the sweet spot
        self._steps = max(1, min(4, int(steps)))
        self._seed = seed  # None = bridge auto-seeds per request
        self._request_timeout = request_timeout
        self._transport = transport or _urllib_transport(request_timeout)

    @property
    def name(self) -> str:
        return "mflux"

    def generate(
        self,
        prompt: str,
        *,
        aspect: str = "16:9",
        count: int = 1,
        reference: tuple[bytes, str] | None = None,
    ) -> list[GeneratedImage]:
        """Generate ``count`` images, strictly sequentially.

        The bridge is single-process/single-model, so parallel batches
        would just serialize behind each other.  ``reference`` is
        accepted for provider parity but ignored (the bridge is txt2img
        only).  Prompts are capped around 512 tokens server-side and
        silently truncated, so :func:`fts.aesthetic.build_prompt` stays
        deliberately concise.
        """
        del reference  # txt2img only, by design
        width, height = flux_dimensions(aspect)
        images: list[GeneratedImage] = []
        for index in range(max(1, count)):
            body = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": self._steps,
                "seed": self._seed,
            }
            status, payload = self._request(
                "POST",
                f"{self._base}/generate",
                json.dumps(body).encode("utf-8"),
            )
            document = _parse_json(status, payload, "mflux /generate")
            try:
                data = base64.b64decode(document.get("image_base64") or "")
            except (ValueError, TypeError) as exc:
                raise ProviderError(f"mflux sent a corrupt image: {exc}") from exc
            if not data:
                raise ProviderError("mflux returned no image data")
            images.append(
                GeneratedImage(
                    data=data,
                    mime=document.get("mime_type") or "image/png",
                    provider=self.name,
                    prompt=prompt,
                    meta={
                        "model": document.get("model"),
                        "width": document.get("width", width),
                        "height": document.get("height", height),
                        "steps": document.get("steps", self._steps),
                        "seed": document.get("seed", self._seed),
                        "time_seconds": document.get("time_seconds"),
                        "index": index,
                    },
                )
            )
        return images

    def _request(self, method: str, url: str, body: bytes | None = None):
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            return self._transport(method, url, body, headers)
        except Exception as exc:
            raise ProviderError(
                f"Could not reach the mflux bridge at {self._base}: {exc}"
            ) from exc


# --------------------------------------------------------------------------
# ComfyUI (local server)
# --------------------------------------------------------------------------

class ComfyUIProvider:
    """Minimal txt2img against a ComfyUI server (default: Mac mini M2)."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        checkpoint: str | None = None,
        steps: int = 28,
        cfg: float = 7.0,
        request_timeout: float = 30.0,
        generation_timeout: float = 300.0,
        poll_interval: float = 1.0,
        transport=None,
    ) -> None:
        self._base = (base_url or paths.comfyui_url()).rstrip("/")
        self._checkpoint = checkpoint or paths.comfyui_checkpoint()
        self._steps = steps
        self._cfg = cfg
        self._request_timeout = request_timeout
        self._generation_timeout = generation_timeout
        self._poll_interval = poll_interval
        self._transport = transport or _urllib_transport(request_timeout)

    @property
    def name(self) -> str:
        return "comfyui"

    def generate(
        self,
        prompt: str,
        *,
        negative: str = "",
        aspect: str = "16:9",
        count: int = 1,
        reference: tuple[bytes, str] | None = None,
    ) -> list[GeneratedImage]:
        """Queue ``count`` txt2img jobs and collect their outputs.

        ``reference`` is accepted for provider parity but ignored: img2img
        needs a checkpoint-specific denoise workflow, so the local server
        is text-driven only.
        """
        del reference  # txt2img only, by design
        width, height = latents_for_aspect(aspect)
        client_id = str(uuid.uuid4())
        images: list[GeneratedImage] = []
        for index in range(max(1, count)):
            seed = random.getrandbits(64)
            graph = self._graph(prompt, negative, width, height, seed)
            status, payload = self._request(
                "POST",
                f"{self._base}/prompt",
                json.dumps({"prompt": graph, "client_id": client_id}).encode("utf-8"),
            )
            document = _parse_json(status, payload, "ComfyUI /prompt")
            prompt_id = document.get("prompt_id")
            if not prompt_id:
                raise ProviderError(f"ComfyUI did not return a prompt id: {document}")
            outputs = self._wait_for_outputs(prompt_id)
            data, mime = self._download_first_image(outputs)
            images.append(
                GeneratedImage(
                    data=data,
                    mime=mime,
                    provider=self.name,
                    prompt=prompt,
                    meta={
                        "checkpoint": self._checkpoint,
                        "width": width,
                        "height": height,
                        "seed": seed,
                        "index": index,
                    },
                )
            )
        return images

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _graph(
        self, positive: str, negative: str, width: int, height: int, seed: int
    ) -> dict:
        """The API-format node graph: checkpoint -> two text encodes ->
        empty latent -> KSampler -> VAE decode -> SaveImage."""
        return {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": self._checkpoint},
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": positive, "clip": ["1", 1]},
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": negative, "clip": ["1", 1]},
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": width, "height": height, "batch_size": 1},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": self._steps,
                    "cfg": self._cfg,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "terminal-theme-studio",
                    "images": ["6", 0],
                },
            },
        }

    def _request(self, method: str, url: str, body: bytes | None = None):
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            return self._transport(method, url, body, headers)
        except Exception as exc:
            raise ProviderError(
                f"Could not reach ComfyUI at {self._base}: {exc}"
            ) from exc

    def _wait_for_outputs(self, prompt_id: str) -> dict:
        """Poll /history until the job finishes; returns its outputs dict."""
        deadline = time.monotonic() + self._generation_timeout
        while time.monotonic() < deadline:
            status, payload = self._request("GET", f"{self._base}/history/{prompt_id}")
            document = _parse_json(status, payload, "ComfyUI /history")
            entry = document.get(prompt_id)
            if isinstance(entry, dict):
                state = entry.get("status") or {}
                if state.get("status_str") == "error":
                    raise ProviderError(
                        "ComfyUI reported a failed job (is the checkpoint "
                        f"“{self._checkpoint}” installed on the server?)"
                    )
                outputs = entry.get("outputs")
                if outputs:
                    return outputs
            time.sleep(self._poll_interval)
        raise ProviderError(
            "ComfyUI did not finish in time "
            f"({self._generation_timeout:.0f}s) — the server may be busy"
        )

    def _download_first_image(self, outputs: dict) -> tuple[bytes, str]:
        """Fetch the first output image via /view (raw bytes, usually png)."""
        for node in outputs.values():
            for info in node.get("images") or []:
                query = urllib.parse.urlencode(
                    {
                        "filename": info.get("filename", ""),
                        "subfolder": info.get("subfolder", ""),
                        "type": info.get("type", "output"),
                    }
                )
                status, data = self._request("GET", f"{self._base}/view?{query}")
                if status == 200 and data:
                    mime = "image/png"
                    if info.get("filename", "").lower().endswith((".jpg", ".jpeg")):
                        mime = "image/jpeg"
                    return data, mime
        raise ProviderError("ComfyUI finished but returned no image outputs")
