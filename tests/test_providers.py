"""Provider tests: request shapes, response parsing, error paths.

All HTTP goes through an injected fake transport -- these tests never
touch the network.
"""

import base64
import json
import os
import sys
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fts import providers  # noqa: E402

_PNG = b"\x89PNG\r\n\x1a\nnot-really-a-png"


class FakeTransport:
    """Records calls; a handler(method, url, body, headers) -> (status, bytes)."""

    def __init__(self, handler) -> None:
        self.calls: list[tuple[str, str, bytes | None, dict]] = []
        self._handler = handler

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, dict(headers or {})))
        return self._handler(method, url, body, headers)


def _json_response(payload) -> tuple[int, bytes]:
    return 200, json.dumps(payload).encode("utf-8")


class TestLatentsAndMime(unittest.TestCase):
    def test_known_aspects(self):
        self.assertEqual(providers.latents_for_aspect("16:9"), (1344, 768))
        self.assertEqual(providers.latents_for_aspect("16:10"), (1216, 768))
        self.assertEqual(providers.latents_for_aspect("21:9"), (1536, 640))

    def test_unknown_aspect_raises(self):
        with self.assertRaises(ValueError):
            providers.latents_for_aspect("32:9")

    def test_ext_for_mime(self):
        self.assertEqual(providers.ext_for_mime("image/png"), ".png")
        self.assertEqual(providers.ext_for_mime("image/jpeg"), ".jpg")
        self.assertEqual(providers.ext_for_mime("image/webp"), ".webp")
        self.assertEqual(providers.ext_for_mime("image/weird"), ".png")
        self.assertEqual(providers.ext_for_mime(""), ".png")


class TestGeminiProvider(unittest.TestCase):
    def _provider(self, handler) -> tuple[providers.GeminiProvider, FakeTransport]:
        transport = FakeTransport(handler)
        return providers.GeminiProvider(api_key="test-key", transport=transport), transport

    def test_missing_key_is_a_provider_error(self):
        provider = providers.GeminiProvider(api_key=None)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("a wallpaper")
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_request_shape_and_response(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["method"] = method
            seen["url"] = url
            seen["body"] = json.loads(body.decode("utf-8"))
            seen["headers"] = headers
            return _json_response(
                {"output_image": {"data": base64.b64encode(_PNG).decode("ascii"),
                                  "mime_type": "image/png"}}
            )

        provider, transport = self._provider(handler)
        images = provider.generate("a moody wallpaper", aspect="16:9", count=2)

        self.assertEqual(seen["method"], "POST")
        self.assertTrue(seen["url"].startswith("https://generativelanguage"))
        self.assertTrue(seen["url"].endswith("/v1beta/interactions"))
        self.assertEqual(seen["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(seen["body"]["model"], "gemini-3.1-flash-lite-image")
        self.assertEqual(
            seen["body"]["response_format"],
            {"type": "image", "aspect_ratio": "16:9", "image_size": "1K"},
        )
        self.assertEqual(seen["body"]["input"][-1]["type"], "text")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].data, _PNG)
        self.assertEqual(images[0].mime, "image/png")
        self.assertEqual(images[0].provider, "gemini")
        self.assertEqual(images[0].meta["model"], "gemini-3.1-flash-lite-image")

    def test_reference_image_becomes_base64_block(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["body"] = json.loads(body.decode("utf-8"))
            return _json_response(
                {"output_image": {"data": base64.b64encode(_PNG).decode("ascii"),
                                  "mime_type": "image/png"}}
            )

        provider, _transport = self._provider(handler)
        provider.generate("x", reference=(b"ref-bytes", "image/jpeg"))

        first = seen["body"]["input"][0]
        self.assertEqual(first["type"], "image")
        self.assertEqual(first["mime_type"], "image/jpeg")
        self.assertEqual(base64.b64decode(first["data"]), b"ref-bytes")

    def test_http_error_surfaces_message(self):
        def handler(method, url, body, headers):
            return 429, json.dumps(
                {"error": {"message": "resource exhausted"}}
            ).encode("utf-8")

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("429", str(ctx.exception))
        self.assertIn("resource exhausted", str(ctx.exception))

    def test_steps_fallback_extraction(self):
        def handler(method, url, body, headers):
            return _json_response(
                {"steps": [
                    {"type": "thought", "content": [{"type": "text", "text": "hm"}]},
                    {"type": "model_output", "content": [
                        {"type": "text", "text": "here you go"},
                        {"type": "image",
                         "data": base64.b64encode(_PNG).decode("ascii"),
                         "mime_type": "image/png"},
                    ]},
                ]}
            )

        provider, _transport = self._provider(handler)
        images = provider.generate("x")
        self.assertEqual(images[0].data, _PNG)

    def test_no_image_in_response(self):
        def handler(method, url, body, headers):
            return _json_response({"steps": []})

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("no image", str(ctx.exception))

    def test_transport_failure_is_wrapped(self):
        def handler(method, url, body, headers):
            raise OSError("name resolution failed")

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("Gemini request failed", str(ctx.exception))


class TestFluxDimensions(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(providers.flux_dimensions("16:9"), (960, 544))
        self.assertEqual(providers.flux_dimensions("1:1"), (720, 720))

    def test_all_multiples_of_16_near_the_measured_budget(self):
        budget = 720 * 720
        for aspect in ("16:9", "16:10", "21:9", "4:3", "1:1"):
            width, height = providers.flux_dimensions(aspect)
            self.assertEqual(width % 16, 0, aspect)
            self.assertEqual(height % 16, 0, aspect)
            self.assertTrue(0.9 * budget <= width * height <= 1.1 * budget, aspect)

    def test_unknown_aspect_raises(self):
        with self.assertRaises(ValueError):
            providers.flux_dimensions("32:9")


class TestMfluxProvider(unittest.TestCase):
    def _provider(self, handler, **kwargs) -> tuple[providers.MfluxProvider, FakeTransport]:
        transport = FakeTransport(handler)
        defaults = dict(base_url="http://mflux.test:4030/")
        defaults.update(kwargs)
        return providers.MfluxProvider(**defaults, transport=transport), transport

    def _ok_document(self) -> dict:
        return {
            "image_base64": base64.b64encode(_PNG).decode("ascii"),
            "mime_type": "image/png",
            "model": "flux2-klein-4b",
            "width": 960,
            "height": 544,
            "steps": 2,
            "seed": 12345,
            "time_seconds": 21.5,
        }

    def test_request_shape_and_response(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["method"] = method
            seen["url"] = url
            seen["body"] = json.loads(body.decode("utf-8"))
            seen["headers"] = headers
            return _json_response(self._ok_document())

        provider, transport = self._provider(handler)
        images = provider.generate("a wallpaper", aspect="16:9", count=2)

        self.assertEqual(seen["method"], "POST")
        self.assertTrue(seen["url"].endswith("/generate"))
        self.assertEqual(seen["headers"]["Content-Type"], "application/json")
        # Klein: no negative_prompt (guidance pinned), seed None = bridge auto
        self.assertEqual(
            seen["body"],
            {"prompt": "a wallpaper", "width": 960, "height": 544,
             "steps": 2, "seed": None},
        )
        # single-process bridge: requests must serialize one at a time
        self.assertEqual(len(transport.calls), 2)

        self.assertEqual(images[0].data, _PNG)
        self.assertEqual(images[0].mime, "image/png")
        self.assertEqual(images[0].provider, "mflux")
        self.assertEqual(images[0].meta["model"], "flux2-klein-4b")
        self.assertEqual(images[0].meta["time_seconds"], 21.5)

    def test_seed_fixed_and_steps_clamped(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["body"] = json.loads(body.decode("utf-8"))
            return _json_response(self._ok_document())

        provider, _transport = self._provider(handler, steps=9, seed=42)
        provider.generate("x", aspect="1:1")

        self.assertEqual(seen["body"]["steps"], 4)  # Klein's useful range is 1-4
        self.assertEqual(seen["body"]["seed"], 42)
        self.assertEqual((seen["body"]["width"], seen["body"]["height"]),
                         (720, 720))

    def test_error_detail_surfaces(self):
        def handler(method, url, body, headers):
            return 400, json.dumps({"detail": "empty prompt"}).encode("utf-8")

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("")
        self.assertIn("400", str(ctx.exception))
        self.assertIn("empty prompt", str(ctx.exception))

    def test_server_error_detail_surfaces(self):
        def handler(method, url, body, headers):
            return 500, json.dumps({"detail": "mflux failed: out of memory"}).encode()

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("500", str(ctx.exception))
        self.assertIn("out of memory", str(ctx.exception))

    def test_missing_image_data(self):
        def handler(method, url, body, headers):
            return _json_response({"model": "flux2-klein-4b"})

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("no image data", str(ctx.exception))

    def test_unreachable_bridge_is_wrapped(self):
        def handler(method, url, body, headers):
            raise ConnectionRefusedError("refused")

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("Could not reach the mflux bridge", str(ctx.exception))


class TestOpenAIImageProvider(unittest.TestCase):
    def _provider(self, handler, **kwargs) -> tuple[providers.OpenAIImageProvider, FakeTransport]:
        transport = FakeTransport(handler)
        defaults = dict(base_url="http://img.test:8080/v1", api_key="sk-test")
        defaults.update(kwargs)
        return providers.OpenAIImageProvider(**defaults, transport=transport), transport

    def test_requires_a_base_url(self):
        with mock.patch.dict(os.environ, {"FTS_OPENAI_IMAGE_URL": ""}, clear=False):
            provider = providers.OpenAIImageProvider(base_url=None)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("FTS_OPENAI_IMAGE_URL", str(ctx.exception))

    def test_request_shape_and_b64_response(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["method"] = method
            seen["url"] = url
            seen["body"] = json.loads(body.decode("utf-8"))
            seen["headers"] = headers
            return _json_response(
                {"data": [{"b64_json": base64.b64encode(_PNG).decode("ascii")}]}
            )

        provider, transport = self._provider(handler)
        images = provider.generate("a wallpaper", aspect="16:9", count=2)

        self.assertEqual(seen["method"], "POST")
        self.assertTrue(seen["url"].endswith("/v1/images/generations"))
        self.assertEqual(seen["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(
            seen["body"],
            {"model": "gpt-image-1", "prompt": "a wallpaper",
             "size": "960x544", "n": 1},
        )
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(images[0].data, _PNG)
        self.assertEqual(images[0].provider, "openai")
        self.assertEqual(images[0].meta["size"], "960x544")

    def test_url_response_is_fetched(self):
        def handler(method, url, body, headers):
            if method == "POST":
                return _json_response({"data": [{"url": "http://img.test:8080/img/1"}]})
            if method == "GET" and url.endswith("/img/1"):
                return 200, _PNG
            return 404, b"{}"

        provider, _transport = self._provider(handler)
        images = provider.generate("x")
        self.assertEqual(images[0].data, _PNG)

    def test_error_detail_surfaces(self):
        def handler(method, url, body, headers):
            return 400, json.dumps({"error": {"message": "bad size"}}).encode()

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("bad size", str(ctx.exception))

    def test_explicit_size_override(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["body"] = json.loads(body.decode("utf-8"))
            return _json_response(
                {"data": [{"b64_json": base64.b64encode(_PNG).decode("ascii")}]}
            )

        provider, _transport = self._provider(handler, size="auto")
        provider.generate("x")
        self.assertEqual(seen["body"]["size"], "auto")

    def test_no_header_without_key(self):
        seen = {}

        def handler(method, url, body, headers):
            seen["headers"] = headers
            return _json_response(
                {"data": [{"b64_json": base64.b64encode(_PNG).decode("ascii")}]}
            )

        provider, _transport = self._provider(handler, api_key=None)
        provider.generate("x")
        self.assertNotIn("Authorization", seen["headers"])


class TestCustomCommandProvider(unittest.TestCase):
    def test_missing_command_explains_setup(self):
        provider = providers.CustomCommandProvider(command="")
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("FTS_IMAGE_COMMAND", str(ctx.exception))

    def test_runs_a_real_command_and_returns_its_stdout(self):
        provider = providers.CustomCommandProvider(
            command="printf '%s' {prompt}"
        )
        images = provider.generate("misty pines & 'quotes'", aspect="16:9")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, b"misty pines & 'quotes'")
        self.assertEqual(images[0].provider, "custom")
        self.assertEqual(images[0].meta["command"], "printf '%s' {prompt}")

    def test_placeholders_and_mime_sniffing(self):
        # POSIX octal escapes so /bin/sh is dash (Ubuntu CI) or bash.
        provider = providers.CustomCommandProvider(
            command="printf '\\211PNG\\r\\n\\032\\n {width}x{height}'"
        )
        images = provider.generate("x", aspect="21:9")
        self.assertEqual(images[0].data, b"\x89PNG\r\n\x1a\n 1104x464")
        self.assertEqual(images[0].mime, "image/png")

    def test_failing_command_surfaces_stderr(self):
        provider = providers.CustomCommandProvider(command="echo boom >&2; exit 3")
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("boom", str(ctx.exception))

    def test_empty_stdout_is_an_error(self):
        provider = providers.CustomCommandProvider(command="true")
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("no image", str(ctx.exception))


class TestRegistry(unittest.TestCase):
    def test_ids_unique_and_nonempty(self):
        ids = [pid for pid, _label in providers.PROVIDERS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(ids))

    def test_make_provider_covers_every_registry_entry(self):
        for pid, _label in providers.PROVIDERS:
            provider = providers.make_provider(pid)
            self.assertEqual(provider.name, pid)

    def test_make_provider_rejects_unknown(self):
        with self.assertRaises(ValueError):
            providers.make_provider("nonexistent")

    def test_hints_exist_for_every_entry(self):
        for pid, _label in providers.PROVIDERS:
            self.assertTrue(providers.provider_hint(pid), pid)

    def test_sniff_mime(self):
        self.assertEqual(providers.sniff_mime(b"\x89PNG\r\n\x1a\nxx"), "image/png")
        self.assertEqual(providers.sniff_mime(b"\xff\xd8xx"), "image/jpeg")
        self.assertEqual(providers.sniff_mime(b"GIF89a"), "image/gif")
        self.assertEqual(
            providers.sniff_mime(b"RIFFxxxxWEBP"), "image/webp"
        )
        self.assertEqual(providers.sniff_mime(b"junk"), "image/png")


class TestComfyUIProvider(unittest.TestCase):
    def _provider(self, handler, **kwargs) -> tuple[providers.ComfyUIProvider, FakeTransport]:
        transport = FakeTransport(handler)
        defaults = dict(
            base_url="http://comfy.test:8188/",
            checkpoint="sd_xl_base_1.0.safetensors",
            generation_timeout=2.0,
            poll_interval=0.01,
        )
        defaults.update(kwargs)
        return providers.ComfyUIProvider(**defaults, transport=transport), transport

    def _history_ok(self, state={"polled": False}):
        """A history endpoint that reports the job done on the second poll."""
        def handler(method, url, body, headers):
            if method == "POST" and url.endswith("/prompt"):
                return _json_response({"prompt_id": "job-1"})
            if method == "GET" and "/history/" in url:
                if not state["polled"]:
                    state["polled"] = True
                    return _json_response({})
                return _json_response({
                    "job-1": {
                        "status": {"status_str": "success"},
                        "outputs": {"7": {"images": [
                            {"filename": "fts_00001_.png", "subfolder": "",
                             "type": "output"},
                        ]}},
                    }
                })
            if method == "GET" and "/view?" in url:
                return 200, _PNG
            return 404, b"{}"

        return handler

    def test_happy_path_and_graph_shape(self):
        provider, transport = self._provider(self._history_ok())
        images = provider.generate("a wallpaper", negative="text", aspect="16:9")

        prompt_calls = [
            c for c in transport.calls if c[1].endswith("/prompt")
        ]
        self.assertEqual(len(prompt_calls), 1)
        posted = json.loads(prompt_calls[0][2].decode("utf-8"))
        graph = posted["prompt"]
        self.assertTrue(posted["client_id"])
        self.assertEqual(graph["1"]["class_type"], "CheckpointLoaderSimple")
        self.assertEqual(
            graph["1"]["inputs"]["ckpt_name"], "sd_xl_base_1.0.safetensors"
        )
        self.assertEqual(graph["2"]["inputs"]["text"], "a wallpaper")
        self.assertEqual(graph["3"]["inputs"]["text"], "text")
        self.assertEqual(graph["4"]["inputs"], {"width": 1344, "height": 768,
                                                "batch_size": 1})
        self.assertEqual(graph["5"]["inputs"]["positive"], ["2", 0])
        self.assertEqual(graph["5"]["inputs"]["negative"], ["3", 0])
        self.assertIsInstance(graph["5"]["inputs"]["seed"], int)

        view_calls = [c for c in transport.calls if "/view?" in c[1]]
        self.assertEqual(len(view_calls), 1)
        query = urllib.parse.parse_qs(
            view_calls[0][1].split("?", 1)[1]
        )
        self.assertEqual(query["filename"], ["fts_00001_.png"])
        self.assertEqual(query["type"], ["output"])

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].data, _PNG)
        self.assertEqual(images[0].mime, "image/png")
        self.assertEqual(images[0].provider, "comfyui")
        self.assertEqual(images[0].meta["seed"], graph["5"]["inputs"]["seed"])

    def test_prompt_failure(self):
        def handler(method, url, body, headers):
            if method == "POST":
                return 400, json.dumps({"error": {"message": "bad graph"}}).encode()
            return _json_response({})

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("400", str(ctx.exception))
        self.assertIn("bad graph", str(ctx.exception))

    def test_history_error_status(self):
        def handler(method, url, body, headers):
            if method == "POST":
                return _json_response({"prompt_id": "job-1"})
            return _json_response({
                "job-1": {"status": {"status_str": "error"}, "outputs": {}}
            })

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("checkpoint", str(ctx.exception))

    def test_generation_timeout(self):
        def handler(method, url, body, headers):
            if method == "POST":
                return _json_response({"prompt_id": "job-1"})
            return _json_response({})

        provider, _transport = self._provider(
            handler, generation_timeout=0.1, poll_interval=0.02
        )
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("did not finish", str(ctx.exception))

    def test_unreachable_server_is_wrapped(self):
        def handler(method, url, body, headers):
            raise ConnectionRefusedError("refused")

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("Could not reach ComfyUI", str(ctx.exception))

    def test_no_image_outputs(self):
        def handler(method, url, body, headers):
            if method == "POST":
                return _json_response({"prompt_id": "job-1"})
            return _json_response({
                "job-1": {"status": {"status_str": "success"}, "outputs": {"9": {}}}
            })

        provider, _transport = self._provider(handler)
        with self.assertRaises(providers.ProviderError) as ctx:
            provider.generate("x")
        self.assertIn("no image outputs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
