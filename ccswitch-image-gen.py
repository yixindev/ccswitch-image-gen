#!/usr/bin/env python3
import argparse
import base64
import mimetypes
import os
import secrets
from pathlib import Path
import json
import urllib.error
import urllib.request


DEFAULT_MODEL = "gpt-image-2.5-flare"


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36"


def _read_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _require_env() -> tuple[str, str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is missing")
    if not base_url:
        raise SystemExit("OPENAI_BASE_URL is missing")
    return api_key, base_url.rstrip("/")


def _decode_first_image(result: dict, output: str) -> None:
    try:
        image_b64 = result["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as error:
        raise SystemExit("Unexpected response body: " + _format_json(result)) from error
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(image_b64))
    print(output_path)


def _request_json(url: str, api_key: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    return _open_json(request)


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _multipart_body(fields: list[tuple[str, str]], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = "----ccswitch-imagegen-" + secrets.token_hex(16)
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")

    for name, path in files:
        if not path.is_file():
            raise SystemExit(f"Image file not found or not a regular file: {path}")
        try:
            image_bytes = path.read_bytes()
        except OSError as error:
            raise SystemExit(f"Cannot read image file {path}: {error}") from error
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {_guess_mime(path)}\r\n\r\n".encode())
        chunks.append(image_bytes)
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def _request_multipart(url: str, api_key: str, fields: list[tuple[str, str]], files: list[tuple[str, Path]]) -> dict:
    body, boundary = _multipart_body(fields, files)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    return _open_json(request)


def _format_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _open_json(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
            if isinstance(result, dict) and "error" in result:
                raise SystemExit(f"HTTP {response.status}: " + _format_json(result))
            return result
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {error.code}: {body}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--mode",
        choices=("auto", "generate", "edit"),
        default="auto",
        help="Request mode (default: auto). Auto uses /images/edits when --image is provided; otherwise /images/generations.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_IMAGE_MODEL") or DEFAULT_MODEL,
        help=f"Image model (default: OPENAI_IMAGE_MODEL or {DEFAULT_MODEL}).",
    )
    parser.add_argument("--size", default="1024x1536")
    parser.add_argument(
        "--quality",
        default="high",
        help="Image quality (default: high). GPT Image 2.5 supports low, medium, high, xhigh, max, auto.",
    )
    parser.add_argument(
        "--output-format",
        choices=("png", "jpeg", "webp"),
        help="Output encoding. When omitted, uses the provider default (OpenToken: png).",
    )
    parser.add_argument(
        "--background",
        choices=("auto", "opaque", "transparent"),
        help="Background mode. Transparent backgrounds require png or webp output.",
    )
    parser.add_argument(
        "--output-compression",
        type=int,
        help="Compression level from 0 to 100; requires --output-format jpeg or webp.",
    )
    parser.add_argument(
        "--image",
        action="append",
        help="PNG/JPEG/WEBP input/reference image. Uses /images/edits. Repeat only if the provider supports multiple images.",
    )
    parser.add_argument(
        "--mask",
        help="Optional PNG mask with an alpha channel and the same dimensions as the original image. Transparent areas are edited.",
    )
    args = parser.parse_args()
    if args.mode == "edit" and not args.image:
        parser.error("--mode edit requires at least one --image")
    if args.mode == "generate" and (args.image or args.mask):
        parser.error("--mode generate cannot be used with --image or --mask; use --mode edit or auto")
    if args.mask and not args.image:
        parser.error("--mask requires at least one --image")
    if args.background == "transparent" and args.output_format == "jpeg":
        parser.error("transparent backgrounds require --output-format png or webp")
    if args.output_compression is not None:
        if not 0 <= args.output_compression <= 100:
            parser.error("--output-compression must be between 0 and 100")
        if args.output_format not in ("jpeg", "webp"):
            parser.error("--output-compression requires --output-format jpeg or webp")

    api_key, base_url = _require_env()
    prompt = _read_prompt(args.prompt_file)

    # Both endpoints accept the same generation options. Only send optional
    # fields when requested so existing relay providers remain compatible.
    payload = {
        "model": args.model,
        "prompt": prompt,
        "size": args.size,
        "quality": args.quality,
    }
    for name in ("output_format", "background", "output_compression"):
        value = getattr(args, name)
        if value is not None:
            payload[name] = value

    if args.image:
        fields = [(name, str(value)) for name, value in payload.items()]
        files = [("image", Path(path)) for path in args.image]
        if args.mask:
            files.append(("mask", Path(args.mask)))
        result = _request_multipart(base_url + "/images/edits", api_key, fields, files)
    else:
        result = _request_json(
            base_url + "/images/generations",
            api_key,
            payload,
        )

    _decode_first_image(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
