---
name: richmedia-creator
description: Generate and edit images and videos. Image capabilities include text-to-image generation, reference-based creation, multi-image fusion, region editing, and layer decomposition; video capabilities include text-to-video generation, image-to-video generation, first/last-frame control, multimodal image/video/audio references, content editing, and duration extension. Use for visual creation and media asset production.
---

# 富媒体生成器 · RichMedia Creator

This skill integrates image and video processing capabilities from multiple suppliers. It generates or edits images and videos based on user requirements, with a unified workflow for prompt optimization, parameter configuration, supplier selection, cost estimation, and delivery of generated results. Each supplier’s credentials, models, prices, assets, and jobs are managed independently.

## Pre-run checks

Run `python3 <skill-dir>/scripts/media.py check` for read-only checks. Use `doctor` to repair detected issues, `doctor --dependencies` for dependencies only, or `doctor --exchange-rate` to refresh the rate in `.env`.

### Configuration checks

Read configuration from the `.env` file in the current project directory.

| Setting | Purpose |
|---|---|
| `VOLCENGINE_API_KEY` | API key required when using Volcengine |
| `BYTEPLUS_API_KEY` | API key required when using BytePlus |
| `USD_CNY` | USD-to-CNY exchange rate, expressed as CNY per USD |
| `USD_CNY_EXPIRES_AT` | Exchange rate expiration time |

Check that the selected supplier's API key is configured. When currency conversion is needed, check that the exchange rate configuration is complete and has not expired. The script manages the exchange rate source internally; users do not need to configure it.

If required configuration is missing, ask the user to supply it locally. If the exchange rate is missing or expired, update it first or show only native-currency quotes. Never expose API keys in chat, logs, or task files.

### Dependency checks

Check that the scripts, helper tools, and prompt-optimization skills required for the current task are available. Install missing dependencies according to the relevant references, then check again. If they remain unavailable, explain why and stop the affected operation.

### Input checks

Check that input assets exist and are readable, and that their formats, dimensions, durations, and task parameters meet the applicable requirements. Identify any information or adjustments needed when they do not.

## Setup

1. Resolve this skill's directory and run `python3 <skill-dir>/scripts/media.py check` from the current project directory. Business configuration is read from project `.env`: `VOLCENGINE_API_KEY`, `BYTEPLUS_API_KEY`, `USD_CNY`, and `USD_CNY_EXPIRES_AT`. Configure missing supplier keys locally; never request them in chat or write them to logs, requests, or skill files. The command checks configuration and dependency presence, not live credentials, model permissions, balances, or quotas.
2. Use `doctor` to repair detected issues, `doctor --dependencies` to install missing sd25-pe/ffprobe dependencies, or `doctor --exchange-rate` to refresh the exchange rate in project `.env`. Recheck after repairs. Seedance 2.5 requires a readable, nonempty `sd25-pe/SKILL.md`; if installation fails, stop tasks requiring it. Other tasks do not require sd25-pe. ffprobe is required only when the task depends on its media inspection.
3. For every Seedance 2.5 prompt, read and apply the installed `sd25-pe/SKILL.md`, including its applicable instructions. Record `optimizer: {"skill":"sd25-pe","status":"applied"}` only after applying it. Other models use their relevant model references; do not apply 2.5 templates to other models.

## File storage

Keep only final deliverables in the user-selected output directory (default: the current project directory). Before preparing a task, supply the agent-authored requirement JSON on stdin to `python3 <skill-dir>/scripts/media.py init` to create a private working directory named `/tmp/richmedia-YYYYMMDDHHmmss/`; reuse the returned directory throughout the task. Store all requests, costs, job state, API responses, usage, download manifests, temporary files and intermediate downloads beneath it. Do not create task/work directories such as `generated/`, `output/`, `richmedia/` or `richmedia-jobs/` in the project. Keep the CLI working directory at the project so its `.env` still loads.

After a successful download, copy only the completed media to the output directory with a descriptive, non-conflicting filename; preserve original bytes. For layer decomposition, layer images and placement metadata are final deliverables. Keep all other metadata and recovery state in the `/tmp` working directory, including after failure or unknown submission outcome. Return links/previews to the final copies and state the temporary working path when needed for resuming. Temporary storage can be cleared by the system; check existing state before resuming and never treat missing state as permission to repeat a paid POST.

## Workflow

### 1. Identify intent and deliverables

Use the user's description and supplied assets to identify the capability and mode for this task.

| Intent / capability | operation | Identifying requirement | Modes |
|---|---|---|---|
| Text-to-image | `text-to-image` | Generate an image from a text description. | — |
| Image-to-image | `image-to-image` | Generate or modify images based on existing images. | Single-image editing, multi-image fusion, region editing |
| Layer decomposition | `decompose-layers` | Separate an image into a background and usable layers. | — |
| Text-to-video | `text-to-video` | Generate a video from text without reference assets. | — |
| Image-to-video | `image-to-video` | Use specified images as the opening frame or opening and ending frames. | First frame, first and last frames |
| Reference-to-video | `reference-to-video` | Borrow reference assets to generate a new video, or modify an existing video's content. | Reference generation, video editing |
| Video extension | `extend-video` | Continue before or after an existing video. | Extend before, extend after |

An image used as a first/last frame belongs to image-to-video; an image used as a person, product or style reference belongs to reference-to-video.

For staged requests, identify each stage's capability and mode separately.

Use only these seven `operation` values; image-to-image has no top-level `mode` and expresses editing/fusion intent in the prompt. See supplier references for video mode parameters.

### 2. Read supplier capabilities and check prerequisites

Read the relevant [Volcengine](references/volcengine.md) or [BytePlus](references/byteplus.md) documentation and model catalog. Distinguish provider API support from capabilities actually implemented by this skill. Check required inputs, counts, formats, dimensions, durations, transport modes and parameter limits. Perform task-relevant configuration and dependency checks; configured credentials do not prove access, balance or successful live calls. Explain unsupported operations without silently changing the model or supplier.

### 3. Prepare the run environment

From the project directory pass agent-authored JSON through stdin to `python3 <skill-dir>/scripts/media.py init`; directory names use the system local clock. Reuse its returned `workdir` throughout this task, including supplier examples. The command validates the stdin JSON object, creates a private directory, writes request.json, and returns only `{"workdir":"/tmp/richmedia-YYYYMMDDHHmmss"}`; it does not infer task content.

The agent supplies the original prompt, resolved user intent, confirmed information from step 2, each candidate supplier's model/operation/parameters, and asset paths and purposes through stdin for init to save as `request.json`. Keep supplier-specific parameters, roles, asset IDs and provenance under the corresponding supplier. Ask for unresolved required information rather than guessing, and never store credentials or Base64 bodies. See [run directory and requirement records](references/usage.md#run-directory-and-requirement-records).

This agent-maintained record is not an API payload or a submit input. After prompt optimization and estimation inputs are ready, derive a separate CLI-compatible `task-spec.json` or `<provider>-task-spec.json` without overwriting the original prompt. The agent follows the request.json field format in the CLI manual; init validates JSON syntax and the top-level object and writes the file, without validating business fields.

### 4. Estimate costs

1. Resolve candidate suppliers: calculate only the user-selected supplier, or each available supplier supporting the task when none was selected.
2. Read the candidate supplier's cost rules ([Volcengine](references/volcengine.md#cost-calculation)) and assemble a JSON object following the operation's required fields, types and examples.
3. Run the shared cost script from the project directory, passing that JSON on stdin, once per supplier. Replace the JSON placeholder in this command template before execution:

   ```bash
   python3 "$SKILL/scripts/media.py" estimate-cost --workdir "$WORK" <<'JSON'
   <JSON object assembled from the current supplier's rules>
   JSON
   ```

   `$SKILL` is the installed skill directory and `$WORK` is the task workdir from step 3. Python inspects the supplied media, reads rates and calculates costs, saving the result to `$WORK/<supplier>/cost.json`.

4. Read `result` for the confirmation: amount, currency, range and uncertainty reasons. Unknown is not zero, and a lower bound is not a total. Only use script-returned conversions to compare currencies. Re-estimate and obtain confirmation after generation settings change; submission reuses the saved estimate and evidence. An estimate is not an actual bill or a hard spending cap.

Example showing only `result` from the complete response saved to `$WORK/<supplier>/cost.json` (see the [CLI manual](references/usage.md) for the calculation record):

```jsonc
{
  "status": "estimate", // estimate: value/range; lower_bound: upper amount unknown; unknown: amount undetermined
  "currency": "CNY", // Native currency for the confirmation
  "amount": { // Example: Seedream Pro, 1K, one input image and one output
    "min": 0.3, // Lower amount; null when unknown
    "max": 0.3 // Upper amount; null when unknown
  },
  "uncertainties": [] // Items contain field and reason explaining uncertain costs
  // Valid FX adds conversion: currency, amount {min,max}, usd_cny and expires_at.
  // Without valid FX, conversion is absent.
}
```

### 5. Generate the confirmation and obtain confirmation

Follow [task confirmation template and native selection](references/task-confirmation.md) to generate the sheet and obtain user confirmation.

### 6. Execute the confirmed supplier plan

- Resolve the execution plan using the supplier, model and capability confirmed by the user in step 5.
- Read “Generation steps” for that capability in the selected supplier's reference (see the supplier references in step 2), and assemble the required call parameters.
- Call the specified scripts in the documented order. Parse each step's returned result before proceeding to the next, until generated outputs have been downloaded or saved.
- Follow that capability's “Success, failure and retries” instructions to determine the outcome and handle failures or recovery.

### 7. Verify and deliver

Use the confirmed user requirements and the operation-specific success criteria to check provider status, expected output count, file integrity and observable product details, identity, text, sequence, audio and duration. Queued/running status or API acceptance is not completion. State inspection limits. Copy only final media to the delivery directory, include placement metadata for decomposed layers, and provide absolute local links or previews. Keep intermediate state in the temporary directory. Distinguish estimates, API usage and verified billing; further paid corrections require a new confirmation.

### Creative and model notes

#### Images

Use a concise brief: subject/product, intended use, action, setting, composition, light, style, text content, and properties that must remain. Inspect reference images and assign each a role (product shape, background, palette, person). Do not add unrequested decorative objects or change product markings. Default to `size=1K` and one output. Infer an image composition ratio from the prompt and set `parameters.ratio`; it is appended as prompt guidance, not a guaranteed output pixel ratio. User-specified exact pixels become `size=WxH` and take precedence over a size tier.

For edits, state the change and scope. Region editing uses verified normalized coordinates or user-provided annotations. Preserve transparent input alpha only through the supported image-edit path. Decomposing a picture returns a background and transparent layers; save every result and bounding_box/z_index metadata rather than just data[0]. Pro/Flash image batches use multiple independent tasks, not native group generation.

#### Seedance 2.5

Mandatory: apply installed sd25-pe. Use its task-specific templates and material-responsibility rules. Distinguish semantic reference from strict first/last-frame input and from actual edit/extension. Use upload-order per-type references and preserve identities, dialogue and event order. Runtime parameters remain separate from prompt narrative. Preserve user-specified timestamp events; do not invent timestamps just because an API duration was selected.

Video editing: explicitly express editing intent (e.g. 编辑视频、修改、替换、删除、增加). 2.5 `omni_reference_task_type=edit`, ratio=adaptive, duration=-1. Extension: explicitly express 向前/向后延长、延续、续写 and use type=extend with adaptive ratio. Reference creation: type=reference; clearly describe what to borrow, avoiding wording that accidentally requests strict editing. Source video selected by model when multiple videos exist; if ambiguous, clarify the target before confirmation.

#### Seedance 2.0 / Fast / Mini

Use the 2.0 official guide rather than treating 2.5 prompt control as universal. Describe subject, actions, scene, light, shots, style and necessary constraints. Use shot sequence for ordering rather than promising precise 2.5 timestamp behavior. State the specific reference dimension (appearance/action/camera/voice). Editing/extension should name 视频N directly rather than vaguely saying 参考视频N. Do not overconstrain or add unrequested subtitles, logos, watermarks or generic negative-prompt bundles. Platform watermark is a separate displayed API setting.

#### Image → video

Prepare/confirm/generate/download the image first. Inspect that actual result before forming the next video plan; do not pre-approve a video using an unknown future image. Each paid step has its own confirmation. A user's approval of image generation does not approve subsequent video generation. For trusted portraits, keep original bytes, account provenance and timestamps; do not assume any Seedream edit output or cross-platform image is trusted.

#### Longer videos and creative methods

Use native model duration limits. Split longer stories into separately reviewed shots when needed; do not imply that a model can generate an unlimited-length single clip. Tail-frame chaining and video extension can maintain continuity, but every paid generation needs a fresh plan/confirmation. Stitching is a separate explicitly requested post-processing task, not currently a bundled command. Advertising/UGC methodology can be added as focused references after concrete examples are supplied; do not invent a large unvalidated prompt library.

#### Quality review

Inspect generated media when the environment can display/read it. Check requested product details, identities, scene order, text, audio and duration. State observation limits when audio/video cannot be inspected. Do not claim quality verification from task success or a file header. If correction needs another paid request, explain the targeted change and obtain approval for a new plan.

### Existing reference content

1. Read only the relevant references: [workflow](#workflow), [Volcengine constraints](references/volcengine.md), [BytePlus differences](references/byteplus.md), [CLI and request schema](references/usage.md), [Volcengine cost rules](references/volcengine.md#cost-calculation), and [task confirmation](#5-generate-the-confirmation-and-obtain-confirmation).
2. Inspect provided media. Preserve requested identities, product details, subject count, event order, dialogue, model and material mapping. Record the original prompt separately. Do not invent asset observations. Give each used asset a purpose; number video content by type and upload order.
3. For image creation, default to the smallest supported size and one output. Infer a composition ratio and set `parameters.ratio`; current image adapters express it as prompt guidance, not guaranteed output pixels. Exact user-specified pixels take precedence. For video creation/editing, use the lowest supported resolution (480p), minimum configurable duration (4 seconds), one request and no optional audio unless requested or needed. Explicit user requirements take precedence. Seedance 2.5 editing uses `duration=-1` and `ratio=adaptive`; never truncate input to reduce cost. Extension needs a resolved resolution and duration and must preserve requested audio/continuity. Do not silently switch a named model to a cheaper one.
4. Prepare one common request for supplier comparison. If multiple suppliers have keys configured and the user has not selected one, first run `media.py estimate-cost --workdir <workdir>` to calculate each compatible supplier’s quote, then read each cost.json to assemble the quotes in the confirmation sheet. Keep model, prompt, media, resolution, duration and options comparable. Verify supplier-specific asset IDs and cost-result limitations independently. Do not silently choose the cheapest, compare unlike currencies, call suppliers just to compare, or reuse portrait trust/asset IDs across suppliers or accounts. For an explicit single-provider request, specify that provider in the task configuration.
5. Generate and display the sheet following [step 5](#5-generate-the-confirmation-and-obtain-confirmation); do not duplicate its format or supplier list here.
6. Obtain the actual native selection following step 5 and its template. End the confirmation turn before paid execution; preselection or silence never confirms.
7. Only after the user's current supplier selection and confirmation, submit the selected task configuration with `submit --request <task-spec.json> --workdir <workdir> --approval-text <actual choice>`. The command reads `<workdir>/<provider>/cost.json` directly; it does not require plan or comparison files. Provider `submit`, `status`, and `download` commands need outbound network access; when the default command sandbox blocks network/DNS, run them through `exec_command` with `sandbox_permissions: "require_escalated"` and a concise reason. Do not first attempt a paid POST in the restricted sandbox: Python DNS failure can produce `URLError` before the request reaches the provider. Each confirmation permits one paid attempt. After the previous task reaches a known terminal state and the user confirms again, the same workdir permits a new submission with an incremented submit-NNN.json record. Active or unknown submissions must be queried/reconciled first; never automatically retry or fail over. Unknown cost upper bounds require explicit acceptance before using `--accept-uncertain-cost`. Any change to prompt, media, price, model, quantity or parameters invalidates approval; update the task configuration, reprice when billing inputs change, and ask again.
8. Submit once. Poll `status --wait 45` in bounded intervals. A queued/running task is not complete. Download into the temporary working directory on success, copy only final deliverables to the output directory as described under File storage, preserve original bytes and layer placement metadata, and provide absolute local file links/previews. Report API usage separately from estimates; report actual money only after verified billing data.

When a user asks for a cURL example for a prepared or approved request, use `compile_request` on the selected task configuration and copy its `payload_template` and prompt exactly; after submission read `execution.compiled` from submit-NNN.json. Do not rebuild or normalize parameters from the confirmation text. For Seedream 5.0 Pro/Flash, preserve a resolution tier such as `1K`; the ratio is prompt guidance and is not a separate API field. If the request explicitly uses pixel dimensions, validate them against the model's documented total-pixel and aspect-ratio limits. Keep `output_format`, `response_format`, `watermark`, and other approved fields unchanged. A shell `curl` command does not automatically load project `.env`; use a safe data-only loader to read the selected key from project `.env`; never `source`/execute the file or expose the key in output.



## Failure and recovery

- Never auto-retry a paid POST. A timeout, `URLError`, server error or interruption may mean the request was accepted or charged even when no response/task ID arrived. This is a transport-level unknown outcome, not proof of provider rejection. Use the persisted job state; reconcile with the selected supplier console/account before recovery. When only `URLError` is known, do not claim whether DNS, proxy, TLS, firewall or timeout caused it. Never automatically fail over to another supplier. A supplier switch needs a new plan and confirmation. Do not clear `submit-NNN.json` to bypass duplicate protection.
- Status and download GET requests may be repeated. Do not regenerate because a URL expired or a download failed; save outputs promptly because supplier URLs generally expire after 24 hours.
- A failed task, partial response or provider rejection is not success. Explain the provider status/error, propose a focused change and prepare a new task confirmation before another paid attempt. Avoid repeated subjective retries.
- Do not automatically crop or transcode trusted portrait inputs. Track supplier/account provenance, creation time and original hashes. Follow the official portrait paths in the relevant references.
- Supported scope: four Seedance models and Seedream Pro/Flash standard generation, editing and layer decomposition. Draft-to-final, native video search, interactive canvas selection, automatic storage upload, stitching and additional suppliers are not implemented. Do not send unchecked raw parameters; add reviewed adapter capabilities when requested.

## Validation

For code changes, run `python3 -m unittest discover -s <skill-dir>/tests -v`. Tests mock paid calls and do not prove live model access or output quality. Never run paid smoke tests without a task confirmation and the user's current approval. Refresh official sources when model capabilities or prices may have changed.
