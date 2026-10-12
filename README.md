# CCSwitch ImageGen Fallback

Codex App 使用第三方中转 provider 时的图片生成 fallback。

官方 provider 仍走 Codex 内置 `image_gen`；第三方中转 provider 走本工具，用 raw HTTP 调图片接口，绕过部分中转站对 SDK 图片请求的拦截。

## 你可能是因为这些问题找到这里

- Codex App 聊天已经切到第三方中转，但生图还是失败。
- 直接调用 Codex 内置 `image_gen` 时遇到 `Your request was blocked`。
- 中转站文字模型可用，但图片生成、图生图或 mask 编辑不稳定。
- `OPENAI_BASE_URL`、`OPENAI_API_KEY`、`gpt-image-2` 配好后，OpenAI SDK 仍然不能正常生图。
- 想让 Codex 自动判断官方 provider / 第三方中转 provider，不想每次手动说明“走中转”。

## 安装

先克隆源码（已有本地仓库时可跳过）：

```bash
git clone https://github.com/yixindev/ccswitch-image-gen.git
cd ccswitch-image-gen
```

可先在仓库内运行 `./ccswitch-imagegen --help`，确认参数后再安装：

```bash
mkdir -p ~/.codex/bin
cp ccswitch-imagegen ~/.codex/bin/ccswitch-imagegen
cp ccswitch-image-gen.py ~/.codex/bin/ccswitch-image-gen.py
chmod +x ~/.codex/bin/ccswitch-imagegen ~/.codex/bin/ccswitch-image-gen.py
```

把 `AGENTS.snippet.md` 追加到：

```text
~/.codex/AGENTS.md
```

检查是否安装成功：

```bash
~/.codex/bin/ccswitch-imagegen --help
```

## 配置

如果你用 CCSwitch App 管理 Codex provider，通常不用额外配置。脚本会读取当前 Codex provider 的 key 和 `base_url`。

不用 CCSwitch 时，手动设置：

```bash
export OPENAI_API_KEY="你的中转站 key"
export OPENAI_BASE_URL="https://你的中转站域名/v1"
```

如果要让 Codex App 这类 macOS GUI 应用也读到：

```bash
launchctl setenv OPENAI_API_KEY "你的中转站 key"
launchctl setenv OPENAI_BASE_URL "https://你的中转站域名/v1"
```

不要把 API key 发到聊天里。

## 安全行为

API key 和接口地址必须来自同一配置来源，并作为完整的一对使用。启动脚本按以下优先级选择：

1. 当前进程的 `OPENAI_API_KEY` + `OPENAI_BASE_URL`
2. macOS `launchctl` 中的 `OPENAI_API_KEY` + `OPENAI_BASE_URL`
3. CCSwitch 当前 Codex provider 的 key + 接口地址
4. Codex `config.toml` 根级 `model_provider` 对应的 `experimental_bearer_token` + `base_url`

如果环境变量或 `launchctl` 只设置了一项，工具会报错，不会从其他来源补齐。CCSwitch 当前 provider 的凭证不完整、数据库无法解析或当前选中了官方 provider 时，也不会继续尝试其他 provider；仅在 CCSwitch 数据源不存在或没有当前 Codex provider 时，才尝试 Codex 配置文件。CCSwitch 的 provider 和接口地址会在同一个只读数据库事务中读取。

**图片请求不跟随 HTTP 重定向**，包括同源重定向，防止 Bearer key 被转发到其他地址。遇到 `HTTP 301/302/303/307/308: Redirects are disabled` 时，应核对并直接配置受信任的最终 API 地址，不要关闭保护。

本次保护不包括强制 HTTPS、文件大小限制和输出文件防覆盖；请继续使用 HTTPS 接口，并选择可信的中转服务。

## OpenToken / GPT Image 2.5

默认图片模型为 `gpt-image-2.5-flare`。根据 [OpenToken 图片生成文档](https://docs.opentoken.io/api/openai/image-generation) 和 [图片编辑文档](https://docs.opentoken.io/api/openai/image-edit)，它仍使用 OpenAI 兼容的 `/v1/images/generations`（JSON）与 `/v1/images/edits`（multipart）接口，返回 `data[0].b64_json`。无需改用聊天接口。

使用 OpenToken 时，显式配置图片接口的凭证和地址（优先于 CCSwitch / Codex 配置）：

```bash
export OPENAI_API_KEY="你的 OpenToken key"
export OPENAI_BASE_URL="https://cn2.gw.opentoken.io/v1"
export OPENAI_IMAGE_MODEL="gpt-image-2.5-flare"  # 可省略，已是默认值
```

OpenToken 文档里的 `OPEN_TOKEN_KEY` 对应本工具的 `OPENAI_API_KEY`；如果已经设置前者，可用 `export OPENAI_API_KEY="$OPEN_TOKEN_KEY"`。

模型选择优先级：`--model` > `OPENAI_IMAGE_MODEL` > `gpt-image-2.5-flare`。macOS GUI 可用 `launchctl setenv OPENAI_IMAGE_MODEL "gpt-image-2.5-flare"` 配置模型。仍可通过 `--model gpt-image-2` 使用旧模型，或通过 `--model gpt-image-2.5-sunburst` 使用另一个 2.5 模型，前提是你的中转服务支持。

| 参数 | 说明 |
| --- | --- |
| `--mode` | 默认 `auto`：有 `--image` 时编辑，否则生成；也可显式指定 `edit` 或 `generate` |
| `--quality` | 默认 `high`；2.5 支持 `low` / `medium` / `high` / `xhigh` / `max` / `auto` |
| `--size` | 默认 `1024x1536`；可传 `auto`、`1024x1024`、`1536x1024`、`2048x2048`、`2048x1152`、`3840x2160`、`2160x3840` 等 |
| `--output-format` | `png` / `jpeg` / `webp`；不传时由服务端决定，OpenToken 默认为 PNG |
| `--background` | `auto` / `opaque` / `transparent`；透明背景需要 PNG 或 WEBP |
| `--output-compression` | 0–100，必须同时指定 `--output-format jpeg` 或 `webp` |

自定义尺寸仍须满足 OpenToken 的限制：宽高为 16 的倍数、单边不超过 3840、长短边比不超过 3:1、总像素在 655,360–8,294,400 之间。脚本保留原样传递模型名、尺寸和质量的行为，不对其他中转服务强制套用 OpenToken 的限制。

工具每次保存第一张图片，不提供多张输出的 `n` 参数。输出文件扩展名不会自动决定编码；使用 JPEG/WEBP 时请让 `--output` 扩展名与 `--output-format` 一致。新增的格式、背景、压缩字段只在明确指定时发送，避免影响旧中转站。

## 在 Codex App 里用

配置好后，直接正常说生图需求即可：

```text
生成一张公众号封面图，主题是 AI 工具效率提升
```

Codex 会自动判断当前 provider：

- 官方：内置 `image_gen`
- 中转：`ccswitch-imagegen`

## 终端用法

文本生成图片：

```bash
cat > prompt.txt <<'EOF'
生成一张竖版中文科技海报。
主标题：中转站生图成功
风格：高级、干净、专业。
不要水印，不要乱码。
EOF

~/.codex/bin/ccswitch-imagegen \
  --prompt-file prompt.txt \
  --output output.png \
  --model gpt-image-2.5-flare \
  --size 1024x1536 \
  --quality high
```

### Image Edit：根据原图编辑

传入 `--image` 会自动调用 `/v1/images/edits`，也可以用 `--mode edit` 显式选择编辑模式。原图以 multipart 的 `image` 文件字段上传，不会把文件路径当作提示词或改用聊天接口。原图支持 PNG、JPEG、WEBP；不需要局部遮罩时，省略 `--mask` 即可。

```bash
cat > edit-prompt.txt <<'EOF'
在原图天空中添加一道彩虹，保留原有建筑、人物和构图。
EOF
```

单图编辑（不带 mask）：

```bash
~/.codex/bin/ccswitch-imagegen \
  --mode edit \
  --prompt-file edit-prompt.txt \
  --image input.png \
  --output edited.png \
  --model gpt-image-2.5-flare \
  --size 1024x1536 \
  --quality high
```

局部编辑（带 mask）：

```bash
~/.codex/bin/ccswitch-imagegen \
  --mode edit \
  --prompt-file edit-prompt.txt \
  --image input.png \
  --mask mask.png \
  --output outputs/edited-region.png \
  --model gpt-image-2.5-flare \
  --size auto \
  --quality max \
  --output-format png
```

`mask.png` 必须是**带透明通道、与原图尺寸相同的 PNG**，透明区域表示需要编辑的部分。`--size` 是输出尺寸，不是 mask 尺寸。脚本检查文件存在且可读、mask 必须伴随原图；图片内容、透明通道和尺寸约束由服务端校验。

旧命令无需改动：省略 `--mode` 时仍会自动识别编辑请求。`--mode edit` 没有原图、或 `--mode generate` 搭配原图/mask，会在发送请求前报错，避免误走生成接口。编辑请求同样支持输出格式、背景和压缩参数，并将响应中的 `data[0].b64_json` 保存到 `--output`。

更高质量的透明背景 WEBP（生成和编辑均支持这些参数）：

```bash
~/.codex/bin/ccswitch-imagegen \
  --prompt-file prompt.txt \
  --output output.webp \
  --model gpt-image-2.5-flare \
  --size 1024x1024 \
  --quality xhigh \
  --background transparent \
  --output-format webp \
  --output-compression 90
```

多张参考图可以重复传 `--image`，工具会上传多个同名 `image` 文件字段。OpenToken 该文档明确展示的是单图编辑，多图是否被接受需由中转服务确认；使用 mask 时建议按文档采用单张原图。

中文、长提示词、包含标点或换行的提示词，建议始终写进 `--prompt-file`。

## 本地测试

```bash
python3 -m unittest discover -s tests -v
zsh -n ccswitch-imagegen
```

测试只使用本地模拟 HTTP 服务、临时配置和模拟 `launchctl`，不读取真实 GUI 凭证，不需要真实 API key，不调用 OpenToken，不产生生图费用。覆盖默认/指定模型、环境变量优先级、JSON 生成、自动/显式编辑模式、单图无 mask、PNG/JPEG/WEBP 文件字段、多参考图与 mask 编辑、2.5 质量档位、格式/背景/压缩、错误处理和仓库启动脚本的生成/编辑入口。安全回归测试还覆盖生成/编辑重定向拦截、配置来源优先级、不完整凭证拒绝、官方 provider 与损坏数据库的安全停止，以及非活动 profile 不得选择凭证。

## 出问题时

先看命令输出里的 HTTP 状态和错误正文。

常见原因：

- API key 或 `base_url` 没配好
- 中转站不支持 `/images/edits`
- 中转站不支持多图或 mask
- 图片过大、格式不支持，或模型名不支持图片输入

这个工具不替代 CCSwitch，也不替代官方 `image_gen`。它只负责第三方中转模式下的图片生成 fallback。
