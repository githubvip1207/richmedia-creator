# 刊例价估算：使用所选供应商的独立价目表，区分原币、换算金额和未知上界。
# 公式与快照只能用于预估，不是实际账单，也不是供应商侧的硬性支出限制。
"""Public list-price estimates, never an actual bill or guaranteed spending cap."""
import json
import math
from .request import ROOT, require, number
from providers import get_provider
from .operations import internal_operation

# 视频尺寸查表按比例位置对应；2.0 的部分 480p 映射在后面单独覆盖。
RATIOS = ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9']
DIMENSIONS = {
    '480p': [(854,480),(752,560),(640,640),(560,752),(480,854),(992,432)],
    '720p': [(1280,720),(1112,834),(960,960),(834,1112),(720,1280),(1470,630)],
    '1080p': [(1920,1080),(1664,1248),(1440,1440),(1248,1664),(1080,1920),(2206,946)],
    '4k': [(3840,2160),(3326,2494),(2880,2880),(2494,3326),(2160,3840),(4398,1886)]}


def table_dimensions(model, resolution, ratio):
    dims = DIMENSIONS[resolution][RATIOS.index(ratio)]
    if resolution == '480p' and model != 'seedance-2.5':
        dims = {'16:9': (864,496), '9:16': (496,864)}.get(ratio, dims)
    return list(dims)


def target_asset(compiled, context):
    """Select a deterministic source; the selector is an estimate input, not an API control."""
    assets, operation = compiled['assets'], internal_operation(compiled)
    if operation in ('first-frame', 'first-last-frame'):
        candidates = [0] if assets else []
    elif operation in ('edit-video', 'extend-video'):
        candidates = [i for i, a in enumerate(assets) if a['kind'] == 'video']
    else:
        candidates = []
    selected = context.get('target_asset_index')
    if selected is not None:
        require(type(selected) is int and selected in candidates,
                'target_asset_index must identify the first frame or an editing/extension source video')
        return selected, assets[selected]
    if len(candidates) == 1:
        return candidates[0], assets[candidates[0]]
    return None, None


def adaptive_dimensions(compiled, source):
    """Only infer documented 2.5 source-preserving cases with a known table ratio."""
    if compiled['provider'] not in ('volcengine', 'byteplus') or compiled['model'] != 'seedance-2.5' or source is None:
        return None
    metadata = source.get('metadata', {})
    width, height = metadata.get('width'), metadata.get('height')
    if not (number(width) and number(height) and width > 0 and height > 0):
        return None
    for ratio in RATIOS:
        numerator, denominator = map(int, ratio.split(':'))
        known_ratios = [(numerator, denominator)] + [table_dimensions(compiled['model'], resolution, ratio)
                         for resolution in DIMENSIONS if resolution != '4k']
        if any(width * h == height * w for w, h in known_ratios):
            return table_dimensions(compiled['model'], compiled['parameters']['resolution'], ratio)
    return None


# 按已编译任务的供应商加载独立价目表，验证币种、可选汇率和估算上下文。
# 图片按张数/像素计价；视频按输入加输出时长及像素估算 Token，缺少门槛时保持上界未知。
def estimate(compiled, context=None, pricing=None, fx=None):
    provider = compiled['provider']
    info = get_provider(provider)
    price = pricing or json.loads((ROOT / 'models' / info['pricing']).read_text())
    currency = info['currency']
    # 不允许把人民币快照用于美元供应商，或仅因模型别名一致就共用不同供应商的价格。
    require(price.get('currency') == currency and price.get('provider',provider) == provider,
            'Pricing snapshot supplier/currency mismatch')
    # 汇率结构与到期时间统一校验；不按核验日期推算有效期。
    if fx is not None:
        from .envfile import validate_fx
        validate_fx(fx)
    ctx = {} if context is None else context
    require(isinstance(ctx, dict), 'estimate_context must be an object')
    require(not (set(ctx) - {'output_dimensions', 'minimum_billable_tokens', 'minimum_tokens_source',
                            'target_asset_index'}), 'Unknown estimate_context fields')
    out = {'provider':provider, 'currency': currency, 'price_verified_on': price['verified_on'], 'source': price['source'],
           'basis': price['basis'], 'tokens': None, 'amount': None, 'missing_inputs': [],
           'notes': ['估算不是账单或硬预算上限；实际用量以 API usage、实付金额以账户账单为准。']}
    # 在原币估算完成后补充人民币/美元视图，仅使用用户提供并已通过检查的汇率。
    # 保留 None 表示未知金额；没有汇率时不猜测兑换率，也不把未知当作零。
    def finish():
        amount = out['amount']
        out['amount_cny'] = amount if currency == 'CNY' else ([round(v*fx['usd_cny'],6) if v is not None else None for v in amount] if fx and amount else None)
        out['amount_usd'] = amount if currency == 'USD' else ([round(v/fx['usd_cny'],6) if v is not None else None for v in amount] if fx and amount else None)
        if fx:
            out['fx'] = fx
        if currency == 'USD' and not fx:
            out['notes'].append('美元原币估算；没有有效且未过期的汇率，不进行人民币换算，不能直接与人民币数字比较大小。')
        return out
    model, p, assets = compiled['model'], compiled['parameters'], compiled['assets']
    # 图片按输出像素档位与额外参考图计价；Token 没有可靠调用前估算，不填假定数值。
    if compiled['kind'] == 'image':
        r = price['image'][model]
        extra = max(0, len(assets)-1) * r['input_after_first']
        # 拆分前不知道图层数和每层像素，使用一份底图至十七份输出的费用区间。
        if compiled['operation'] == 'decompose-layers':
            lo,hi = r['layer']
            # Actual layer count and per-layer pixel tier are unknown before inference.
            out['amount'] = [round(lo+extra,6), round(17*hi+extra,6)]
            out['notes'].append('图层拆分按实际输出的底图/图层分别计价，最多17张；这里覆盖1..17张与全部像素档位。')
        else:
            size = p['size']
            # 1K 与 1.5K 采用低像素档，2K 采用高像素档；准确尺寸按供应商阈值判断。
            if size in ('1K', '1.5K'):
                lo = hi = r['single'][0]
            elif size == '2K':
                lo = hi = r['single'][1]
            else:
                w,h = map(int,size.split('x'))
                lo = hi = r['single'][int(w*h > r['threshold_pixels'])]
            out['amount'] = [round(lo+extra,6), round(hi+extra,6)]
        out['calculation'] = {'size': p['size'], 'input_images': len(assets),
                              'extra_input_images': max(0, len(assets)-1),
                              'extra_input_unit_price': r['input_after_first'], 'extra_input_cost': extra,
                              'output_count_range': [1,17] if compiled['operation'] == 'decompose-layers' else [1,1],
                              'output_unit_price_range': r['layer'] if compiled['operation'] == 'decompose-layers' else [lo,hi]}
        out['status'] = 'estimate'
        out['notes'].append('图片 Token 无可靠的调用前估算公式；显示为未知。图片费用按输入/输出张数与像素档位计算，不按此未知 Token 计费。')
        return finish()
    # 有无输入视频影响费率；此外输入视频秒数还会进入 Token 数量，二者分别计算。
    video = [a for a in assets if a['kind'] == 'video']
    rates = price['video']
    rate = rates[model][p['resolution']][int(bool(video))]
    require(number(rate) and rate > 0, 'Invalid token rate')
    out['unit_price_per_million_tokens'] = rate
    out['unit_price_'+currency.lower()+'_per_million_tokens'] = rate
    duration = p['duration']
    selected_index, source = target_asset(compiled, ctx)
    if selected_index is not None:
        out['target_asset_index'] = selected_index
    if duration == -1:
        if internal_operation(compiled) == 'edit-video' and model == 'seedance-2.5':
            targets = [source] if source is not None else video
            duration_range = [max(0, min(a['metadata']['duration'] for a in targets) - 0.4),
                              max(a['metadata']['duration'] for a in targets)]
            if source is None:
                out['notes'].append('未指定多视频中的编辑目标，自动时长范围覆盖所有候选；可提供 target_asset_index 明确估算目标。')
        else:
            duration_range = [4, 30 if model == 'seedance-2.5' else 15]
    else:
        duration_range = [duration, duration]
    dims = ctx.get('output_dimensions')
    if dims is not None:
        require(isinstance(dims, list) and len(dims) == 2 and all(type(d) is int and d > 0 for d in dims),
                'output_dimensions must be [width,height]')
        out['output_dimensions_basis'] = 'provided_estimate'
        out['notes'].append('输出像素为有依据的估算输入，不是额外 API 参数或准确输出保证。')
    elif p['ratio'] in RATIOS:
        dims = table_dimensions(model, p['resolution'], p['ratio'])
        out['output_dimensions_basis'] = 'official_ratio_table'
    else:
        dims = adaptive_dimensions(compiled, source)
        if dims is not None:
            out['output_dimensions_basis'] = 'source_ratio_and_official_table'
            out['notes'].append('2.5 首帧/首尾帧或编辑/延长按目标素材比例查官方像素表，仅用于估算，不直接复用输入像素。')
    if dims is None:
        out['status'] = 'unknown'
        out['missing_inputs'] = ['estimate_context.output_dimensions']
        out['assumed_output_duration'] = duration_range
        out['notes'].append('无法可靠确定 adaptive 输出像素；多视频编辑/延长先明确 target_asset_index，或按官方依据提供 estimate_context.output_dimensions，不能猜测。')
        return finish()
    # 公式把全部输入视频秒数与输出秒数相加，再乘像素和 24 FPS，最后向上取整。
    input_seconds = sum(a['metadata']['duration'] for a in video)
    tokens = [math.ceil((input_seconds+d) * dims[0] * dims[1] * 24 / 1024) for d in duration_range]
    out.update({'assumed_output_dimensions': list(dims), 'assumed_output_duration': duration_range,
                'input_video_seconds': input_seconds, 'frames_per_second': 24, 'formula_tokens': list(tokens), 'formula': '(input_video_seconds + output_seconds) * width * height * 24 / 1024'})
    if video:
        minimum = ctx.get('minimum_billable_tokens')
        # 含视频输入但未独立核验最低计费门槛时，公式只构成下界，上界明确保留 None。
        if minimum is None:
            out['status'] = 'lower_bound'
            out['missing_inputs'] = ['estimate_context.minimum_billable_tokens', 'estimate_context.minimum_tokens_source']
            tokens = [tokens[0], None]
            out['notes'].append('含输入视频存在最低计费 Token；尚未核对本规格的最低用量，金额仅为公式下界，上界未知，不可作为总价或预算上限。')
        else:
            require(isinstance(ctx.get('minimum_tokens_source'), str)
                    and ctx['minimum_tokens_source'].startswith('https://'),
                    'Minimum billable tokens need an official table/calculator source URL')
            if isinstance(minimum, list):
                require(len(minimum) == 2 and all(number(v) and v > 0 for v in minimum)
                        and minimum[0] <= minimum[1], 'Minimum token range must be [positive lower, positive upper]')
                floors = minimum
            else:
                require(number(minimum) and minimum > 0, 'Minimum billable tokens must be positive')
                require(duration_range[0] == duration_range[1],
                        'Automatic duration needs a verified minimum token range covering the entire duration range')
                floors = [minimum, minimum]
            tokens = [max(t, math.ceil(floor)) for t, floor in zip(tokens, floors)]
            out['status'] = 'estimate'
            out['minimum_billable_tokens'] = minimum
            out['minimum_tokens_source'] = ctx['minimum_tokens_source']
    else:
        out['status'] = 'estimate'
    out['tokens'] = tokens
    out['amount'] = [round(t*rate/1_000_000,6) if t is not None else None for t in tokens]
    out['notes'].append('根据官方公式和像素表估算，帧处理/取整会有偏差；输入图片/音频不按文字 Token 粗算。')
    return finish()
