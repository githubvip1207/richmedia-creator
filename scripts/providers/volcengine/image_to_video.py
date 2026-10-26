"""火山引擎 / 图生视频：模型规则、费用计算、提交、状态判断和交付。

compile_request 使用报价中固定的素材测量结果。
submit 返回供应商原始响应；命令层将其与 execution.compiled、task_id 一并保存。
status 和 deliver 始终使用同一份已有提交记录，不创建新请求。
"""

import copy
import json
import math
import re
from core.validation import require, number
from core.video_options import validate_video_options
from core.catalogs import ROOT, CATALOGS, RATIOS
from core.operations import internal_operation
from core.cost_record import build_record
from core.cost_quote import billing_inputs
from core import media_probe, payload as payload_tools, submission_store as store
from core.asset_inspect import inspect_asset, quoted_asset_matches
from core.payload_size import validate_image_request_size
from core.output_files import retrieve_outputs
from providers import get_provider
from . import client

PROVIDER = "volcengine"
OPERATION = "image-to-video"
KIND = "video"


def require_identity(value):
    require(
        value.get("provider") == PROVIDER and value.get("operation") == OPERATION,
        "Capability supplier/operation mismatch",
    )


from core.image_constraints import validate_image_metadata


def compile_image_assets(inputs, measured_assets, operation="image-to-image"):
    """将有序图片来源与实测报价绑定，仅在执行 POST 时编码。"""
    from core.asset_inspect import inspect_asset

    maximum = 10
    require(
        isinstance(inputs, list) and 1 <= len(inputs) <= maximum,
        "image-to-video requires 1.." + str(maximum) + " outer assets",
    )
    for item in inputs:
        require(
            isinstance(item, dict) and set(item) == {"id", "kind", "source", "purpose"},
            "Each outer asset requires id, kind, source and purpose",
        )
        require(
            isinstance(item["id"], str) and bool(item["id"].strip()),
            "Asset id must be a nonempty string",
        )
        require(item["kind"] == "image", "image-to-video accepts image assets only")
    require(len({item["id"] for item in inputs}) == len(inputs), "Asset ids must be unique")
    sources = [item["source"] for item in inputs]
    if measured_assets is not None:
        require(
            isinstance(measured_assets, list) and len(measured_assets) == len(sources),
            "Image sources differ from cost artifact; estimate again",
        )
    assets = []
    for index, source in enumerate(sources):
        measured = measured_assets[index] if measured_assets is not None else None
        if measured is not None:
            require(
                quoted_asset_matches(measured, inputs[index]),
                "Image sources/order differ from cost artifact; estimate again",
            )
        asset = inspect_asset({k: v for k, v in inputs[index].items() if k != "id"})
        asset["id"] = inputs[index]["id"]
        asset["source"] = source
        require(
            asset["transport"] in ("https", "local-base64"),
            "Image input accepts local paths or HTTPS, not asset IDs",
        )
        if measured is not None:
            metadata = {k: v for k, v in measured.items() if k not in ("id", "kind", "source")}
            if asset["transport"] == "local-base64":
                require(
                    metadata.get("sha256") == asset["sha256"],
                    "Local image changed after estimation; estimate again and reconfirm",
                )
            else:
                asset["metadata"] = metadata
            if "id" in measured:
                asset["id"] = measured["id"]
        validate_image_metadata(asset["metadata"], require_dimensions=measured is not None)
        assets.append(asset)
    return assets


def validate_frame_metadata(metadata):
    validate_image_metadata(metadata)
    w, h = (metadata["width"], metadata["height"])
    require(
        300 <= min(w, h) and max(w, h) <= 6000 and (0.4 <= w / h <= 2.5),
        "Video frame dimensions must be 300..6000 px with aspect ratio 0.4..2.5",
    )
    require(metadata.get("bytes", 0) < 31457280, "Video frame must be less than 30 MB")


def validate_video_tools(provider, operation, tools):
    require(
        isinstance(tools, list) and (tools == [] or tools == [{"type": "web_search"}]),
        'Video tools must be [] or [{"type":"web_search"}]',
    )


# 生成参数校验：按本供应商模型规则校验，并将外层素材编排进请求模板。
def compile_request(spec, measured_assets=None):
    from core.operations import internal_operation

    require_identity(spec)
    allowed = {
        "provider",
        "operation",
        "mode",
        "original_prompt",
        "payload",
        "assets",
        "estimate_context",
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
        "callback_url",
        "safety_identifier",
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
        and ("image-to-video" in models[alias]["operations"]),
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
    required_fields = (
        "resolution",
        "ratio",
        "duration",
        "generate_audio",
        "watermark",
        "return_last_frame",
    )
    for key in required_fields:
        require(
            key in body,
            "payload." + key + " is required; resolve documented defaults before submission",
        )
    require(
        "omni_reference_task_type" not in body,
        "omni_reference_task_type is only supported for Seedance 2.5 multimodal video",
    )
    require(body["ratio"] == "adaptive", "Image-to-video requires ratio=adaptive")
    validate_video_options(body, PROVIDER, alias)
    body.setdefault("tools", [{"type": "web_search"}] if alias == "seedance-2.5" else [])
    require(alias == "seedance-2.5" or not body["tools"], "Seedance 2.0 web_search requires pure text input; disable tools for media inputs")
    if "tools" in body:
        validate_video_tools("volcengine", "image-to-video", body["tools"])
    inputs = spec.get("assets", [])
    require(isinstance(inputs, list), "assets must be an array")
    if op == "text-to-video":
        require(
            inputs == [] and measured_assets in (None, []), "Text-to-video must not include assets"
        )
        assets = []
    else:
        count = 1 if op == "first-frame" else 2
        require(len(inputs) == count, "Incorrect first/last frame count")
        assets = compile_image_assets(inputs, measured_assets)
        for index, asset in enumerate(assets):
            validate_frame_metadata(asset["metadata"])
            asset["role"] = "first_frame" if index == 0 else "last_frame"
            body["content"].append(
                {
                    "type": "image_url",
                    "image_url": {"url": {"asset_index": index}},
                    "role": asset["role"],
                }
            )
    params = {k: v for k, v in body.items() if k not in ("model", "content")}
    params["output_format"] = body.get("output_format", "mp4")
    validate_cost_inputs(
        {
            "provider": "volcengine",
            "model": alias,
            "operation": "image-to-video",
            **{},
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
        "operation": "image-to-video",
        **{},
        "prompt": prompt,
        "assets": assets,
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
    get_provider(PROVIDER)
    models = CATALOGS[PROVIDER]["models"]
    model = inputs["model"]
    if model not in models:
        model = next((k for k, v in models.items() if v["id"] == model), None)
    require(model is not None, "Unknown model")
    m = models[model]
    op = internal_operation(inputs)
    require("image-to-video" in m["operations"], "Operation not supported by model")
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
        "operation": "image-to-video",
        **({"mode": inputs["mode"]} if inputs.get("mode") is not None else {}),
        "parameters": params,
        "assets": assets,
    }


from core.video_dimensions import table_dimensions


def target_asset(compiled, context):
    """明确选择目标素材；此选择仅用于估价，不作为 API 控制参数。"""
    assets, operation = (compiled["assets"], internal_operation(compiled))
    if operation in ("first-frame", "first-last-frame"):
        candidates = [0] if assets else []
    elif operation in ("edit-video", "extend-video"):
        candidates = [i for i, a in enumerate(assets) if a["kind"] == "video"]
    else:
        candidates = []
    selected = (context or {}).get("target_asset_index")
    if selected is not None:
        require(
            type(selected) is int and selected in candidates,
            "target_asset_index must identify the first frame or an editing/extension source video",
        )
        return (selected, assets[selected])
    if len(candidates) == 1:
        return (candidates[0], assets[candidates[0]])
    return (None, None)




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

    mode = internal_operation(inputs)
    require(
        len(assets) == (1 if mode == "first-frame" else 2)
        and all((isinstance(a, dict) and a.get("kind") == "image" for a in assets)),
        "Image-to-video requires ordered first/last image frames",
    )
    measured = [media_probe.probe_asset(a) for a in assets]
    for asset in measured:
        require(asset["kind"] == "image", "Image-to-video accepts image frames only")
        validate_frame_metadata(asset["metadata"])
    validate_image_request_size(measured)
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


# 生成查询审计信息，路径来自本供应商客户端。
def status_request(record):
    """记录查询请求的审计信息，任务 ID 使用 submit 保存的值。"""
    require_identity(record["execution"]["compiled"])
    return {"method": "GET", "path": client.status_path(record["execution"]["task_id"])}
