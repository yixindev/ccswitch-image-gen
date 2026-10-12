"""Contract tests against a local HTTP server; no API credentials or spend needed."""
import base64
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
# A valid 1x1 PNG, enough to verify exact Base64 decoding and file writes.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH1sAAAAASUVORK5CYII="
)


class ImageGenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.response_status = 200
        cls.response_body = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                cls.requests.append((self.path, self.headers, body))
                self.send_response(cls.response_status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(cls.response_body).encode())

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.prompt = self.work / "prompt.txt"
        self.prompt.write_text("生成一张科技海报。\n不要水印。", encoding="utf-8")
        self.output = self.work / "outputs" / "image.png"
        self.env = dict(os.environ)
        self.env.pop("OPENAI_IMAGE_MODEL", None)
        self.env.update(
            OPENAI_API_KEY="test-key-not-a-real-secret",
            OPENAI_BASE_URL=f"http://127.0.0.1:{self.server.server_port}/v1/",
            HOME=str(self.work),
            CODEX_HOME=str(self.work / ".codex"),
        )
        type(self).requests.clear()
        type(self).response_status = 200
        type(self).response_body = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}

    def run_cli(self, *args, wrapper=False):
        executable = ([str(ROOT / "ccswitch-imagegen")] if wrapper else
                      [sys.executable, str(ROOT / "ccswitch-image-gen.py")])
        return subprocess.run(
            executable + ["--prompt-file", str(self.prompt), "--output", str(self.output), *args],
            env=self.env, capture_output=True, text=True, timeout=10,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), PNG)
        self.assertEqual(result.stdout.strip(), str(self.output))

    def json_payload(self):
        path, headers, body = self.requests[-1]
        self.assertEqual(path, "/v1/images/generations")
        self.assertEqual(headers["Authorization"], "Bearer test-key-not-a-real-secret")
        self.assertEqual(headers["Content-Type"], "application/json")
        return json.loads(body)

    def multipart_payload(self):
        path, headers, body = self.requests[-1]
        self.assertEqual(path, "/v1/images/edits")
        self.assertEqual(headers["Authorization"], "Bearer test-key-not-a-real-secret")
        self.assertTrue(headers["Content-Type"].startswith("multipart/form-data; boundary="))
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + headers["Content-Type"] + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
        )
        fields, files = {}, []
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if part.get_filename():
                files.append((name, part.get_filename(), part.get_content_type(), part.get_payload(decode=True)))
            else:
                fields[name] = part.get_payload(decode=True).decode("utf-8")
        return fields, files

    def test_default_flare_generation(self):
        self.assert_success(self.run_cli())
        self.assertEqual(self.json_payload(), {
            "model": "gpt-image-2.5-flare",
            "prompt": self.prompt.read_text(encoding="utf-8"),
            "size": "1024x1536", "quality": "high",
        })

    def test_model_environment_and_cli_override(self):
        self.env["OPENAI_IMAGE_MODEL"] = "gpt-image-2.5-sunburst"
        self.assert_success(self.run_cli())
        self.assertEqual(self.json_payload()["model"], "gpt-image-2.5-sunburst")
        self.assert_success(self.run_cli("--model", "gpt-image-2"))
        self.assertEqual(self.json_payload()["model"], "gpt-image-2")

    def test_empty_model_environment_uses_default(self):
        self.env["OPENAI_IMAGE_MODEL"] = ""
        self.assert_success(self.run_cli())
        self.assertEqual(self.json_payload()["model"], "gpt-image-2.5-flare")

    def test_quality_and_size_passthrough(self):
        for quality in ("low", "medium", "high", "xhigh", "max", "auto"):
            with self.subTest(quality=quality):
                self.assert_success(self.run_cli("--quality", quality, "--size", "2048x1152"))
                payload = self.json_payload()
                self.assertEqual(payload["quality"], quality)
                self.assertEqual(payload["size"], "2048x1152")

    def test_output_options_generation(self):
        self.assert_success(self.run_cli(
            "--output-format", "webp", "--background", "transparent",
            "--output-compression", "0",
        ))
        payload = self.json_payload()
        self.assertEqual(payload["output_format"], "webp")
        self.assertEqual(payload["background"], "transparent")
        self.assertEqual(payload["output_compression"], 0)
        self.assertIsInstance(payload["output_compression"], int)

    def test_transparent_default_png(self):
        self.assert_success(self.run_cli("--background", "transparent"))
        self.assertEqual(self.json_payload()["background"], "transparent")
        self.assertNotIn("output_format", self.json_payload())

    def test_multiple_references_mask_and_options(self):
        paths = [self.work / name for name in ("参考图.png", "second.png", "mask.png")]
        for path in paths:
            path.write_bytes(PNG)
        self.assert_success(self.run_cli(
            "--image", str(paths[0]), "--image", str(paths[1]), "--mask", str(paths[2]),
            "--quality", "max", "--size", "auto", "--output-format", "webp",
            "--background", "transparent", "--output-compression", "100",
        ))
        fields, files = self.multipart_payload()
        self.assertEqual(fields, {
            "model": "gpt-image-2.5-flare", "prompt": self.prompt.read_text(encoding="utf-8"),
            "size": "auto", "quality": "max", "output_format": "webp",
            "background": "transparent", "output_compression": "100",
        })
        self.assertEqual(files, [(name, path.name, "image/png", PNG)
                                 for name, path in zip(("image", "image", "mask"), paths)])

    def test_single_image_edit_without_mask(self):
        image = self.work / "original.png"
        image.write_bytes(PNG)
        self.assert_success(self.run_cli("--image", str(image)))
        fields, files = self.multipart_payload()
        self.assertEqual(fields, {
            "model": "gpt-image-2.5-flare", "prompt": self.prompt.read_text(encoding="utf-8"),
            "size": "1024x1536", "quality": "high",
        })
        self.assertEqual(files, [("image", "original.png", "image/png", PNG)])

    def test_explicit_edit_mode_and_mime_types(self):
        # Sentinel bytes verify transport only; the server validates image contents.
        for suffix, mime in ((".png", "image/png"), (".jpg", "image/jpeg"),
                             (".jpeg", "image/jpeg"), (".webp", "image/webp")):
            with self.subTest(suffix=suffix):
                image = self.work / ("original" + suffix)
                content = b"upload transport fixture: " + suffix.encode()
                image.write_bytes(content)
                self.assert_success(self.run_cli(
                    "--mode", "edit", "--image", str(image), "--quality", "xhigh",
                ))
                fields, files = self.multipart_payload()
                self.assertEqual(fields["model"], "gpt-image-2.5-flare")
                self.assertEqual(fields["quality"], "xhigh")
                self.assertEqual(files, [("image", image.name, mime, content)])

    def test_explicit_generate_mode(self):
        self.assert_success(self.run_cli("--mode", "generate"))
        self.assertEqual(self.json_payload()["model"], "gpt-image-2.5-flare")

    def test_missing_mask_and_directory_input(self):
        image = self.work / "original.png"
        image.write_bytes(PNG)
        for args in (("--image", str(image), "--mask", str(self.work / "missing.png")),
                     ("--image", str(self.work))):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Image file not found or not a regular file", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.requests, [])

    def test_invalid_options_fail_before_request(self):
        cases = [
            (["--mode", "edit"], "--mode edit requires"),
            (["--mode", "generate", "--image", "original.png"], "--mode generate cannot"),
            (["--mode", "generate", "--mask", "mask.png"], "--mode generate cannot"),
            (["--mask", "mask.png"], "--mask requires"),
            (["--background", "transparent", "--output-format", "jpeg"], "transparent backgrounds require"),
            (["--output-compression", "-1", "--output-format", "webp"], "between 0 and 100"),
            (["--output-compression", "101", "--output-format", "jpeg"], "between 0 and 100"),
            (["--output-compression", "90"], "requires --output-format"),
            (["--output-compression", "90", "--output-format", "png"], "requires --output-format"),
            (["--output-format", "gif"], "invalid choice"),
        ]
        for args, message in cases:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
        self.assertEqual(self.requests, [])
        self.assertFalse(self.output.exists())

    def test_missing_reference_fails_before_request(self):
        result = self.run_cli("--image", str(self.work / "missing.png"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Image file not found", result.stderr)
        self.assertEqual(self.requests, [])

    def test_missing_credentials(self):
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
            with self.subTest(name=name):
                original = self.env.pop(name)
                result = self.run_cli()
                self.env[name] = original
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name + " is missing", result.stderr)
        self.assertEqual(self.requests, [])

    def test_http_error_body(self):
        type(self).response_status = 400
        type(self).response_body = {"error": {"message": "Unsupported model"}}
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 400", result.stderr)
        self.assertIn("Unsupported model", result.stderr)
        self.assertFalse(self.output.exists())

    def test_error_inside_success_response(self):
        type(self).response_body = {"error": {"message": "请求被拒绝"}}
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP 200", result.stderr)
        self.assertIn("请求被拒绝", result.stderr)
        self.assertFalse(self.output.exists())

    def test_unexpected_response(self):
        type(self).response_body = {"data": []}
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unexpected response body", result.stderr)
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(shutil.which("zsh"), "wrapper requires zsh")
    def test_wrapper_runs_from_checkout_before_install(self):
        # Keep this independent of any model set in the user's launchctl env.
        self.env["OPENAI_IMAGE_MODEL"] = "gpt-image-2.5-flare"
        self.assert_success(self.run_cli("--quality", "xhigh", wrapper=True))
        self.assertEqual(self.json_payload()["model"], "gpt-image-2.5-flare")
        self.assertEqual(self.json_payload()["quality"], "xhigh")
        self.assertFalse((Path(self.env["CODEX_HOME"]) / "bin").exists())


    @unittest.skipUnless(shutil.which("zsh"), "wrapper requires zsh")
    def test_wrapper_image_edit(self):
        self.env["OPENAI_IMAGE_MODEL"] = "gpt-image-2.5-flare"
        image, mask = self.work / "original.png", self.work / "mask.png"
        image.write_bytes(PNG)
        mask.write_bytes(PNG)
        self.assert_success(self.run_cli(
            "--mode", "edit", "--image", str(image), "--mask", str(mask),
            "--output-format", "png", "--quality", "max", wrapper=True,
        ))
        fields, files = self.multipart_payload()
        self.assertEqual(fields["model"], "gpt-image-2.5-flare")
        self.assertEqual(fields["quality"], "max")
        self.assertEqual(fields["output_format"], "png")
        self.assertEqual([part[0] for part in files], ["image", "mask"])


if __name__ == "__main__":
    unittest.main()
