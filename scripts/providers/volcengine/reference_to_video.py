"""火山引擎 / 参考生视频：模型规则、费用计算、提交、状态判断和交付。

compile_request 使用报价中固定的素材测量结果。
submit 返回供应商原始响应；命令层将其与 execution.compiled、task_id 一并保存。
status 和 deliver 始终使用同一份已有提交记录，不创建新请求。
"""

import copy
import json
import math
import re
from core.validation import require, number
from core.target_asset import target_index, validate_target_scope
from core.catalogs import ROOT, CATALOGS, RATIOS
from core.operations import internal_operation
from core.cost_record import build_record
from core.cost_quote import billing_inputs
from core import media_probe, payload as payload_tools, submission_store as store
from core.asset_inspect import inspect_asset, quoted_asset_matches
from core.output_files import retrieve_outputs
from providers import get_provider
from . import client

PROVIDER = "volcengine"
OPERATION = "reference-to-video"
KIND = "video"


def require_identity(value):
    require(
        value.get("provider") == PROVIDER and value.get("operation") == OPERATION,
        "Capability supplier/operation mismatch",
    )


def validate_reference_sources(assets):
    require(isinstance(assets, list) and bool(assets), "Reference generation requires assets")
    for asset in assets:
        require(
            isinstance(asset, dict) and asset.get("kind") in ("image", "video", "audio"),
            "Reference kind must be image/video/audio",
        )
        source = asset.get("source")
        require(isinstance(source, str) and bool(source), "Reference source is required")
        if asset["kind"] == "video":
            require(
                source.startswith("https://"),
                "Video input requires an accessible HTTPS URL; local video/Base64 and asset IDs are not supported",
            )


def validate_reference_metadata(kind, metadata, model, editing=False):
    if kind == "image":
        validate_frame_metadata(metadata)
    else:
        duration = metadata.get("duration")
        maximum = model["max_duration"]
        minimum = 4 if editing and maximum == 30 and (kind == "video") else 2
        require(
            number(duration) and minimum <= duration <= maximum,
            "Input " + kind + " duration outside model limits",
        )
        formats = set(str(metadata.get("format_name", "")).split(","))
        if kind == "video":
            require(bool(formats & {"mov", "mp4"}), "Reference video must be verified MP4 or MOV")
            require(
                metadata.get("codec_name") in ("h264", "hevc"),
                "Reference video requires H.264 or H.265",
            )
            width, height = (metadata.get("width"), metadata.get("height"))
            require(
                type(width) is int
                and type(height) is int
                and (300 <= min(width, height))
                and (max(width, height) <= 6000)
                and (0.4 <= width / height <= 2.5)
                and (407696 <= width * height <= 8295044),
                "Reference video dimensions outside model limits",
            )
            rate = metadata.get("frame_rate")
            require(
                number(rate) and 24 <= rate <= 60, "Reference video frame rate must be 24..60 FPS"
            )
        else:
            require(bool(formats & {"wav", "mp3"}), "Reference audio must be verified WAV or MP3")
    limit = {"image": 30, "video": 200, "audio": 15}[kind] * 1024 * 1024
    size = metadata.get("bytes")
    require(
        type(size) is int and 0 < size <= limit and (kind != "image" or size < limit),
        "Reference " + kind + " requires a measured byte size within its limit",
    )


def validate_reference_target(operation, mode, assets, context, require_target=True, target_asset_id=None):
    if mode != "edit":
        return
    require(any(asset['kind'] == 'video' for asset in assets), "Editing/extension needs a video")
    target_index(assets, target_asset_id, context, require_target=require_target)


def validate_reference_request_size(assets, template=None):
    body = copy.deepcopy(template or {})
    body.setdefault("content", [])
    encoded = 0
    for asset in assets:
        key = asset["kind"] + "_url"
        source = asset["source"]
        if not source.startswith("https://"):
            source = "data:" + asset["metadata"]["mime"] + ";base64,"
            encoded += 4 * ((asset["metadata"]["bytes"] + 2) // 3)
        body["content"].append(
            {"type": key, key: {"url": source}, "role": "reference_" + asset["kind"]}
        )
    require(
        len(json.dumps(body, ensure_ascii=False).encode()) + encoded <= 67108864,
        "Request exceeds 64 MB after Base64 encoding; use approved HTTPS asset URLs",
    )


def compile_reference_assets(inputs, measured_assets, model, editing=False):
    validate_reference_sources(inputs)
    for asset in inputs:
        require(
            set(asset) == {"id", "kind", "source", "purpose"},
            "Each outer reference requires id, kind, source and purpose",
        )
        require(
            isinstance(asset["id"], str) and bool(asset["id"].strip()),
            "Asset id must be a nonempty string",
        )
    require(len({a["id"] for a in inputs}) == len(inputs), "Asset ids must be unique")
    require(
        isinstance(measured_assets, list) and len(measured_assets) == len(inputs),
        "Reference assets require measured cost assets; run cost first",
    )
    assets = []
    for item, measured in zip(inputs, measured_assets):
        require(
            quoted_asset_matches(measured, item),
            "Reference sources/order differ from cost artifact; estimate again",
        )
        asset = inspect_asset({k: v for k, v in item.items() if k != "id"})
        require(
            asset["transport"] in ("https", "local-base64"),
            "References accept local image/audio or HTTPS URLs",
        )
        metadata = {k: v for k, v in measured.items() if k not in ("id", "kind", "source")}
        if asset["transport"] == "local-base64":
            require(
                metadata.get("sha256") == asset["sha256"],
                "Local reference changed after estimation; estimate again and reconfirm",
            )
        asset.update(id=item["id"], metadata=metadata, role="reference_" + item["kind"])
        validate_reference_metadata(item["kind"], metadata, model, editing)
        assets.append(asset)
    return assets


from core.image_constraints import validate_image_metadata


def validate_video_tools(provider, operation, tools):
    require(
        isinstance(tools, list) and (tools == [] or tools == [{"type": "web_search"}]),
        'Video tools must be [] or [{"type":"web_search"}]',
    )


# 生成参数校验：按本供应商模型规则校验，并将外层素材编排进请求模板。
def compile_request(spec, measured_assets=None):
    from core.operations import internal_operation

    require_identity(spec)
    validate_target_scope(spec)
    allowed = {
        "provider",
        "operation",
        "mode",
        "original_prompt",
        "payload",
        "assets",
        "estimate_context",
        "target_asset_id",
        "budget_cny",
        "budget_usd",
        "fx",
    }
    require(not set(spec) - allowed, "Unsupported native video envelope fields")
    require("volcengine" in CATALOGS, "Select a supported supplier explicitly")
    op = internal_operation(spec)
    body = copy.deepcopy(spec.get("payload"))
    require(isinstance(body, dict), "payload must be an object")
    fields = {
        "model",
        "content",
        "resolution",
        "ratio",
        "duration",
        "generate_audio",
        "watermark",
        "return_last_frame",
        "output_format",
        "service_tier",
        "tools",
        "omni_reference_task_type",
    }
    require(
        not set(body) - fields,
        "Unsupported native video payload fields: " + str(sorted(set(body) - fields)),
    )
    models = CATALOGS[PROVIDER]["models"]
    alias = next((k for k, v in models.items() if v["id"] == body.get("model")), None)
    require(
        alias is not None
        and models[alias]["kind"] == "video"
        and ("reference-to-video" in models[alias]["operations"]),
        "payload.model must be an exact video model ID belonging to the selected supplier",
    )
    content = body.get("content")
    require(
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and (set(content[0]) == {"type", "text"})
        and (content[0]["type"] == "text"),
        "payload.content must contain exactly one text item; provide ordered frames in outer assets",
    )
    prompt = content[0]["text"]
    require(isinstance(prompt, str) and bool(prompt.strip()), "Video prompt is required")
    require(
        not re.search(
            "--(?:rs|rt|dur|resolution|ratio|duration|frames|seed|cf|camerafixed|camera_fixed|wm|watermark)\\b",
            prompt,
        ),
        "Inline API parameter flags are unsupported; resolve settings in payload before confirmation",
    )
    omit_service_tier = True
    required_fields = (
        "resolution",
        "ratio",
        "duration",
        "generate_audio",
        "watermark",
        "return_last_frame",
    )
    if omit_service_tier:
        require("service_tier" not in body, "This video request must omit service_tier")
    else:
        required_fields += ("service_tier",)
    for key in required_fields:
        require(
            key in body,
            "payload." + key + " is required; resolve documented defaults before submission",
        )
    if alias == "seedance-2.5":
        task_type = {
            "reference-to-video": "reference",
            "edit-video": "edit",
            "extend-video": "extend",
        }[op]
        require(
            body.get("omni_reference_task_type") == task_type,
            "omni_reference_task_type must match operation/mode: " + task_type,
        )
    else:
        require(
            "omni_reference_task_type" not in body,
            "omni_reference_task_type is only supported for Seedance 2.5 multimodal video",
        )
    for key in ("generate_audio", "watermark", "return_last_frame"):
        require(type(body[key]) is bool, key + " must be a boolean")
    fixed_fields = {"watermark": False, "return_last_frame": False}
    if not omit_service_tier:
        fixed_fields["service_tier"] = "default"
    for key, value in fixed_fields.items():
        require(
            type(body[key]) is type(value) and body[key] == value,
            "Video generation requires " + key + "=" + str(value),
        )
    if alias == "seedance-2.5":
        require(body.get("output_format") == "mp4", "Seedance 2.5 requires output_format=mp4")
    else:
        require(
            "output_format" not in body,
            "Seedance 2.0 series must omit output_format; output is MP4",
        )
    body.setdefault("tools", [{"type": "web_search"}] if alias == "seedance-2.5" else [])
    require(alias == "seedance-2.5" or not body["tools"], "Seedance 2.0 web_search requires pure text input; disable tools for media inputs")
    if "tools" in body:
        validate_video_tools("volcengine", "reference-to-video", body["tools"])
    inputs = spec.get("assets", [])
    require(isinstance(inputs, list), "assets must be an array")
    if op == "text-to-video":
        require(
            inputs == [] and measured_assets in (None, []), "Text-to-video must not include assets"
        )
        assets = []
    else:
        assets = compile_reference_assets(
            inputs, measured_assets, models[alias], editing=op == "edit-video"
        )
        validate_reference_target(
            "reference-to-video", spec["mode"], assets, spec.get("estimate_context"), target_asset_id=spec.get("target_asset_id")
        )
        validate_reference_request_size(assets, body)
        for index, asset in enumerate(assets):
            key = asset["kind"] + "_url"
            body["content"].append(
                {"type": key, key: {"url": {"asset_index": index}}, "role": asset["role"]}
            )
    params = {k: v for k, v in body.items() if k not in ("model", "content")}
    params["output_format"] = body.get("output_format", "mp4")
    validate_cost_inputs(
        {
            "provider": "volcengine",
            "model": alias,
            "operation": "reference-to-video",
            **{"mode": spec["mode"]},
            **{k: params[k] for k in ("resolution", "ratio", "duration")},
            "input_images": sum((a["kind"] == "image" for a in assets)),
            "input_video_seconds": [
                a["metadata"]["duration"] for a in assets if a["kind"] == "video"
            ],
            "input_audio_seconds": [
                a["metadata"]["duration"] for a in assets if a["kind"] == "audio"
            ],
        }
    )
    for key in ("budget_cny", "budget_usd"):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + " must be positive")
    return {
        "provider": "volcengine",
        "model": alias,
        "kind": "video",
        "operation": "reference-to-video",
        **{"mode": spec["mode"]},
        "prompt": prompt,
        "assets": assets,
        **({"target_asset_id": spec["target_asset_id"]} if "target_asset_id" in spec else {}),
        "parameters": params,
        "payload_template": body,
        "warnings": [],
        "quantity": 1,
        "optimizer": None,
        "original_prompt": spec.get("original_prompt"),
    }


# 计费参数校验：模型规格和素材数量必须满足本能力要求。
def validate_cost_inputs(inputs, measured_assets=None):
    """仅校验计费输入，不需要提示词、虚构素材或生成请求正文。"""
    require_identity(inputs)
    validate_target_scope(inputs)
    get_provider(PROVIDER)
    models = CATALOGS[PROVIDER]["models"]
    model = inputs["model"]
    if model not in models:
        model = next((k for k, v in models.items() if v["id"] == model), None)
    require(model is not None, "Unknown model")
    m = models[model]
    op = internal_operation(inputs)
    require("reference-to-video" in m["operations"], "Operation not supported by model")
    count = inputs.get("input_images", 0)
    seconds = inputs.get("input_video_seconds", [])
    audio_seconds = inputs.get("input_audio_seconds", [])
    require(type(count) is int and count >= 0, "input_images must be a nonnegative integer")
    require(
        isinstance(seconds, list) and all((number(d) and d > 0 for d in seconds)),
        "Provide measured positive seconds for each input video",
    )
    require(
        isinstance(audio_seconds, list) and all((number(d) and d > 0 for d in audio_seconds)),
        "Provide measured positive seconds for each input audio",
    )
    require(inputs.get("size") is None, "Video costs require resolution, not image size")
    resolution, ratio, duration = (inputs.get(k) for k in ("resolution", "ratio", "duration"))
    require(resolution in m["resolutions"], "Invalid resolution")
    locked = op in ("first-frame", "first-last-frame") or (
        model == "seedance-2.5" and op in ("edit-video", "extend-video")
    )
    require(ratio in (["adaptive"] if locked else RATIOS), "Invalid ratio for operation")
    require(
        type(duration) is int and (duration == -1 or 4 <= duration <= m["max_duration"]),
        "Invalid duration",
    )
    require(
        not (model == "seedance-2.5" and op == "edit-video") or duration == -1,
        "Seedance 2.5 editing requires duration=-1",
    )
    require(
        count <= m["limits"]["image"]
        and len(seconds) <= m["limits"]["video"]
        and (len(audio_seconds) <= m["limits"]["audio"]),
        "Too many input assets",
    )
    minimum_seconds = 4 if model == "seedance-2.5" and op == "edit-video" else 2
    require(
        all((minimum_seconds <= d <= m["max_duration"] for d in seconds))
        and sum(seconds) <= m["max_duration"],
        "Input video duration outside model limits",
    )
    require(
        all((2 <= d <= m["max_duration"] for d in audio_seconds))
        and sum(audio_seconds) <= m["max_duration"],
        "Input audio duration outside model limits",
    )
    if op == "text-to-video":
        require(
            count == 0 and (not seconds) and (not audio_seconds),
            "Text-to-video has no input assets",
        )
    elif op in ("first-frame", "first-last-frame"):
        require(
            count == (1 if op == "first-frame" else 2) and (not seconds) and (not audio_seconds),
            "Invalid first/last frame input count",
        )
    elif op == "reference-to-video":
        require(bool(count or seconds or audio_seconds), "Reference generation requires assets")
        require(
            model == "seedance-2.5" or bool(count or seconds), "2.0 cannot use audio-only reference"
        )
    elif op in ("edit-video", "extend-video"):
        require(bool(seconds), "Editing/extension needs measured input video durations")
    params = {"resolution": resolution, "ratio": ratio, "duration": duration}
    assets = (
        measured_assets
        if measured_assets is not None
        else [{"kind": "image"} for _ in range(count)]
        + [{"kind": "video", "metadata": {"duration": d}} for d in seconds]
        + [{"kind": "audio", "metadata": {"duration": d}} for d in audio_seconds]
    )
    return {
        "provider": "volcengine",
        "model": model,
        "kind": "video",
        "operation": "reference-to-video",
        **({"mode": inputs["mode"]} if inputs.get("mode") is not None else {}),
        "parameters": params,
        "assets": assets,
        **({"target_asset_id": inputs["target_asset_id"]} if "target_asset_id" in inputs else {}),
    }


from core.video_dimensions import table_dimensions


def target_asset(compiled, context):
    """明确选择目标素材；此选择仅用于估价，不作为 API 控制参数。"""
    assets, operation = (compiled["assets"], internal_operation(compiled))
    if operation not in ("edit-video", "extend-video"):
        return (None, None)
    selected = target_index(assets, compiled.get("target_asset_id"), context)
    return (selected, assets[selected]) if selected is not None else (None, None)




# 计费公式：按本供应商、模型和能力计算原币金额及不确定范围。
def calculate_cost(compiled, context=None, pricing=None, fx=None):
    require_identity(compiled)
    from core.pricing import load_pricing
    from core.video_cost import calculate_video_cost
    return calculate_video_cost(compiled, context, pricing or load_pricing(PROVIDER), fx,
                                table_dimensions, target_asset)


# 将已验证的计费输入、公式和价格快照组织成可审计报价。
def calculate_inputs(inputs, pricing=None, context=None, fx=None, measured_assets=None):
    require_identity(inputs)
    from core import submission_store as store

    compiled = validate_cost_inputs(inputs, measured_assets)
    info = get_provider(PROVIDER)
    from core.pricing import load_pricing
    pricing = pricing or load_pricing(PROVIDER)
    detail = calculate_cost(compiled, context, pricing, fx)
    return build_record(
        inputs, compiled, billing_inputs(compiled), pricing, detail, context, fx, store.now()
    )


# 估价入口：测量素材后计算报价；不提交生成任务。
def cost(inputs, fx=None):
    require_identity(inputs)
    validate_target_scope(inputs)
    allowed = {
        "provider",
        "model",
        "operation",
        "mode",
        "size",
        "resolution",
        "ratio",
        "duration",
        "assets",
        "estimate_context",
        "target_asset_id",
    }
    require(isinstance(inputs, dict), "Cost input must be a JSON object")
    require(
        not set(inputs) - allowed,
        "Unknown cost input fields: " + str(sorted(set(inputs) - allowed)),
    )
    for key in ("provider", "model", "operation"):
        require(
            isinstance(inputs.get(key), str) and bool(inputs[key]),
            key + " must be a nonempty string",
        )
    from providers import get_provider

    get_provider(PROVIDER)
    assets = inputs.get("assets", [])
    require(isinstance(assets, list), "assets must be an array")
    from core.operations import internal_operation

    internal_operation(inputs)
    validate_reference_sources(assets)
    validate_reference_target(
        "reference-to-video",
        inputs["mode"],
        assets,
        inputs.get("estimate_context"),
        require_target=False, target_asset_id=inputs.get("target_asset_id"),
    )
    measured = [media_probe.probe_asset(a) for a in assets]
    catalog = CATALOGS[PROVIDER]["models"]
    model = catalog.get(inputs["model"]) or next(
        (m for m in catalog.values() if m["id"] == inputs["model"]), None
    )
    require(model is not None and model["kind"] == "video", "Unknown video model")
    for asset in measured:
        validate_reference_metadata(
            asset["kind"], asset["metadata"], model, editing=inputs["mode"] == "edit"
        )
    validate_reference_request_size(measured)
    resolved = {k: v for k, v in inputs.items() if k not in ("assets", "estimate_context")}
    resolved["input_images"] = sum((a["kind"] == "image" for a in measured))
    resolved["input_video_seconds"] = [
        a["metadata"]["duration"] for a in measured if a["kind"] == "video"
    ]
    resolved["input_audio_seconds"] = [
        a["metadata"]["duration"] for a in measured if a["kind"] == "audio"
    ]
    quote = calculate_inputs(
        resolved, context=inputs.get("estimate_context"), fx=fx, measured_assets=measured
    )
    quote["input"] = copy.deepcopy(inputs)
    return quote


# 提交前将素材编码、回填进请求模板；不改写提示词。
def build_payload(compiled):
    require_identity(compiled)
    return payload_tools.payload({"compiled": compiled})


# 生成入口：仅执行一次 POST；持久化和确认校验由命令层统一组织。
def submit(compiled, payload):
    require_identity(compiled)
    return client.request("POST", "/contents/generations/tasks", payload)


# 状态入口：消费 submit 保存的响应或 task_id，不创建新生成。
def status(record, timeout=None):
    """仅查询本次提交 POST 返回的任务 ID。"""
    require_identity(record["execution"]["compiled"])
    state = record["execution"]
    task_id = state.get("task_id")
    require(isinstance(task_id, str) and bool(task_id), "Submission has no task ID")
    return client.status(task_id) if timeout is None else client.status(task_id, timeout=timeout)


# 按本能力的响应格式判断生成状态。
def response_state(result, compiled, task_id=None):
    require_identity(compiled)
    require(isinstance(result, dict), "Video response must be an object")
    require(result.get("id", task_id) == task_id, "Provider returned a different task ID")
    return {
        "state": result.get("status", "unknown"),
        "usage": result.get("usage"),
        "error": result.get("error"),
    }


# 交付入口：解析本能力的输出，再调用 core 下载、校验和落盘。
def deliver(record, record_path):
    require_identity(record["execution"]["compiled"])
    task_id = record["execution"]["task_id"]
    result = next(
        (
            query["response"]
            for query in reversed(record.get("queries", []))
            if isinstance(query.get("response"), dict)
            and query["response"].get("id", task_id) == task_id
        ),
        record.get("response"),
    )
    content = result.get("content", {})
    entries = (
        [({"url": content["video_url"], "label": "video"}, "video")]
        if content.get("video_url")
        else []
    )
    if content.get("last_frame_url"):
        entries.append(({"url": content["last_frame_url"], "label": "last-frame"}, "image"))
    return retrieve_outputs(
        record, record_path, result, entries, currency=get_provider(PROVIDER)["currency"]
    )


def validate_frame_metadata(metadata):
    validate_image_metadata(metadata)
    w, h = (metadata["width"], metadata["height"])
    require(
        300 <= min(w, h) and max(w, h) <= 6000 and (0.4 <= w / h <= 2.5),
        "Video frame dimensions must be 300..6000 px with aspect ratio 0.4..2.5",
    )
    require(metadata.get("bytes", 0) < 31457280, "Video frame must be less than 30 MB")


# 生成查询审计信息，路径来自本供应商客户端。
def status_request(record):
    """记录查询请求的审计信息，任务 ID 使用 submit 保存的值。"""
    require_identity(record["execution"]["compiled"])
    return {"method": "GET", "path": client.status_path(record["execution"]["task_id"])}
