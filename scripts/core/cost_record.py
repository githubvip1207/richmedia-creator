"""生成精简报价结果，并完整保存实际采用的费用公式及审计依据。"""

import copy


def bounds(value):
    return {"min": value[0] if value else None, "max": value[1] if value else None}


def amount_in(result, currency):
    if result["currency"] == currency:
        return result["amount"]
    converted = result.get("conversion")
    return (
        converted["amount"]
        if converted and converted["currency"] == currency
        else {"min": None, "max": None}
    )


def build_record(inputs, compiled, billing, pricing, estimate, context, fx, created_at):
    model, kind = compiled["model"], compiled["kind"]
    rates = pricing[kind][model]
    calculation = {
        "schema_version": 3,
        "created_at": created_at,
        **copy.deepcopy(billing),
        "assets": [
            {k: copy.deepcopy(v) for k, v in asset.items() if k in ("id", "kind", "source")}
            | copy.deepcopy(asset.get("metadata", {}))
            for asset in compiled["assets"]
        ],
        "currency": estimate["currency"],
        "pricing": {
            "source": pricing["source"],
            "verified_on": pricing["verified_on"],
            "basis": pricing["basis"],
            "rates": copy.deepcopy(
                rates
                if kind == "image"
                else {
                    compiled["parameters"]["resolution"]: rates[
                        compiled["parameters"]["resolution"]
                    ]
                }
            ),
        },
        "estimate_context": copy.deepcopy(context),
        "fx": copy.deepcopy(fx),
        "notes": copy.deepcopy(estimate.get("notes", [])),
    }
    result = {
        "status": estimate["status"],
        "currency": estimate["currency"],
        "amount": bounds(estimate["amount"]),
        "uncertainties": [],
    }
    from core.pricing import freshness
    calculation['pricing_freshness'] = freshness(pricing)
    if pricing.get('refresh_status'):
        calculation['pricing_refresh'] = pricing['refresh_status']
    if pricing.get('verification_source'):
        calculation['pricing']['verification_source'] = pricing['verification_source']
    if freshness(pricing)['status'] != 'fresh':
        result['uncertainties'].append({'field': 'pricing', 'reason':
                                      '价格快照超过7天或日期无效；刷新未完成，仍按所列历史单价估算。'})
    result['range_is_guaranteed'] = False
    if estimate.get('estimate_quality'):
        result['estimate_quality'] = estimate['estimate_quality']
    for uncertainty in estimate.get('uncertainties', []):
        if uncertainty not in result['uncertainties']:
            result['uncertainties'].append(copy.deepcopy(uncertainty))
    if estimate.get('scenarios'):
        result['scenarios'] = copy.deepcopy(estimate['scenarios'])
        if fx:
            for scenario in result['scenarios']:
                values = scenario['amount']
                scenario['conversion'] = {
                    'currency': 'CNY' if result['currency'] == 'USD' else 'USD',
                    'amount': [round(v * fx['usd_cny'] if result['currency'] == 'USD'
                                     else v / fx['usd_cny'], 6) for v in values]}
    for field in estimate.get("missing_inputs", []):
        reason = (
            "无法可靠确定输出像素，费用未知。"
            if field.endswith("output_dimensions")
            else "未核实本规格的最低计费 Token，仅能计算费用下界，上界未知。"
        )
        result["uncertainties"].append({"field": field, "reason": reason})
    if kind == "image":
        calculation.update(copy.deepcopy(estimate["calculation"]))
        size = compiled["parameters"]["size"]
        if "x" in size:
            width, height = map(int, size.split("x"))
            calculation.update(
                output_dimensions=[width, height],
                output_pixels=width * height,
                pixel_tier="high" if width * height > rates["threshold_pixels"] else "low",
            )
        elif compiled["operation"] != "decompose-layers":
            calculation["pixel_tier"] = "high" if size == "2K" else "low"
        unit = calculation["output_unit_price_range"]
        count = calculation["output_count_range"]
        output_cost = [round(unit[i] * count[i], 6) for i in (0, 1)]
        calculation["formula"] = (
            "output_count * output_unit_price + extra_input_count * extra_input_unit_price"
        )
        calculation["steps"] = [
            {
                "name": "extra_input_count",
                "formula": "max(input_images - 1, 0)",
                "value": calculation["extra_input_images"],
            },
            {
                "name": "extra_input_cost",
                "formula": "extra_input_count * extra_input_unit_price",
                "value": calculation["extra_input_cost"],
            },
            {
                "name": "output_cost",
                "formula": "output_count * output_unit_price",
                "value": bounds(output_cost),
            },
            {
                "name": "total_cost",
                "formula": "output_cost + extra_input_cost",
                "value": copy.deepcopy(result["amount"]),
            },
        ]
        if compiled["operation"] == "decompose-layers":
            result["uncertainties"].append(
                {
                    "field": "output_layers",
                    "reason": "生成前无法确定实际图层数量及各层尺寸，费用按 1～17 份输出和像素档位估算范围。",
                }
            )
    else:
        for key in (
            "target_asset_index",
            "assumed_output_dimensions",
            "output_dimensions_basis",
            "assumed_output_duration",
            "input_video_seconds",
            "frames_per_second",
            "formula_tokens",
            "tokens",
            "minimum_billable_tokens",
            "minimum_tokens_source",
            "minimum_tokens_evidence",
            "output_dimension_candidates",
            "unit_price_per_million_tokens",
            "formula",
        ):
            if key in estimate:
                # 计费输入包含各段视频的秒数；使用独立字段保存总时长。
                target = "total_input_video_seconds" if key == "input_video_seconds" else key
                calculation[target] = copy.deepcopy(estimate[key])
        calculation.setdefault("total_input_video_seconds", sum(billing["input_video_seconds"]))
        calculation.setdefault("frames_per_second", 24)
        calculation["steps"] = [
            {
                "name": "input_video_seconds",
                "formula": "sum(each input video duration)",
                "value": calculation["total_input_video_seconds"],
            },
            {
                "name": "formula_tokens",
                "formula": "ceil((input_seconds + output_seconds) * width * height * fps / 1024)",
                "value": bounds(estimate.get("formula_tokens")),
            },
            {
                "name": "billable_tokens",
                "formula": "max(formula_tokens, ceil(applicable minimum_tokens))",
                "value": bounds(estimate.get("tokens")),
            },
            {
                "name": "total_cost",
                "formula": "billable_tokens * unit_price_per_million_tokens / 1000000",
                "value": copy.deepcopy(result["amount"]),
            },
        ]
        duration = estimate.get("assumed_output_duration")
        if duration and duration[0] != duration[1]:
            result["uncertainties"].append(
                {
                    "field": "output_duration",
                    "reason": "实际输出时长尚未确定，按所记录的输出时长范围计算费用。",
                }
            )
    if fx:
        target = "CNY" if result["currency"] == "USD" else "USD"
        converted = estimate["amount_" + target.lower()]
        result["conversion"] = {
            "currency": target,
            "amount": bounds(converted),
            "usd_cny": fx["usd_cny"],
            "expires_at": fx["expires_at"],
        }
        calculation["steps"].append(
            {
                "name": "currency_conversion",
                "formula": "amount * usd_cny" if target == "CNY" else "amount / usd_cny",
                "value": copy.deepcopy(result["conversion"]),
            }
        )
    return {"input": copy.deepcopy(inputs), "calculation": calculation, "result": result}
