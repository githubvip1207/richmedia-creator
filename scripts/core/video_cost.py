"""视频估价：可核验的规格优先，无法预知的部分给出带依据的情景估算。"""

import copy
import math
from urllib.parse import urlsplit
from core.operations import internal_operation
from core.validation import require, number

RATIOS = ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9']


def official_source(url, provider):
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    domains = {'volcengine': ('docs.volcengine.com', 'ark.volcengine.com', 'console.volcengine.com'),
               'byteplus': ('docs.byteplus.com', 'ai.byteplus.com', 'console.byteplus.com')}
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and parsed.hostname in (*domains[provider], 'bytedance.larkoffice.com'))


def duration_range(compiled, context, source):
    p = compiled['parameters']
    if p['duration'] != -1:
        return [p['duration'], p['duration']]
    if internal_operation(compiled) == 'edit-video' and compiled['model'] == 'seedance-2.5':
        targets = [source] if source else [a for a in compiled['assets'] if a['kind'] == 'video']
        seconds = [a['metadata']['duration'] for a in targets]
        return [max(0, min(seconds) - .4), max(seconds)]
    return [4, 30 if compiled['model'] == 'seedance-2.5' else 15]


def dimension_options(compiled, context, source, table, notes, uncertainties):
    model, p = compiled['model'], compiled['parameters']
    choices = [table(model, p['resolution'], r) for r in RATIOS]
    if 'output_dimensions' in context:
        dims = context['output_dimensions']
        require(isinstance(dims, list) and len(dims) == 2
                and all(type(v) is int and v > 0 for v in dims),
                'output_dimensions must be [width,height]')
        areas = [math.prod(d) for d in choices]
        require(min(areas) * .8 <= math.prod(dims) <= max(areas) * 1.2,
                'output_dimensions conflicts with selected resolution')
        require(.4 <= dims[0] / dims[1] <= 2.5,
                'output_dimensions aspect ratio outside supported range')
        if p['ratio'] in RATIOS:
            expected = table(model, p['resolution'], p['ratio'])
            require(dims == expected, 'output_dimensions conflicts with official ratio table')
        uncertainties.append({'field': 'output_dimensions', 'reason':
                              '输出像素来自补充估算依据；生成后核对实际像素。'})
        return [dims], 'provided_estimate'
    if p['ratio'] in RATIOS:
        return [table(model, p['resolution'], p['ratio'])], 'official_ratio_table'
    if source:
        m = source.get('metadata', {})
        w, h = m.get('display_width', m.get('width')), m.get('display_height', m.get('height'))
        if number(w) and number(h) and w > 0 and h > 0:
            ratio = w / h
            distances = [abs(math.log(ratio / (d[0] / d[1]))) for d in choices]
            nearest = min(range(len(choices)), key=distances.__getitem__)
            # 容纳近似 9:16 的 800×1424 等尺寸，避免整数取整导致拒绝估价。
            if distances[nearest] <= .01:
                return [choices[nearest]], 'source_ratio_and_official_table'
            if model != 'seedance-2.5':
                # 2.0 adaptive 在可选比例中选择；覆盖全部候选而非假定必选最近者。
                uncertainties.append({'field': 'output_dimensions', 'reason':
                                      '模型自动选择标准比例，费用覆盖全部官方候选尺寸。'})
                return choices, 'official_adaptive_candidates'
            areas = [math.prod(d) for d in choices]
            dims = []
            for area in (min(areas), max(areas)):
                width = max(2, round(math.sqrt(area * ratio) / 2) * 2)
                height = max(2, round(math.sqrt(area / ratio) / 2) * 2)
                dims.append([width, height])
            uncertainties.append({'field': 'output_dimensions', 'reason':
                                  '任意比例：保留素材显示比例，按同分辨率官方像素面积范围推算；非官方精确尺寸或保证边界。'})
            return dims, 'source_ratio_area_estimate'
    uncertainties.append({'field': 'output_dimensions', 'reason':
                          '自动比例尚未确定，费用覆盖全部官方候选尺寸。'})
    return choices, 'official_adaptive_candidates'


def minimum_floor(compiled, context, durations, dimensions, price, table, uncertainties):
    provider, model, p = compiled['provider'], compiled['model'], compiled['parameters']
    from core.pricing import freshness
    evidence = price.get('minimum_token_estimation')
    require(isinstance(evidence, dict), 'Supplier pricing snapshot is missing minimum_token_estimation')
    # 官方门槛属于价格配置，不接受调用方在任务入参中填写。
    expected = {'model': model, 'resolution': p['resolution'], 'ratio': p['ratio'], 'duration': p['duration']}
    rules = evidence.get('rules', [])
    require(isinstance(rules, list) and all(isinstance(row, dict) for row in rules),
            'Minimum token pricing rules must be objects')
    matching = [row for row in rules if all(row.get(k) == v for k, v in expected.items())]
    require(len(matching) <= 1, 'Duplicate minimum token pricing rules for this specification')
    if matching:
        row = matching[0]
        require(official_source(row.get('source'), provider), 'Minimum token rule requires official supplier source')
        supplied = row.get('tokens')
        values = supplied if isinstance(supplied, list) else [supplied, supplied]
        require(len(values) == 2 and all(number(v) and v > 0 for v in values)
                and values[0] <= values[1], 'Minimum token range must be [positive lower, positive upper]')
        require(isinstance(supplied, list) or durations[0] == durations[1],
                'Automatic duration needs a verified minimum token range covering the entire duration range')
        if durations == [evidence['anchor_duration']] * 2 and p['ratio'] == evidence['anchor_ratio'] and freshness(evidence)['status'] == 'fresh':
            rounding = evidence.get('rounding_by_model', {}).get(model, evidence['rounding'])
            lower = (evidence['examples'][model][p['resolution']] - rounding) / evidence['rates'][model][p['resolution']] * 1_000_000
            require(values[0] >= lower * .95,
                    'Minimum tokens contradict same-spec official public price example; recheck configuration')
        if freshness(row)['status'] != 'fresh':
            uncertainties.append({'field': 'minimum_billable_tokens', 'reason':
                                  '价格配置中的官方最低用量规则超过7天或缺少核实日期，应重新核对。'})
        return values, {'method': 'configured_official_table', 'source': row['source'],
                        'verified_on': row.get('verified_on'), 'specification': expected}
    if freshness(evidence)['status'] != 'fresh':
        uncertainties.append({'field': 'minimum_tokens_evidence', 'reason':
                              '公开最低价格示例依据超过7天，应重新核对门槛；本次保留历史依据估算。'})
    family = 'seedance-2.5' if model == 'seedance-2.5' else model
    anchor = evidence['examples'][family][p['resolution']]
    anchor_rate = evidence['rates'][family][p['resolution']]
    anchor_dims = table(model, p['resolution'], evidence['anchor_ratio'])
    # 公开示例最低金额为四舍五入值，反推门槛并保留其舍入区间。
    rounding = evidence.get('rounding_by_model', {}).get(model, evidence['rounding'])
    floors = []
    for i, seconds in enumerate(durations):
        area = (min if i == 0 else max)(math.prod(d) for d in dimensions)
        value = (anchor + (-rounding if i == 0 else rounding)) / anchor_rate * 1_000_000
        floors.append(max(1, value * seconds / evidence['anchor_duration'] * area / math.prod(anchor_dims)))
    scaled = durations != [evidence['anchor_duration']] * 2 or any(d != anchor_dims for d in dimensions)
    uncertainties.append({'field': 'minimum_billable_tokens', 'reason':
                          ('价格配置未提供匹配的官方门槛行；由官方5秒示例反推门槛，再按输出时长与像素面积比例外推；外推误差尚未校准。'
                           if scaled else '价格配置未提供匹配的官方门槛行；由官方同规格5秒最低价格示例反推门槛，保留公开金额舍入误差。')})
    return floors, {'method': 'public_example_scaled' if scaled else 'public_example_rounded',
                    'source': evidence['source'],
                    'verified_on': evidence['verified_on'],
                    'extrapolation_error': 'uncalibrated' if scaled else 'not_applicable',
                    'interval_covers': ['published_price_rounding'], 'anchor_duration': evidence['anchor_duration'],
                    'anchor_dimensions': anchor_dims, 'anchor_amount': anchor,
                    'anchor_rate': anchor_rate,
                    'formula': '(published_minimum_price ± rounding) / anchor_rate * 1000000 * output_seconds / 5 * output_area / anchor_area',
                    'table_source': evidence['table_sources']['2.5' if model == 'seedance-2.5' else '2.0']}


def calculate_video_cost(compiled, context, price, fx, table, target):
    from core.pricing import freshness
    provider, model, p = compiled['provider'], compiled['model'], compiled['parameters']
    currency = 'CNY' if provider == 'volcengine' else 'USD'
    require(price.get('currency') == currency and price.get('provider', 'volcengine') == provider,
            'Pricing snapshot supplier/currency mismatch')
    if fx is not None:
        from core.exchange_rate import validate_fx
        validate_fx(fx)
    ctx = copy.deepcopy(context or {})
    require(isinstance(context, (dict, type(None))), 'estimate_context must be an object')
    require(not set(ctx) - {'output_dimensions', 'target_asset_index', 'preferred_duration'},
            'Unknown estimate_context fields')
    uncertainties, notes = [], []
    selected, source = target(compiled, ctx)
    durations = duration_range(compiled, ctx, source)
    dimensions, basis = dimension_options(compiled, ctx, source, table, notes, uncertainties)
    video = [a for a in compiled['assets'] if a['kind'] == 'video']
    seconds = sum(a['metadata']['duration'] for a in video)
    rate = price['video'][model][p['resolution']][int(bool(video))]
    require(number(rate) and rate > 0, 'Invalid token rate')
    tokens = [math.ceil((seconds + durations[i]) *
                       (min if i == 0 else max)(math.prod(d) for d in dimensions) * 24 / 1024)
              for i in (0, 1)]
    out = {'provider': provider, 'currency': currency, 'status': 'estimate',
           'price_verified_on': price['verified_on'], 'source': price['source'], 'basis': price['basis'],
           'missing_inputs': [], 'notes': notes, 'uncertainties': uncertainties,
           'assumed_output_dimensions': dimensions[0], 'output_dimension_candidates': dimensions,
           'output_dimensions_basis': basis, 'assumed_output_duration': durations,
           'input_video_seconds': seconds, 'frames_per_second': 24, 'formula_tokens': tokens[:],
           'formula': '(input_video_seconds + output_seconds) * width * height * 24 / 1024',
           'unit_price_per_million_tokens': rate,
           'unit_price_' + currency.lower() + '_per_million_tokens': rate,
           'pricing_freshness': freshness(price), 'range_is_guaranteed': False}
    if selected is not None:
        out['target_asset_index'] = selected
        if compiled.get('target_asset_id') is not None:
            out['target_asset_id'] = compiled['target_asset_id']
    if video:
        floors, evidence = minimum_floor(compiled, ctx, durations, dimensions, price, table, uncertainties)
        tokens = [max(t, math.ceil(f)) for t, f in zip(tokens, floors)]
        out.update(minimum_billable_tokens=floors,
                   minimum_tokens_source=evidence['source'], minimum_tokens_evidence=evidence)
    evidence_method = out.get('minimum_tokens_evidence', {}).get('method')
    out['estimate_quality'] = ('extrapolated' if evidence_method == 'public_example_scaled'
                               or basis == 'source_ratio_area_estimate' else 'documented_estimate')
    out.update(tokens=tokens, amount=[round(t * rate / 1_000_000, 6) for t in tokens])
    if durations[0] != durations[1]:
        scenarios = []
        preferred = ctx.get('preferred_duration')
        if preferred is not None:
            require(number(preferred) and durations[0] <= preferred <= durations[1],
                    'preferred_duration must fall within actual output duration range')
        for d in sorted(set([durations[0], durations[1]] +
                            [v for v in (5, 10, 15, 20, preferred) if v is not None
                             and durations[0] <= v <= durations[1]])):
            fixed = copy.deepcopy(compiled)
            fixed['parameters']['duration'] = d
            subctx = {k: v for k, v in ctx.items() if k != 'preferred_duration'}
            q = calculate_video_cost(fixed, subctx, price, fx, table, target)
            scenarios.append({'output_seconds': d, 'amount': q['amount'],
                              'basis': 'duration_scenario', 'preferred': d == preferred})
        out['scenarios'] = scenarios
    if out['pricing_freshness']['status'] != 'fresh':
        uncertainties.append({'field': 'pricing', 'reason': '价格快照超过7天或日期无效；已保留原核实日期，应重新核对官方价格。'})
    notes.append('金额是所列假设下的估算范围，不是保证上限；生成后按实际 usage 和媒体规格核对。')
    for target_currency in ('CNY', 'USD'):
        out['amount_' + target_currency.lower()] = (
            out['amount'][:] if currency == target_currency else
            ([round(v * fx['usd_cny'] if currency == 'USD' else v / fx['usd_cny'], 6)
              for v in out['amount']] if fx else None))
    if fx:
        out['fx'] = fx
    return out
