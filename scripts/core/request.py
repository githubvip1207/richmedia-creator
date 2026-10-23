# 原生请求入口：校验供应商 API 请求，不改写已确认提示词。
# 此处只做离线检查；远程素材尺寸、可访问性和账户权限不能靠编译结果证明。
"""Compile an explicit operation into a validated request."""
import copy
import json
import math
from pathlib import Path
from .operations import internal_operation
from providers import PROVIDERS

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
    # The skill intentionally exposes a narrower contract than the supplier API.
    require('size' in payload, 'payload.size is required; resolve the documented default before submission')
    fixed = {'output_format': 'png', 'response_format': 'url', 'watermark': False,
             'background': 'opaque', 'layer_decomposition': False}
    for key, value in fixed.items():
        require(key in payload and type(payload[key]) is type(value) and payload[key] == value,
                'Text-to-image requires ' + key + '=' + str(value))
    require('optimize_prompt_options' not in payload, 'Text-to-image must omit optimize_prompt_options')
    params = {'size': payload['size'], **fixed}
    from .cost_quote import compile_cost_inputs
    compile_cost_inputs({'provider': provider, 'model': alias, 'operation': 'text-to-image',
                         'size': params['size']})
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
    from .legacy_request import compile_request as validate_legacy
    compiled = validate_legacy(validation)
    # The legacy compiler is used for checks only: its defaults/prompt additions are not posted.
    compiled.update(payload_template=body, prompt=prompt, native_payload=True)
    if not video:
        compiled['parameters'].pop('ratio', None)
    return compiled


def compile_request(spec, measured_assets=None):
    """Compile only the provider-native envelope documented by this skill."""
    require(isinstance(spec, dict), 'Request must be an object')
    require('payload' in spec, 'Submission requires a provider-native payload; legacy request format is not supported')
    return compile_native_request(spec, measured_assets)
