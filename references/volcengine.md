# Volcengine integration

## Capabilities

Match the capability and mode identified in the main workflow, then read the corresponding operation requirements. Detailed procedures are maintained in the [Chinese supplier reference](volcengine_cn.md#能力操作说明).

| Capability | operation | Modes | Models | Script support | Details |
|---|---|---|---|---|---|
| Text-to-image | `text-to-image` | — | Seedream 5.0 Pro, Flash | Implemented | [Text-to-image](volcengine_cn.md#文生图) |
| Image-to-image | `image-to-image` | Single-image editing, multi-image fusion, region editing | Seedream 5.0 Pro, Flash | Implemented | [Image-to-image](volcengine_cn.md#图生图) |
| Layer decomposition | `decompose-layers` | — | Seedream 5.0 Pro, Flash | Implemented | [Layer decomposition](volcengine_cn.md#图层拆分) |
| Text-to-video | `text-to-video` | — | Seedance 2.5, 2.0, 2.0 Fast, 2.0 Mini | Implemented | [Text-to-video](volcengine_cn.md#文生视频) |
| Image-to-video | `image-to-video` | First frame, first and last frames | The same four Seedance models | Implemented | [Image-to-video](volcengine_cn.md#图生视频) |
| Reference-to-video | `reference-to-video` | Reference generation, video editing | The same four Seedance models; audio-only references require 2.5 | Implemented | [Reference-to-video](volcengine_cn.md#参考生视频) |
| Video extension | `extend-video` | Extend before, extend after | The same four Seedance models | Implemented | [Video extension](volcengine_cn.md#视频延长) |

Model- and mode-specific asset requirements, parameters and limits remain in the relevant capability requirements.

## Cost calculation

The agent builds JSON from the capability/mode requirements; Python inspects the media, loads `models/volcengine-pricing.json`, resolves formula dependencies and calculates the estimate. Full dependency tables and annotated input examples are maintained in [cost calculation](volcengine_cn.md#预估成本).

| Formula group | Operations | Required task settings | Media |
|---|---|---|---|
| Ordinary images | `text-to-image`, `image-to-image` | `size` | None for text-to-image; 1–10 images for image-to-image |
| Layer decomposition | `decompose-layers` | `size` (tier or `auto`) | 1 image |
| Videos | `text-to-video`, `image-to-video`, `reference-to-video`, `extend-video` | `resolution`, `ratio`, `duration` | As required by the selected mode |

All requests require `provider`, `model` and one of the seven `operation` identifiers. Video capabilities with modes require top-level `mode`: image-to-video uses `first-frame|first-last-frame`; reference-to-video uses `reference|edit`; extend-video uses `before|after`. Image capabilities and text-to-video do not accept mode. Each `assets` item contains `kind`, an absolute path or HTTPS `source`, and optional asset identifier `id`. The identifier is preserved with measurements and does not affect billing. Do not supply prices, measured dimensions/durations, image counts, prompts or a price-file path. Python retains and validates audio assets even though audio duration is not added to video seconds. Text-only generation forbids assets; reference generation needs assets; 2.0 forbids audio-only reference; editing/extension needs a video.

```text
ordinary_image_cost = output_pixel_tier_price + max(input_images - 1, 0) * extra_image_price
layer_cost_range = [one low-tier layer price, 17 * high-tier layer price]
formula_tokens = ceil((sum(input_video_seconds) + output_seconds) * width * height * 24 / 1024)
billable_tokens = formula_tokens if no input video, else max(formula_tokens, minimum_billable_tokens)
video_cost = billable_tokens * price_per_million_tokens / 1_000_000
```

Fixed ratios use the model-specific official output-pixel table. For Volcengine 2.5 first/last-frame, editing and extension, an unambiguous source with a known table aspect ratio resolves adaptive pixels at the requested resolution; source pixels are not directly substituted for output pixels. Multiple editing/extension videos can use `estimate_context.target_asset_index` (zero-based in `assets`) to identify the estimate target, consistent with the prompt. Unmappable/model-selected dimensions require a justified `estimate_context.output_dimensions=[width,height]`; otherwise the result is `unknown` with `result.uncertainties`.

When input includes video, provide verified `estimate_context.minimum_billable_tokens` and `minimum_tokens_source` from the official table/calculator for the exact model/resolution/ratio/output-duration specification. A fixed duration accepts a positive number; automatic-duration intervals require a verified `[lower,upper]` floor range covering the interval. Without a verified floor, the result is only `lower_bound`, with no known upper amount. Never invent these values. See [official billing rules](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh) and [output-size/adaptive rules](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh).

Python measures input video durations. For 2.5 editing with `duration=-1`, use target duration minus 0.4 seconds through target duration; other automatic durations use the model's 4–30 or 4–15 second range. The saved quote and stdout contain identical JSON with `input`, `calculation` and `result`. Calculation inputs, measured assets, selected rates, assumptions and intermediate formula steps remain in `calculation` for auditing; `result` contains confirmation amounts and uncertainty reasons. Submission reuses the saved evidence; changed generation settings require re-estimation and confirmation.

## API contract

- Images: `POST /images/generations`. Process every `data` item, including error items and decomposition layers. `response_format=url|b64_json`. Preserve `usage` and per-layer `z_index`, `bounding_box`, `name`, `description`. PNG/JPEG outputs, layers always PNG.
- Video: `POST /contents/generations/tasks` returns `id`. Query `GET /contents/generations/tasks/{id}`; queued/running are nonterminal, succeeded/failed/expired/cancelled are terminal. Success media are in `content.video_url` and optional `content.last_frame_url`. Do not confuse API acceptance with generated media success. Report `usage.completion_tokens`/`total_tokens` as returned.
- Video input: text plus image_url/video_url/audio_url and explicit role. First-frame and first-last-frame are mutually exclusive with multimodal reference modes. Images/audio accept HTTPS, Base64 or asset://; video accepts HTTPS or asset:// only. Seedream image API accepts URL/Base64, not asset://.
- Local image/audio inputs are converted to Base64 in memory during submission; HTTPS URLs and existing Volcengine `asset://` IDs can also be used where the specific endpoint accepts them. The skill does not call Volcengine upload APIs or create asset IDs. Users must upload through the provider or approved storage separately, then provide the resulting asset ID or URL. Video inputs cannot be sent as Base64.
- Results generally have 24-hour URL retention. Download promptly and keep original bytes. Expired media cannot be fixed by re-querying indefinitely; check existing storage/provider recovery before proposing a newly charged generation. In sandboxed execution environments, run API network commands with escalation if outbound DNS/network is blocked; otherwise Python `urllib` can fail locally with `URLError` before receiving any HTTP response. Transport diagnostics should retain a sanitized underlying reason (for example, `gaierror`) without secrets.

## Model-specific limits

- 2.5: video-editing mode, extension and first/last-frame mode ratio must be adaptive. Edit duration must be -1; edit input videos 4..30 s. Other input video/audio 2..30 s; per-kind total duration <=30 s. 2.0 series input video/audio 2..15 s and per-kind total <=15 s. Counts are in the catalog. 2.0 cannot accept audio-only references.
- Video input images: width and height 300..6000; ratio 0.4..2.5; <30 MB. Video input pixel count 407696..8295044, dimensions 300..6000, ratio 0.4..2.5, FPS 24..60, <=200 MB each. Audio WAV/MP3 <=15 MB. Body <=64 MB. Inspect remote formats/dimensions before confirmation; local validation does not prove network preflight.
- Pro/Flash: reference images <=10, <=30 MB each, dimensions >14, ratio 1/16..16, total pixels <=36 million. Layer input PNG/JPEG, single image, pixels >=262144. Standard generation supports 1K/1.5K/2K or exact pixels with total 921600..4624220 and ratio 1/16..16. Decomposition supports tier/auto only.
- Pro/Flash standard generation: prefer the documented resolution tier (`1K`, `1.5K`, or `2K`) and describe the aspect ratio naturally in `prompt`; do not also send a `ratio` field. Common 1K mappings include 4:3 = 1152x864. Exact-pixel mode has a 921600-pixel minimum: 1024x768 is invalid (786432 pixels), while 1152x864 is valid. Do not derive dimensions by scaling a conventional 1024x768 canvas.
- Pro/Flash image generation returns one image per request; `sequential_image_generation`/`sequential_image_generation_options.max_images` are not supported. The `image` input count (up to 10 references) is separate from output quantity. Do not advertise a multi-image quantity option for one Pro/Flash request; do not send `n` or sequential group-output fields. These models also do not support stream or web_search.
- Seedream 5.0 Pro/Flash image request contract: required `model` (Pro: `doubao-seedream-5-0-pro-260628`; Flash: `doubao-seedream-5-0-flash-260915`) and `prompt`; optional `image` (URL or data URI/Base64; up to 10 reference images), `size`, `output_format`, `response_format`, `watermark`, `background`, `optimize_prompt_options`, and `layer_decomposition`.
- `size`: `1K`/`1.5K`/`2K` (default API value 2K), or exact `WxH` subject to 921600..4624220 total pixels and 1/16..16 aspect ratio. Prefer a tier and describe ratio in the prompt; do not send a separate ratio field. Common mapping: 1K 4:3 = 1152x864.
- `output_format`: `png` or `jpeg` (official API default `jpeg`; this skill explicitly defaults to `png`). `response_format`: `url` or `b64_json` (default `url`; URLs expire after 24 hours).
- `watermark`: boolean; official API default is `true`, but this skill explicitly sends `false` by default per user preference. Honor an explicit user choice.
- `background`: `opaque` or `transparent` (default `opaque`). Transparent output is restricted to editing one alpha-channel input and PNG output.
- `optimize_prompt_options.mode`: `standard` for Pro and Flash; `fast` is supported by Pro only. Server-side prompt optimization is distinct from the required sd25-pe workflow.
- `layer_decomposition`: boolean (default `false`); `true` enables layer decomposition and requires exactly one input image. Normal image generation keeps it false. Pro/Flash generate one output per request; do not send `n` or sequential-group fields.
- Example text-to-image payload (Flash; change only the model ID to use Pro):
  ```json
  {
    "model": "doubao-seedream-5-0-flash-260915",
    "prompt": "一只小猫趴在草地上，柔和自然光，摄影质感。画面比例为4:3。",
    "size": "1K",
    "output_format": "png",
    "response_format": "url",
    "watermark": false,
    "background": "opaque",
    "optimize_prompt_options": {"mode": "standard"},
    "layer_decomposition": false
  }
  ```
- The adapter does not expose seed/camera_fixed/frames (these are not supported for the chosen Seedance APIs), flex inference, draft workflows or video web_search. User-facing settings appear in the task confirmation; technical request details remain in task configuration and submission records. Unsupported options are rejected rather than ignored.

## Portrait provenance

The official guide offers trusted model originals, virtual portraits, or certified/authorized human assets. Do not assume direct arbitrary human-face upload works. Trusted originals must come from the same Ark account/platform within 30 days: specified Seedance original face-containing videos/tail frames or Seedream 5.0 Lite/Pro/Flash **text-to-image** face images. Editing/compression/forwarding may invalidate trust. The 30-day trust window is separate from the 24-hour download URL retention. A provenance record alone does not create authorization or guarantee provider acceptance. Licensed-IP input can add charges outside ordinary generation pricing; obtain a real quote before approval.

## Official sources

- [Seedance 2.5 tutorial](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)
- [Seedance 2.5 prompting](https://docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide?lang=zh)
- [Seedance 2.0 series tutorial](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=zh)
- [Seedance 2.0 prompting](https://docs.volcengine.com/docs/ark/seedance-2-0-prompt-guide?lang=zh)
- [Video generation tutorial and pixel mappings](https://docs.volcengine.com/docs/ark/video-generation-tutorial?lang=zh)
- [Create video task API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)
- [Query video task API](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh)
- [Portrait assets](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh)
- [Seedream Pro/Flash tutorial](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)
- [Interactive image editing](https://docs.volcengine.com/docs/ark/seedream-5-0-pro-editing-guide?lang=zh)
- [General image generation and model exceptions](https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh)
- [Image API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)
- [Model list](https://docs.volcengine.com/docs/ark/model-list?lang=zh)
