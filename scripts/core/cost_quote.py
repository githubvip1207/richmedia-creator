"""核对已保存报价的有效期及已确认的计费输入。"""

import copy
import datetime as dt
from core.validation import require
from core.exchange_rate import validate_fx


def billing_inputs(compiled):
    p = compiled["parameters"]
    result = {
        "provider": compiled["provider"],
        "model": compiled["model"],
        "operation": compiled["operation"],
        "input_images": sum((a["kind"] == "image" for a in compiled["assets"])),
        "input_video_seconds": [
            a["metadata"]["duration"] for a in compiled["assets"] if a["kind"] == "video"
        ],
        "input_audio_seconds": [
            a["metadata"]["duration"] for a in compiled["assets"] if a["kind"] == "audio"
        ],
    }
    if "target_asset_id" in compiled:
        result["target_asset_id"] = compiled["target_asset_id"]
    if compiled.get("mode") is not None:
        result["mode"] = compiled["mode"]
    if compiled["kind"] == "image":
        result["size"] = p["size"]
    else:
        result.update({k: p[k] for k in ("resolution", "ratio", "duration")})
    return result


def consume_quote(spec, quote, compiler, currency):
    """复用已保存的公式输入和计算结果，不读取新价格或重新计算费用。"""
    require(
        isinstance(quote, dict) and set(quote) == {"input", "calculation", "result"},
        "Cost artifact format changed; run main.py cost again",
    )
    calculation, result = (quote["calculation"], quote["result"])
    require(
        calculation.get("schema_version") == 3,
        "Cost artifact format changed; run main.py cost again",
    )
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(calculation["created_at"])
    require(
        dt.timedelta(0) <= age <= dt.timedelta(hours=24),
        "Cost artifact expired; run main.py cost again",
    )
    s = copy.deepcopy(spec)
    if "estimate_context" not in s and calculation.get("estimate_context") is not None:
        s["estimate_context"] = copy.deepcopy(calculation["estimate_context"])
    if "fx" not in s and calculation.get("fx") is not None:
        s["fx"] = copy.deepcopy(calculation["fx"])
    if s.get("fx") is not None:
        validate_fx(s["fx"])
    compiled = compiler(s, measured_assets=calculation["assets"] if "payload" in s else None)
    # URL 本身不代表内容不变；付费前重新读取当前计费规格。
    from core.media_probe import probe_asset
    for asset in calculation['assets']:
        if asset.get('source', '').startswith('https://') and asset.get('cost_probe_version') == 2:
            fresh = probe_asset({k: asset[k] for k in ('id', 'kind', 'source') if k in asset})['metadata']
            for key in ('width', 'height', 'display_width', 'display_height', 'duration', 'bytes'):
                require(key not in asset or fresh.get(key) == asset[key],
                        'Remote asset billing properties changed after estimation; estimate again and reconfirm')
    billing = billing_inputs(compiled)
    require(
        all((calculation.get(k) == v for k, v in billing.items()))
        and compiled.get("target_asset_id") == calculation.get("target_asset_id")
        and s.get("estimate_context") == calculation.get("estimate_context")
        and (s.get("fx") == calculation.get("fx")),
        "Request differs from cost artifact; run main.py cost again",
    )
    require(
        calculation["provider"] == compiled["provider"] and result["currency"] == currency,
        "Cost artifact supplier mismatch",
    )
    return (s, compiled, calculation["pricing"], result)
