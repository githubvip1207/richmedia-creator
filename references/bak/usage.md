# CLI and request schema

Cost JSON contains task parameters and an optional `assets` array, each item containing `kind`, an absolute path or HTTPS URL `source`, and optional asset identifier `id`. Python counts images and uses `ffprobe` to inspect dimensions and video/audio duration; prices are loaded internally by `provider`. Do not supply rates, price files, `input_images` or `input_video_seconds`. The complete result is saved to cost.json and returned identically on stdout; the record has exactly three top-level fields: `input`, `calculation` and `result`. Inspection failures stop estimation; remote probing may use the network but never submits generation requests.

Conditional billing evidence belongs in `estimate_context`: `target_asset_index` identifies an editing/extension target among multiple videos; justified `output_dimensions` resolves otherwise unknown output pixels; `minimum_billable_tokens` and `minimum_tokens_source` supply the verified input-video billing floor. These are not prices or measured source metadata. Follow the supplier cost rules; inspect `result.uncertainties` instead of treating a lower bound as a total.

Use `cost.json` to audit the calculation:

- `input` preserves the original JSON, including asset IDs, sources, settings and evidence.
- `calculation` contains normalized supplier/model/operation settings, counts and individual durations; `assets` with IDs, sources and measured dimensions/durations; selected rates, source, verification date and billing rules; estimate timestamp, schema version, evidence and FX. Images record pixel tiers, extra-input charges, output count and unit-price ranges. Videos record assumed output dimensions and their basis, duration range, FPS, formula tokens, minimum tokens and final billable tokens. `steps` records formulas and intermediate values, and `notes` preserves assumptions and limitations. Money is rounded to six decimal places. Only relevant rates are recorded, rather than the complete supplier catalog.
- `result` contains confirmation fields: `status`, `currency`, `amount: {min,max}` and `uncertainties: [{field,reason}]`. Valid FX adds `conversion`. A null amount means unknown, never zero.

Audit measured sources, reconstruct each formula using the recorded rates and `steps`, and compare against `result.amount`. Submission reuses saved costs and evidence without recalculation; changed settings require re-estimation and confirmation.



Calculate using JSON on stdin: `media.py estimate-cost --workdir <workdir>`, once per supplier. Output is `<workdir>/<supplier>/cost.json`. Read the saved costs to write the confirmation sheet; submit reads the selected supplier cost directly. See [cost rules](volcengine.md#cost-calculation).


Set `SKILL` to the installed directory (normally `~/.codex/skills/richmedia-creator`). The examples use Python 3.9+. Use init to create a private working directory `/tmp/richmedia-YYYYMMDDHHmmss/` using the system local clock; existing names are skipped. Put every request, cost, state file, response, manifest and intermediate download beneath it. Keep the CLI working directory at the project for `.env` loading. Only final media (plus placement metadata for layer decomposition) belongs in the user-selected output directory, defaulting to the current project directory. Never create process directories in the project or installed skill.

When run from the project directory, the CLI reads only `VOLCENGINE_API_KEY`, `BYTEPLUS_API_KEY`, `USD_CNY`, and `USD_CNY_EXPIRES_AT` from project `.env`. Assignments are parsed as data without executing the file or printing keys. Business configuration does not fall back to process environment variables. Other `.env` keys are ignored.

```bash
python3 "$SKILL/scripts/media.py" init < /absolute/path/requirements.json
python3 "$SKILL/scripts/media.py" check
python3 "$SKILL/scripts/media.py" doctor
python3 "$SKILL/scripts/media.py" doctor --dependencies
python3 "$SKILL/scripts/media.py" doctor --exchange-rate
python3 "$SKILL/scripts/media.py" models --provider volcengine
python3 "$SKILL/scripts/media.py" models --provider byteplus
python3 "$SKILL/scripts/media.py" estimate-cost --workdir /tmp/richmedia-20261021105342 <<'JSON'
{
  "provider": "volcengine",
  "model": "seedream-5.0-flash",
  "operation": "text-to-image",
  "size": "1K"
}
JSON
```

## Run directory and requirement records

Run `python3 "$SKILL/scripts/media.py" init` with an agent-authored JSON object on stdin, using a quoted heredoc or input-file redirection. The content is not a command-line argument. Init uses the system local clock and atomically creates a mode-0700 directory and writes a mode-0600 request.json file `/tmp/richmedia-YYYYMMDDHHmmss`; an existing file, directory or symlink is never reused or overwritten, and collisions use a new timestamp. It returns only `{"workdir":"/tmp/richmedia-YYYYMMDDHHmmss"}`. Reuse workdir as WORK while keeping the CLI working directory at the project. Init validates JSON syntax and its object root before creating the directory, then saves the supplied UTF-8 text unchanged to `<workdir>/request.json`. Empty or invalid input fails without a directory; failed writes clean up the incomplete run.

The agent supplies requirement content to init through stdin: the verbatim original prompt, resolved intent, candidate suppliers with their own models/operations/parameters, and assets with paths, purposes, roles and measured metadata/provenance when relevant. Group supplier-specific parameters and assets separately, and group them by supplier when presenting them. Ask about unresolved information; do not invent observations, credentials or Base64 bodies. Init validates JSON syntax and the object root and writes the record; it does not infer content, validate business fields, access the network or install software.

Use the annotated [initialization example](../SKILL_cn.md#3-准备运行环境) as the requirement-record schema. `intent` contains only `operation`; do not add `intent.mode`, `intent.description` or a supplier-level mode. Top-level `assets` contains the complete `id`, `kind`, `source` and `purpose` records. Each supplier's `assets` contains only `{"id":"<top-level asset id>"}` references, in input order, without duplicating fields. Resolve these ids to their top-level assets when constructing the supplier's executable request.

The requirement record is not an API payload or direct submit input. Derive a separate task-spec.json or <provider>-task-spec.json using the CLI schema below. Preserve original requirements. No separate plan file is needed.

## Checks and repairs

| Command | Behavior |
|---|---|
| `check` | Read-only checks of project `.env`, configured suppliers, exchange-rate status, the sd25-pe file, and ffprobe availability |
| `doctor` | Install missing dependencies, refresh missing/invalid/expired exchange rates, then recheck |
| `doctor --dependencies` | Repair missing dependencies only, then recheck |
| `doctor --exchange-rate` | Force-refresh the exchange rate in `.env`, then recheck |

`check` does not access the network, install software, modify files, or validate live keys, model access, balances, or quotas. Missing API keys require local user configuration; repairs cannot acquire keys. Default supplier choices include only suppliers with configured keys.

`doctor` installs sd25-pe from the official Ark skills catalog and reports failure if npx is unavailable. For missing ffprobe, it runs `brew install ffmpeg`; without Homebrew, it asks for FFmpeg installation through the system package manager. Installation is followed by a fresh check. Installer output is not echoed directly. Repair failures are reported; stop tasks whose required dependencies remain unavailable.

Exchange rates use the fixed [Frankfurter ECB USD/CNY endpoint](https://api.frankfurter.dev/v2/providers/ecb/rate/usd/cny), without an API key. Validate the currency pair, finite positive rate, and observation date. Expiration is seven days after the observation date at UTC midnight, not seven days after download of potentially old data. Update only `USD_CNY` and `USD_CNY_EXPIRES_AT` in `.env`, preserving other configuration, comments, and line endings. On failure, preserve existing values without switching sources or inventing rates.

`USD_CNY_EXPIRES_AT` is timezone-aware ISO 8601, for example `2026-10-28T00:00:00+00:00`. Missing, invalid, or expired rates result in native-currency quotes in ordinary planning/comparison; repair the rate before applying a budget requiring conversion. Legacy `ARK_API_KEY`, `USD_CNY_VERIFIED_ON`, and `USD_CNY_SOURCE` are no longer read as configuration. Re-estimate and reconfirm to use an updated .env rate.

Executable task-spec.json schema (strict JSON; no credentials or Base64):

```json
{
  "provider": "volcengine",
  "model": "seedance-2.5",
  "operation": "text-to-video",
  "original_prompt": "一只熊猫在草坡上打滚",
  "prompt": "写实自然风格，熊猫幼崽在绿色草坡上笨拙地侧滚，最后趴在草地上。低机位中景，镜头轻微跟随。",
  "optimizer": {"skill": "sd25-pe", "status": "applied"},
  "parameters": {"ratio": "16:9"},
  "assets": []
}
```

For image tasks, choose `parameters.ratio` before preparing (21:9, 16:9, 3:2, 4:3, 1:1, 3:4, 2:3, or 9:16). The adapter adds it as prompt composition guidance; it is not a guaranteed exact pixel ratio. The lowest image-size default is `1K`; each paid plan represents one output request.

When producing cURL for a prepared request, compile the task configuration with `compile_request` and copy its `payload_template` and compiled prompt exactly; after submission use `execution.compiled` in submit-NNN.json. Do not translate `1K` plus a ratio into assumed pixel dimensions or alter fields such as `output_format` and `watermark`. For Seedream 5.0 Pro/Flash, exact dimensions must meet the official 921600..4624220 total-pixel range and 1/16..16 aspect-ratio range; for example, 1024x768 is below the minimum, while 1152x864 is a valid 4:3 1K reference mapping. These models return one generated image per request; they do not support `n` or sequential group output. Raw `curl` does not read project `.env` by itself; read the selected key from project `.env` using a safe data-only loader when constructing a cURL example. Never `source` the `.env` file or print its secret value.

The agent actually applies sd25-pe before writing the final `prompt`. Omitted creation/editing settings resolve to the low-cost policy. The example is a schema example, not proof that optimization or human approval occurred.

The submitted task configuration must explicitly name the user-selected provider, with a model ID belonging to it. Keep supplier configurations separate and submit only the selected one.

Aliases: `seedance-2.5`, `seedance-2.0`, `seedance-2.0-fast`, `seedance-2.0-mini`, `seedream-5.0-pro`, `seedream-5.0-flash`. Exact catalog version IDs are also accepted.

Operations:

| operation | mode | 素材 / Assets |
|---|---|---|
| `text-to-image` | — | 无 / None |
| `image-to-image` | — | 1～10 张图片 / 1–10 images |
| `decompose-layers` | — | 1 张图片 / 1 image |
| `text-to-video` | — | 无 / None |
| `image-to-video` | `first-frame`、`first-last-frame` | 首帧 1 张、首尾帧按顺序 2 张 / 1 first frame or 2 ordered frames |
| `reference-to-video` | `reference`、`edit` | 必须有参考素材；编辑必须有视频 / References required; editing needs video |
| `extend-video` | `before`、`after` | 必须有视频 / Video required |

Assets preserve order within each kind. Each entry:

```json
{
  "kind": "video",
  "source": "https://your-approved-storage.example/reference.mp4",
  "role": "reference_video",
  "purpose": "参考动作和运镜；不采用原视频人物外观",
  "metadata": {"duration": 8.0, "width": 1280, "height": 720, "bytes": 12000000},
  "provenance": {"provider": "volcengine", "account_profile": "my-ark-profile", "generated_at": "2026-10-21T10:00:00+08:00", "original": true}
}
```

`source` accepts absolute local image/audio paths (converted in memory to Base64 only during submission), HTTPS URLs and existing provider-scoped `asset://` IDs. The skill supports the Base64 input path for local images/audio. It does **not** implement either supplier's upload API or create `asset://` IDs; upload media separately through the target supplier or approved storage, then re-plan with that URL or supplier-owned asset ID. **Video inputs do not support Base64** for these task APIs. The skill never silently uploads to public storage. An asset ID is not a prompt reference: use 图片1/视频1/音频1.

Local files get SHA256 and ffprobe metadata when available; `ffprobe` is optional and is not installed automatically. Remote metadata must come from inspection or user-supplied measured facts. Do not invent durations/dimensions. Image transparency needs `metadata.has_alpha=true` verified from the actual input. Remote URLs/IDs are not byte-pinned by this CLI; if their content changes, inspect and reconfirm. Local paths containing video are rejected before network calls.

After showing the `任务确认单` and **receiving the user's current supplier selection and confirmation**:

```bash
python3 "$SKILL/scripts/media.py" submit --workdir /tmp/richmedia-20261021105342 \
  --request /tmp/richmedia-20261021105342/task-spec.json --approval-text '<actual user confirmation>'
python3 "$SKILL/scripts/media.py" status --submission /tmp/richmedia-20261021105342/submit-001.json --wait 45
python3 "$SKILL/scripts/media.py" download --submission /tmp/richmedia-20261021105342/submit-001.json
```

Use `--accept-uncertain-cost` only if the user explicitly accepted an unknown cost upper bound. CLI arguments are audit records, not a substitute for a real user reply. Do not run submit examples literally or create your own approval.

`attach-task --submission <submit-NNN.json> --task-id ...` attaches an independently reconciled existing video task after ambiguous submission; it verifies ID/model but cannot prove this task corresponds to the exact prompt, so independently verify creation time/materials in the console. It performs no paid generation. Keep `request.json`, optional task-spec.json, supplier cost.json files, `submit-NNN.json` and `outputs/` together under the temporary working directory. After download, copy only completed media to descriptive, non-conflicting filenames in the final output directory without changing their bytes; leave manifests and other process files in `/tmp`. For layer decomposition, also deliver placement metadata. Retain temporary recovery state on failure or unknown submission outcome; `/tmp` may be cleared by the system, and missing state does not authorize another paid request. Raw responses can include temporary signed result URLs: do not paste them or Base64 into chat logs. Use final local file links.

For region editing, convert image-local pixel coordinates with `round(pixel / displayed_image_dimension * 1000)`, clamped to 0..999; first subtract canvas offsets/scale. Use `<point>x y</point>` or `<bbox>x1 y1 x2 y2</bbox>` in the prompt. No interactive canvas is bundled.

For new providers: add reviewed model capabilities and pricing, a transport adapter under `scripts/providers/`, operation compilation/routing and meaningful mocked integration tests. Keep user-visible confirmation and single-submit persistence shared. Do not assume another provider shares Ark endpoints, role names, billing or async statuses.

## Supplier quotes and selection

Run estimate-cost separately for each supplier; results remain in `<workdir>/<provider>/cost.json`. Read these costs and the supplier task configurations to compose the confirmation sheet directly. Verify each supplier's model, asset provenance, pricing and FX independently. Do not rank unlike currencies without valid conversion.

After the user selects and confirms one offer, pass the task JSON on stdin to `submit` (or use `--request` for file input). It returns `{"submission":"/absolute/path/submit-001.json"}`. This record preserves the input, with the original POST response in `response`, execution/recovery state in `execution`, each status request/response in `queries`, and the download manifest in `result`. Use `status|download|attach-task --submission <record-path>` for any specific submission, including historical ones. A new confirmation after a known terminal outcome permits a new numbered submission in the same workdir. Media is saved under `outputs/submit-NNN/`; no separate state, response or manifest JSON files are created.

Media URL downloads use Python urllib with a 120-second socket timeout, 64 KiB reads and up to three attempts (2/4-second backoff) for transport errors, incomplete transfers and HTTP 408/429/500/502/503/504. Each attempt restarts the temporary file; no Range resume is implemented. Other HTTP errors stop immediately. These retries apply only to media GETs, never paid generation POSTs.

For persistent Codex execution rules, invoke the installed CLI directly as `python3 /Users/chenyu/.codex/skills/richmedia-creator/scripts/media.py submit|status|download ...` (one actual subcommand per call), without shell wrappers or inline Python. A matching allow rule can avoid repeated execution prompts after rules are loaded; managed restrictions still apply. Execution authorization never replaces the current task confirmation or supplier selection required for a paid POST.
