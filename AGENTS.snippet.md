## Official / Relay Image Generation Routing

When the user asks Codex to generate or edit an image, first detect whether the current Codex provider is official OpenAI or a third-party relay.

Detection:

1. If `~/.cc-switch/cc-switch.db` exists, prefer the current Codex provider recorded by CCSwitch.
2. If the current CCSwitch Codex provider is official, treat it as official mode.
3. If the current CCSwitch Codex provider is non-official, treat it as relay mode.
4. If CCSwitch data is unavailable, read `~/.codex/config.toml`.
5. If root `model_provider` points to a custom provider and that provider has a non-official `base_url`, treat it as relay mode.
6. If `model_provider` is missing, `openai`, or the active provider is the official OpenAI endpoint, treat it as official mode.

Relay mode:

The default relay image model is `gpt-image-2.5-flare`. If the user explicitly requests another model, pass that model with `--model` instead. GPT Image 2.5 also supports `--quality xhigh` and `--quality max`.

1. Use the raw HTTP fallback command instead of assuming the OpenAI SDK works with the relay image endpoint.
2. Write long or non-ASCII prompts to a prompt file and call:

```bash
~/.codex/bin/ccswitch-imagegen \
  --prompt-file <prompt.txt> \
  --output <output.png> \
  --model gpt-image-2.5-flare \
  --size 1024x1536 \
  --quality high
```

3. Save final deliverables under the current workspace `outputs/` directory.
4. Do not ask the user to paste API keys in chat.

Official mode:

Use the normal built-in `image_gen` path.


## Relay Image Edit

If the user supplies an original/reference image or requests image editing, upload the actual local image using the multipart `/images/edits` endpoint:

```bash
~/.codex/bin/ccswitch-imagegen \
  --mode edit \
  --prompt-file <edit-prompt.txt> \
  --image <input.png> \
  --output <outputs/edited.png> \
  --model gpt-image-2.5-flare \
  --size auto \
  --quality high
```

- `--image` supports PNG/JPEG/WEBP. Never substitute an image pathname in the prompt for uploading the file.
- For whole-image edits, omit `--mask`.
- For local edits, add `--mask <mask.png>`. The mask must be a PNG with an alpha channel and the same dimensions as the original; transparent areas are edited. `--size` controls output dimensions, not mask dimensions.
- Repeat `--image` only when the relay supports multiple references. OpenToken's cited Image Edit documentation explicitly demonstrates single-image edits.
- Existing commands without `--mode edit` remain valid: supplying `--image` automatically selects editing.
- Honor an explicitly requested model; do not overwrite the original image unless the user asks to.
