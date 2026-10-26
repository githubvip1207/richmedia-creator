"""火山引擎 / 文生图：模型规则、费用计算、提交、状态判断和交付。

compile_request 使用报价中固定的素材测量结果。
submit 返回供应商原始响应；命令层将其与 execution.compiled、task_id 一并保存。
status 和 deliver 始终使用同一份已有提交记录，不创建新请求。
"""

import copy
import json
import re
from core.validation import require, number
from core.catalogs import ROOT, CATALOGS
from core.operations import internal_operation, require_supported_operation
from core.cost_record import build_record
from core.cost_quote import billing_inputs
from core import media_probe, payload as payload_tools, submission_store as store
from core.http import response_error
from core.output_files import retrieve_outputs
from providers import get_provider
from . import client

PROVIDER = "volcengine"
OPERATION = "text-to-image"
KIND = "image"


def require_identity(value):
    require(
        value.get("provider") == PROVIDER and value.get("operation") == OPERATION,
        "Capability supplier/operation mismatch",
    )


# 生成参数校验：按本供应商模型规则校验，并将外层素材编排进请求模板。
def compile_request(spec, measured_assets=None):
    """校验选定供应商的图片请求正文，不改写提示词。"""
    require(measured_assets in (None, []), "Text-to-image must not include measured assets")
    require_identity(spec)
    allowed = {
        "provider",
        "operation",
        "original_prompt",
        "payload",
        "estimate_context",
        "budget_cny",
        "budget_usd",
        "fx",
    }
    require(not set(spec) - allowed, "Unsupported native request envelope fields")
    require(
        isinstance("volcengine", str) and "volcengine" in CATALOGS,
        "Select a supported supplier explicitly",
    )
    require_supported_operation(spec)
    internal_operation(spec)
    payload = copy.deepcopy(spec.get("payload"))
    require(isinstance(payload, dict), "payload must be an object")
    fields = {
        "model",
        "prompt",
        "size",
        "output_format",
        "response_format",
        "watermark",
        "background",
        "optimize_prompt_options",
        "layer_decomposition",
    }
    require(
        not set(payload) - fields,
        "Unsupported native image payload fields: " + str(sorted(set(payload) - fields)),
    )
    models = CATALOGS[PROVIDER]["models"]
    alias = next((k for k, v in models.items() if v["id"] == payload.get("model")), None)
    require(
        alias is not None and "text-to-image" in models[alias]["operations"],
        "payload.model must be an exact image model ID belonging to the selected supplier",
    )
    prompt = payload.get("prompt")
    require(isinstance(prompt, str) and bool(prompt.strip()), "payload.prompt is required")
    require(
        "size" in payload,
        "payload.size is required; resolve the documented default before submission",
    )
    fixed = {
        "output_format": "png",
        "response_format": "url",
        "watermark": False,
        "background": "opaque",
        "layer_decomposition": False,
    }
    for key, value in fixed.items():
        require(
            key in payload and type(payload[key]) is type(value) and (payload[key] == value),
            "text-to-image requires " + key + "=" + str(value),
        )
    require(
        "optimize_prompt_options" not in payload, "text-to-image must omit optimize_prompt_options"
    )
    assets = []
    params = {"size": payload["size"], **fixed}
    validate_cost_inputs(
        {
            "provider": "volcengine",
            "model": alias,
            "operation": "text-to-image",
            "input_images": len(assets),
            "size": params["size"],
        }
    )
    for key in ("budget_cny", "budget_usd"):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + " must be positive")
    return {
        "provider": "volcengine",
        "model": alias,
        "kind": "image",
        "operation": "text-to-image",
        "prompt": prompt,
        "assets": assets,
        "parameters": params,
        "payload_template": payload,
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
    require("text-to-image" in m["operations"], "Operation not supported by model")
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
    require(not seconds and (not audio_seconds), "Image operations accept image assets only")
    low, high = {"text-to-image": (0, 0), "image-to-image": (1, 10), "decompose-layers": (1, 1)}[op]
    require(low <= count <= high, "Invalid input image count for operation")
    size = inputs.get("size")
    sizes = m["sizes"] + (["auto"] if op == "decompose-layers" else [])
    if size not in sizes:
        import re

        require(
            op != "decompose-layers"
            and isinstance(size, str)
            and re.fullmatch("[1-9][0-9]*x[1-9][0-9]*", size),
            "Invalid image size",
        )
        w, h = map(int, size.split("x"))
        require(
            921600 <= w * h <= 4624220 and 0.0625 <= w / h <= 16,
            "Image size outside supported pixels/ratio",
        )
    require(
        not any((inputs.get(k) is not None for k in ("resolution", "ratio", "duration"))),
        "Image costs require size, not video settings",
    )
    params = {"size": size}
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
        "kind": "image",
        "operation": "text-to-image",
        **({"mode": inputs["mode"]} if inputs.get("mode") is not None else {}),
        "parameters": params,
        "assets": assets,
    }


# 计费公式：按本供应商、模型和能力计算原币金额及不确定范围。
def calculate_cost(compiled, context=None, pricing=None, fx=None):
    require_identity(compiled)
    info = get_provider(PROVIDER)
    from core.pricing import load_pricing
    price = pricing or load_pricing(PROVIDER)
    currency = info["currency"]
    require(
        price.get("currency") == currency and price.get("provider", "volcengine") == "volcengine",
        "Pricing snapshot supplier/currency mismatch",
    )
    if fx is not None:
        from core.exchange_rate import validate_fx

        validate_fx(fx)
    ctx = {} if context is None else context
    require(isinstance(ctx, dict), "estimate_context must be an object")
    require(
        not set(ctx)
        - {
            "output_dimensions",
            "minimum_billable_tokens",
            "minimum_tokens_source",
            "target_asset_index",
        },
        "Unknown estimate_context fields",
    )
    out = {
        "provider": "volcengine",
        "currency": currency,
        "price_verified_on": price["verified_on"],
        "source": price["source"],
        "basis": price["basis"],
        "tokens": None,
        "amount": None,
        "missing_inputs": [],
        "notes": ["估算不是账单或硬预算上限；实际用量以 API usage、实付金额以账户账单为准。"],
    }

    def finish():
        amount = out["amount"]
        out["amount_cny"] = (
            amount
            if currency == "CNY"
            else (
                [round(v * fx["usd_cny"], 6) if v is not None else None for v in amount]
                if fx and amount
                else None
            )
        )
        out["amount_usd"] = (
            amount
            if currency == "USD"
            else (
                [round(v / fx["usd_cny"], 6) if v is not None else None for v in amount]
                if fx and amount
                else None
            )
        )
        if fx:
            out["fx"] = fx
        if currency == "USD" and (not fx):
            out["notes"].append(
                "美元原币估算；没有有效且未过期的汇率，不进行人民币换算，不能直接与人民币数字比较大小。"
            )
        return out

    model, p, assets = (compiled["model"], compiled["parameters"], compiled["assets"])
    r = price["image"][model]
    extra = max(0, len(assets) - 1) * r["input_after_first"]
    size = p["size"]
    if size in ("1K", "1.5K"):
        lo = hi = r["single"][0]
    elif size == "2K":
        lo = hi = r["single"][1]
    else:
        w, h = map(int, size.split("x"))
        lo = hi = r["single"][int(w * h > r["threshold_pixels"])]
    out["amount"] = [round(lo + extra, 6), round(hi + extra, 6)]
    out["calculation"] = {
        "size": p["size"],
        "input_images": len(assets),
        "extra_input_images": max(0, len(assets) - 1),
        "extra_input_unit_price": r["input_after_first"],
        "extra_input_cost": extra,
        "output_count_range": [1, 1],
        "output_unit_price_range": [lo, hi],
    }
    out["status"] = "estimate"
    out["notes"].append(
        "图片 Token 无可靠的调用前估算公式；显示为未知。图片费用按输入/输出张数与像素档位计算，不按此未知 Token 计费。"
    )
    return finish()


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
    measured = [media_probe.probe_asset(a) for a in assets]
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


# 按本能力的响应格式判断生成状态。
def response_state(result, compiled):
    """根据已保存的同步图片响应判断生成是否成功。"""
    require_identity(compiled)
    require(isinstance(result, dict), "Image response must be an object")
    if result.get("error"):
        error = response_error(result["error"], secrets=(compiled.get("prompt", ""),)).details
        return {"state": "failed", "usage": result.get("usage"), "errors": [error]}
    entries = result.get("data")
    require(isinstance(entries, list) and bool(entries), "Image response missing output data")
    require(all((isinstance(x, dict) for x in entries)), "Invalid image result entry")
    require(
        all(
            (
                x.get("error")
                or (isinstance(x.get("url"), str) and x["url"].startswith("https://"))
                or (isinstance(x.get("b64_json"), str) and bool(x["b64_json"]))
                for x in entries
            )
        ),
        "Image result missing usable output",
    )
    outputs = [x for x in entries if not x.get("error")]
    require(
        len(outputs) <= compiled["quantity"], "Image output count differs from confirmed quantity"
    )
    errors = [
        response_error(x["error"], secrets=(compiled.get("prompt", ""),)).details
        for x in entries
        if x.get("error")
    ]
    image_state = (
        "failed" if len(errors) == len(entries) else "partial_failed" if errors else "succeeded"
    )
    return {"state": image_state, "usage": result.get("usage"), "errors": errors}


# 提交前将素材编码、回填进请求模板；不改写提示词。
def build_payload(compiled):
    require_identity(compiled)
    return payload_tools.payload({"compiled": compiled})


# 生成入口：仅执行一次 POST；持久化和确认校验由命令层统一组织。
def submit(compiled, payload):
    require_identity(compiled)
    return client.request("POST", "/images/generations", payload)


# 状态入口：消费 submit 保存的响应或 task_id，不创建新生成。
def status(record, timeout=None):
    """重新判断已保存的同步响应；结果未明确的 POST 继续保持未明确状态。"""
    require_identity(record["execution"]["compiled"])
    state = record["execution"]
    if state["state"] in ("submitting", "submission_unknown", "rejected"):
        return dict(state)
    return response_state(record.get("response"), state["compiled"])


# 交付入口：解析本能力的输出，再调用 core 下载、校验和落盘。
def deliver(record, record_path):
    require_identity(record["execution"]["compiled"])
    result = record.get("response")
    entries = [(entry, "image") for entry in result.get("data", []) if not entry.get("error")]
    return retrieve_outputs(
        record,
        record_path,
        result,
        entries,
        currency=get_provider(PROVIDER)["currency"],
        layers=False,
    )
