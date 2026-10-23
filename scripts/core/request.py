# 请求编译器：把通用任务规格转换为供应商专属的 API 模板。
# 此处只做离线检查；远程素材尺寸、可访问性和账户权限不能靠编译结果证明。
"""Compile an explicit operation into a validated request."""
import copy
import json
import math
import re
from pathlib import Path
from .assets import inspect_asset
from .operations import internal_operation
from providers import PROVIDERS, resolve_provider

# ROOT 始终指向技能根目录；各供应商使用独立模型 JSON，不按字符串前缀猜测能力。
ROOT = Path(__file__).resolve().parents[2]
CATALOGS = {name: json.loads((ROOT / 'models' / p['catalog']).read_text()) for name,p in PROVIDERS.items()}
RATIOS = ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'adaptive']


# 统一执行前置条件检查，条件不成立时抛出 ValueError，交给 CLI 输出错误摘要。
def require(condition, message):
    if not condition:
        raise ValueError(message)


# 只接受有限的 int/float；排除 bool（虽然它是 int 子类）、NaN 和无穷大。
def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def compile_native_image(spec):
    """Validate the selected supplier's text-to-image body without rewriting it."""
    allowed = {'provider', 'operation', 'original_prompt', 'payload',
               'estimate_context', 'budget_cny', 'budget_usd', 'fx'}
    require(not (set(spec) - allowed), 'Unsupported native request envelope fields')
    provider = spec.get('provider')
    require(provider in ('volcengine', 'byteplus') and spec.get('operation') == 'text-to-image',
            'Native image payload requires a supported supplier and text-to-image')
    internal_operation(spec)
    payload = copy.deepcopy(spec['payload'])
    require(isinstance(payload, dict), 'payload must be an object')
    fields = {'model', 'prompt', 'size', 'output_format', 'response_format', 'watermark',
              'background', 'optimize_prompt_options', 'layer_decomposition'}
    require(not (set(payload) - fields), 'Unsupported native image payload fields: ' + str(sorted(set(payload) - fields)))
    models = CATALOGS[provider]['models']
    alias = next((k for k, v in models.items() if v['id'] == payload.get('model')), None)
    require(alias is not None and 'text-to-image' in models[alias]['operations'],
            'payload.model must be an exact image model ID belonging to the selected supplier')
    prompt = payload.get('prompt')
    require(isinstance(prompt, str) and bool(prompt.strip()), 'payload.prompt is required')
    # Omitted fields use API defaults for billing/download metadata only; never insert them into payload.
    params = {'size': '2K', 'output_format': 'jpeg', 'response_format': 'url',
              'watermark': True, 'background': 'opaque',
              'optimize_prompt_options': {'mode': 'standard'}}
    params.update({k: v for k, v in payload.items() if k in params})
    from .costing import compile_cost_inputs
    compile_cost_inputs({'provider': provider, 'model': alias, 'operation': 'text-to-image',
                         'size': params['size']})
    require(params['output_format'] in models[alias]['formats'], 'Invalid output_format')
    require(params['response_format'] in ('url', 'b64_json'), 'Invalid response_format')
    require(type(params['watermark']) is bool, 'watermark must be boolean')
    require(params['background'] == 'opaque', 'Text-to-image background must be opaque')
    modes = [{'mode': 'standard'}] + ([{'mode': 'fast'}] if alias.endswith('pro') else [])
    require(params['optimize_prompt_options'] in modes, 'Invalid optimize_prompt_options')
    require(payload.get('layer_decomposition', False) is False, 'Text-to-image cannot decompose layers')
    for key in ('budget_cny', 'budget_usd'):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + ' must be positive')
    return {'provider': provider, 'model': alias, 'kind': 'image',
            'operation': 'text-to-image', 'prompt': prompt, 'assets': [],
            'parameters': params, 'payload_template': payload,
            'warnings': [], 'quantity': 1, 'optimizer': None,
            'original_prompt': spec.get('original_prompt')}


def compile_native_request(spec, measured_assets=None):
    """Validate the native API body; keep it unchanged for the actual POST."""
    if spec.get('operation') == 'text-to-image':
        return compile_native_image(spec)
    allowed = {'provider', 'operation', 'mode', 'original_prompt', 'payload', 'optimizer',
               'estimate_context', 'budget_cny', 'budget_usd', 'fx'}
    require(not (set(spec) - allowed), 'Unsupported native request envelope fields')
    require(spec.get('provider') == 'volcengine', 'Native payload requires Volcengine')
    op = internal_operation(spec)
    body = copy.deepcopy(spec.get('payload'))
    require(isinstance(body, dict), 'payload must be an object')
    models = CATALOGS['volcengine']['models']
    alias = next((k for k, v in models.items() if v['id'] == body.get('model')), None)
    require(alias is not None, 'payload.model must be an exact supported Volcengine model ID')
    video = models[alias]['kind'] == 'video'
    assets = []
    evidence = measured_assets
    if evidence is not None:
        require(isinstance(evidence, list), 'Measured cost assets must be an array')

    def asset(kind, source, role):
        require(isinstance(source, str) and source.startswith(('https://', 'asset://')),
                'Native media URLs must be HTTPS or supported supplier asset IDs; do not persist Base64 or local paths in payload')
        metadata = {}
        index = len(assets)
        if evidence is not None:
            require(index < len(evidence) and evidence[index].get('kind') == kind
                    and evidence[index].get('source') == source,
                    'Native payload media differs from measured cost assets; re-estimate and confirm')
            metadata = {k: v for k, v in evidence[index].items() if k not in ('id', 'kind', 'source')}
        # API roles are sufficient for local validation; business purposes stay in request.json.
        item = {'kind': kind, 'source': source, 'role': role, 'purpose': role, 'metadata': metadata}
        if source.startswith('asset://'):
            item['provenance'] = {'provider': 'volcengine'}
        assets.append(item)

    if video:
        fields = {'model', 'content', 'resolution', 'ratio', 'duration', 'generate_audio',
                  'watermark', 'output_format', 'return_last_frame', 'execution_expires_after',
                  'priority', 'callback_url', 'safety_identifier', 'service_tier', 'omni_reference_task_type'}
        require(not (set(body) - fields), 'Unsupported native video payload fields')
        # Explicit output settings avoid estimating one set of defaults and POSTing another.
        require({'resolution', 'ratio', 'duration', 'generate_audio', 'watermark'} <= set(body),
                'Native video payload requires explicit resolution, ratio, duration, generate_audio and watermark')
        content = body.get('content')
        require(isinstance(content, list) and bool(content), 'payload.content must be a nonempty array')
        texts = []
        for item in content:
            require(isinstance(item, dict), 'Each content item must be an object')
            if item.get('type') == 'text':
                require(set(item) == {'type', 'text'} and isinstance(item.get('text'), str), 'Invalid text content')
                texts.append(item['text'])
            else:
                key = item.get('type')
                require(key in ('image_url', 'video_url', 'audio_url') and set(item) == {'type', key, 'role'},
                        'Invalid native media content or missing role')
                require(isinstance(item[key], dict) and set(item[key]) == {'url'}, 'Invalid native media URL object')
                asset(key.split('_')[0], item[key]['url'], item['role'])
        require(len(texts) == 1 and bool(texts[0].strip()), 'Provide exactly one nonempty text content item')
        prompt = texts[0]
        params = {k: copy.deepcopy(v) for k, v in body.items() if k not in ('model', 'content', 'service_tier', 'omni_reference_task_type')}
        require(body.get('service_tier', 'default') == 'default', 'Only default service tier is implemented')
        expected = {'reference-to-video': 'reference', 'edit-video': 'edit', 'extend-video': 'extend'}.get(op)
        if alias == 'seedance-2.5' and expected:
            require(body.get('omni_reference_task_type') == expected, 'Native task type must match operation/mode')
        else:
            require('omni_reference_task_type' not in body, 'Task type does not apply to this model/operation')
        require(alias == 'seedance-2.5' or 'output_format' not in body,
                'Seedance 2.0 has fixed MP4 output; omit output_format')
    else:
        fields = {'model', 'prompt', 'image', 'size', 'output_format', 'response_format',
                  'watermark', 'background', 'optimize_prompt_options', 'layer_decomposition'}
        require(not (set(body) - fields), 'Unsupported native image payload fields')
        require(body.get('layer_decomposition', False) is (op == 'decompose-layers'),
                'layer_decomposition must match operation')
        images = body.get('image')
        images = [images] if isinstance(images, str) else images
        require(isinstance(images, list), 'payload.image must be a URL or URL array')
        for source in images:
            asset('image', source, 'reference_image')
        prompt = body.get('prompt', '')
        # These are API defaults for validation/billing, never inserted into the native body.
        params = {'size': 'auto' if op == 'decompose-layers' else '2K',
                  'output_format': 'jpeg', 'response_format': 'url', 'watermark': True,
                  'background': 'opaque', 'optimize_prompt_options': {'mode': 'standard'}}
        params.update({k: copy.deepcopy(v) for k, v in body.items() if k in params})
        params['ratio'] = 'auto' if op == 'decompose-layers' else '1:1'
    if evidence is not None:
        require(len(assets) == len(evidence), 'Native payload media differs from measured cost assets')
    validation = {k: copy.deepcopy(v) for k, v in spec.items() if k not in ('payload',)}
    validation.update(model=alias, prompt=prompt, parameters=params, assets=assets)
    compiled = compile_request(validation)
    # The legacy compiler is used for checks only: its defaults/prompt additions are not posted.
    compiled.update(payload_template=body, prompt=prompt, native_payload=True)
    if not video:
        compiled['parameters'].pop('ratio', None)
    return compiled


# 校验顶层字段、供应商模型、操作、提示词及素材，随后分别编译视频或图片请求。
# 返回 API 模板、参数、确认单选项和未验证事项；模板中的素材索引稍后才替换为实际内容。
def compile_request(spec, measured_assets=None):
    require(isinstance(spec, dict), 'Request must be an object')
    if 'payload' in spec:
        return compile_native_request(spec, measured_assets)
    # 先拒绝未知顶层字段，避免忽略拼写错误或把未审查参数送至供应商。
    unknown = set(spec) - {'provider', 'model', 'operation', 'mode', 'prompt', 'original_prompt', 'parameters',
                           'assets', 'optimizer', 'estimate_context', 'budget_cny', 'budget_usd', 'fx'}
    require(not unknown, 'Unknown request fields: ' + str(sorted(unknown)))
    provider = resolve_provider(spec)
    catalog = CATALOGS[provider]
    alias = spec.get('model')
    # 只在当前供应商目录内解析版本 ID；相似的国内/海外模型名不能混用。
    if alias not in catalog['models']:
        alias = next((k for k, v in catalog['models'].items() if v['id'] == alias), None)
    require(alias is not None, 'Unknown model; run models')
    m = catalog['models'][alias]
    op = internal_operation(spec)
    require(spec['operation'] in m['operations'], 'Operation not supported by model')
    prompt = spec.get('prompt', '')
    require(isinstance(prompt, str), 'prompt must be a string')
    require(bool(prompt.strip()) or op == 'decompose-layers', 'An optimized prompt is required')
    p = copy.deepcopy(spec.get('parameters', {}))
    require(isinstance(p, dict), 'parameters must be an object')
    a = [inspect_asset(x) for x in spec.get('assets', [])]
    # asset:// 仅适用于对应供应商/账户；来源字段匹配也不能单独证明账户信任资格。
    for item in a:
        if item['transport'] == 'asset':
            require(item.get('provenance',{}).get('provider') == provider,
                    'asset:// IDs are supplier/account scoped: specify matching provenance.provider; never reuse across suppliers')
    require(not (m['kind'] == 'image' and any(x['transport'] == 'asset' for x in a)),
            'Seedream image API accepts URLs/Base64, not asset:// IDs')
    warnings = []


    # 填充默认值并校验类型及范围；运行参数保存在 p 中用于构造请求。
    def setting(key, default, choices, predicate=None):
        if key not in p:
            p[key] = default
        require(predicate(p[key]) if predicate else p[key] in choices, 'Invalid ' + key + ': ' + str(p[key]))

    # 视频参数路径：仅开放经过适配的字段，明确限制编辑、延长和首尾帧模式。
    if m['kind'] == 'video':
        allowed = {'resolution', 'ratio', 'duration', 'generate_audio', 'watermark', 'output_format',
                   'return_last_frame', 'execution_expires_after', 'priority', 'callback_url', 'safety_identifier'}
        require(not (set(p) - allowed), 'Unsupported video parameters: ' + str(sorted(set(p) - allowed)))
        # 延长必须显式提供清晰度和时长，防止普通生成的低成本默认值意外截短需求。
        if op == 'extend-video':
            require('resolution' in p and 'duration' in p, 'Extension needs explicit resolution and duration; do not apply low-cost creation defaults')
        setting('resolution', '480p', m['resolutions'])
        # 2.5 编辑/延长/首尾帧按模型规则锁定 adaptive；普通文生视频默认 16:9。
        locked = alias == 'seedance-2.5' and op in ('first-frame', 'first-last-frame', 'edit-video', 'extend-video')
        setting('ratio', 'adaptive' if op != 'text-to-video' else '16:9', ['adaptive'] if locked else RATIOS)
        edit25 = alias == 'seedance-2.5' and op == 'edit-video'
        # 2.5 编辑只允许 -1；其他任务允许自动时长或从四秒到模型上限的整数。
        durations = [-1] if edit25 else [-1] + list(range(4, m['max_duration'] + 1))
        setting('duration', -1 if edit25 else 4, durations, lambda v: type(v) is int and v in durations)
        # 延长默认保留音轨需求；普通生成默认无可选音频，布尔字段必须是真正的 bool。
        for key, default in [('generate_audio', op == 'extend-video'), ('watermark', True), ('return_last_frame', False)]:
            setting(key, default, [False, True], lambda v: type(v) is bool)
        setting('output_format', 'mp4', m['formats'])
        setting('execution_expires_after', 172800, 'integer 3600..259200', lambda v: type(v) is int and 3600 <= v <= 259200)
        setting('priority', 0, list(range(10)), lambda v: type(v) is int and 0 <= v <= 9)
        for key in ('callback_url', 'safety_identifier'):
            setting(key, None, 'optional HTTPS URL' if key == 'callback_url' else 'optional ASCII string <=64 chars',
                    lambda v, k=key: v is None or (isinstance(v, str) and
                    (v.startswith('https://') if k == 'callback_url' else v.isascii() and 0 < len(v) <= 64)))
        for x in a:
            kind = x['kind']
            x.setdefault('role', 'reference_' + kind)
            require(x['role'] in (['reference_image', 'first_frame', 'last_frame'] if kind == 'image'
                                  else ['reference_' + kind]), 'Invalid asset role')
        # 素材模式互斥：纯文本不能带素材；首尾帧必须按角色顺序且不能夹杂多模态参考。
        if op == 'text-to-video':
            require(not a, 'text-to-video must not include assets')
        elif op in ('first-frame', 'first-last-frame'):
            expected = ['first_frame'] if op == 'first-frame' else ['first_frame', 'last_frame']
            require([x['role'] for x in a] == expected and all(x['kind'] == 'image' for x in a),
                    'First frame and multimodal reference modes cannot be mixed; supply first_frame, then last_frame')
        else:
            require(bool(a) and all(x['role'].startswith('reference_') for x in a), 'Reference operation requires reference assets')
            if op in ('edit-video', 'extend-video'):
                require(any(x['kind'] == 'video' for x in a), 'Editing/extension needs a video')
            require(alias == 'seedance-2.5' or any(x['kind'] != 'audio' for x in a), '2.0 cannot use audio-only reference')
        # 按类型检查数量、单段时长和总时长；所有输入视频/音频时长必须是测量值。
        for kind, limit in m['limits'].items():
            subset = [x for x in a if x['kind'] == kind]
            require(len(subset) <= limit, 'Too many ' + kind + ' assets')
            if kind in ('video', 'audio'):
                durations_in = [x['metadata'].get('duration') for x in subset]
                require(all(number(d) and (4 if edit25 and kind == 'video' else 2) <= d <= m['max_duration'] for d in durations_in),
                        'Provide measured duration for each ' + kind + '; outside model input range')
                require(sum(durations_in) <= m['max_duration'], 'Total ' + kind + ' duration exceeds model limit')
        # 2.5 多模态意图由操作统一映射，避免提示词说编辑而运行参数仍按普通参考执行。
        if alias == 'seedance-2.5' and op in ('reference-to-video', 'edit-video', 'extend-video'):
            task_type = {'reference-to-video': 'reference', 'edit-video': 'edit', 'extend-video': 'extend'}[op]
            p['omni_reference_task_type'] = task_type
        p['service_tier'] = 'default'
        # 先用素材索引构建可审计模板，待提交时再将索引替换为地址或 Base64。
        content = [{'type': 'text', 'text': prompt}]
        for i, x in enumerate(a):
            key = x['kind'] + '_url'
            content.append({'type': key, key: {'url': {'asset_index': i}}, 'role': x['role']})
        payload = {'model': m['id'], 'content': content, **{k:v for k,v in p.items() if v is not None}}
        if alias != 'seedance-2.5':
            # 2.0 输出固定为 MP4；确认单可说明格式，但请求不能携带其不支持的字段。
            payload.pop('output_format', None)  # 2.0 format is fixed MP4, no API parameter.
    else:
        # 图片参数路径：禁止原生组图等不受支持字段，输出一次请求始终为一张。
        allowed = {'size', 'ratio', 'output_format', 'response_format', 'watermark', 'background', 'optimize_prompt_options'}
        require(not (set(p) - allowed), 'Unsupported image parameters: ' + str(sorted(set(p) - allowed)))
        require(all(x['kind'] == 'image' for x in a), 'Images only')
        require(len(a) <= m['max_images'], 'At most 10 reference images')
        # 图生图统一接受 1..10 张参考图；具体编辑意图由提示词表达。
        counts = {'text-to-image': (0, 0), 'image-to-image': (1, 10), 'decompose-layers': (1, 1)}
        lo, hi = counts[op]
        require(lo <= len(a) <= hi, 'Incorrect image count for ' + op)
        # 坐标使用 0..999 的整数归一化空间；bbox 必须从左上到右下且面积非零。
        for tag, body in re.findall(r'<(point|bbox)>(.*?)</\1>', prompt):
            try:
                coords = list(map(int,body.split()))
            except ValueError:
                raise ValueError('Coordinates must be normalized integers') from None
            require(len(coords) == (2 if tag == 'point' else 4) and all(0 <= n <= 999 for n in coords),
                    'Coordinates must be 0..999 with 2 point or 4 bbox values')
            if tag == 'bbox':
                require(coords[0] < coords[2] and coords[1] < coords[3], 'bbox corners must be ordered and nonempty')
        # 拆分可用 auto；标准图片允许尺寸档位或受总像素/宽高比限制的准确 WxH。
        sizes = m['sizes'] + (['auto'] if op == 'decompose-layers' else [])
        # 接受模型尺寸档位；普通生成也允许符合总像素与比例限制的 WxH。
        # 图层拆分不接受准确像素；解析失败、零高度或像素越界均返回 False。
        def valid_size(v):
            if v in sizes:
                return True
            if not isinstance(v, str) or op == 'decompose-layers':
                return False
            try:
                w, h = map(int, v.split('x'))
                return 921600 <= w*h <= 4624220 and 1/16 <= w/h <= 16
            except (ValueError, ZeroDivisionError):
                return False
        setting('size', 'auto' if op == 'decompose-layers' else '1K', sizes + ['WxH within documented pixel/ratio limits'], valid_size)
        image_ratios = ['21:9', '16:9', '3:2', '4:3', '1:1', '3:4', '2:3', '9:16']
        # 图片比例必须在准备前选定；只有图层拆分跟随输入使用 auto。
        if op == 'decompose-layers':
            setting('ratio', 'auto', ['auto'])
        else:
            require('ratio' in p, 'Choose an image composition ratio from the prompt before preparing the plan')
            setting('ratio', p['ratio'], image_ratios)
        setting('output_format', 'png', m['formats'])
        setting('response_format', 'url', ['url', 'b64_json'])
        setting('watermark', False, [False, True], lambda v: type(v) is bool)
        setting('background', 'opaque', ['opaque', 'transparent'])
        # 透明输出必须同时满足单张输入、确认存在 Alpha、PNG 和受支持的编辑模式。
        if p['background'] == 'transparent':
            require(op == 'image-to-image' and len(a) == 1 and p['output_format'] == 'png'
                    and a[0]['metadata'].get('has_alpha') is True,
                    'Transparent output needs a single verified alpha-channel input, PNG output, image editing mode')
        mode = {'mode': 'standard'}
        setting('optimize_prompt_options', mode, [{'mode': 'standard'}] + ([{'mode': 'fast'}] if alias.endswith('pro') else []))
        # ratio 不发送给图片 API，而是追加为构图文字；其余已校验字段直接固定进模板。
        payload = {'model': m['id'], **{k:v for k,v in p.items() if k != 'ratio'}, 'layer_decomposition': op == 'decompose-layers'}
        if p['ratio'] != 'auto':
            prompt = (prompt.rstrip() + '\n构图比例偏好：' + p['ratio'] + '。').strip()
        if prompt:
            payload['prompt'] = prompt
        if a:
            payload['image'] = [{'asset_index': i} for i in range(len(a))]
    # 只对已有事实做离线边界检查；缺少远程尺寸时留警告，不把未测事实当作通过。
    # Validate facts available without fetching remote media; absent remote facts stay visible warnings.
    for x in a:
        meta = x['metadata']
        for k in ('width', 'height', 'bytes'):
            if k in meta:
                require(number(meta[k]) and meta[k] > 0, 'Invalid asset metadata ' + k)
        # 检查素材字节数上限；没有提供远程大小时不能据此证明远程文件满足限制。
        size_limit = (30 if x['kind'] == 'image' else 200 if x['kind'] == 'video' else 15) * 1024*1024
        require(meta.get('bytes', 0) <= size_limit, 'Asset exceeds size limit')
        if 'width' in meta and 'height' in meta:
            w,h = meta['width'],meta['height']
            if m['kind'] == 'video' and x['kind'] in ('image', 'video'):
                require(0.4 <= w/h <= 2.5 and 300 <= min(w,h) and max(w,h) <= 6000, 'Video-reference aspect/dimensions out of range')
                if x['kind'] == 'video':
                    require(407696 <= w*h <= 8295044, 'Reference video pixel count out of range')
            elif m['kind'] == 'image':
                require(1/16 <= w/h <= 16 and 14 < min(w,h) and w*h <= 36000000, 'Image dimensions out of range')
                if op == 'decompose-layers':
                    require(w*h >= 262144, 'Layer input must be at least 512x512 total pixels')
        # 保留未验证尺寸和远程字节不固定的警告，提醒批准前还需要实际素材检查。
        elif x['kind'] != 'audio':
            warnings.append('Unverified input dimensions: ' + x['source'])
        if x['transport'] != 'local-base64':
            warnings.append('Remote/asset input bytes are not pinned; verify URL accessibility, media format and provenance before asking for approval: ' + x['source'])
    # 优化器记录是调用约束，只有代理实际应用 sd25-pe 后才允许填写 applied。
    if alias == 'seedance-2.5':
        optimizer = spec.get('optimizer', {})
        require(optimizer.get('skill') == 'sd25-pe' and optimizer.get('status') == 'applied',
                'Seedance 2.5 requires an sd25-pe optimized prompt; record optimizer skill/status')
    for key in ('budget_cny','budget_usd'):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + ' must be positive')
    return {'provider': provider, 'model': alias, 'kind': m['kind'], 'operation': spec['operation'],
            **({'mode': spec['mode']} if spec.get('mode') is not None else {}),
            'prompt': prompt, 'assets': a, 'parameters': p,
            'payload_template': payload, 'warnings': warnings, 'quantity': 1,
            'optimizer': spec.get('optimizer'), 'original_prompt': spec.get('original_prompt')}
