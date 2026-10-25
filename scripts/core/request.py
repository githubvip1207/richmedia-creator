# 原生请求入口：校验供应商 API 请求，不改写已确认提示词。
# 此处只做离线检查；远程素材尺寸、可访问性和账户权限不能靠编译结果证明。
"""Compile an explicit operation into a validated request."""
import copy
import json
import math
import re
from pathlib import Path
from .operations import internal_operation, require_supported_operation
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


def validate_edit_coordinates(prompt, *, allow_point=True):
    """Validate explicit interaction tags without changing the confirmed text."""
    require(allow_point or not re.search(r'</?point\b', prompt),
            'Layer decomposition supports bbox region tags only')
    pattern = r'<(point|bbox)>(.*?)</\1>'
    remainder = re.sub(pattern, '', prompt, flags=re.S)
    require(not re.search(r'</?(?:point|bbox)\b', remainder), 'Coordinate tags must be complete matching pairs')
    for tag, body in re.findall(pattern, prompt, flags=re.S):
        values = body.split()
        require(len(values) == (2 if tag == 'point' else 4)
                and all(re.fullmatch(r'[0-9]+', v) and 0 <= int(v) <= 999 for v in values),
                'Coordinates must be normalized integers 0..999')
        coords = list(map(int, values))
        if tag == 'bbox':
            require(coords[0] < coords[2] and coords[1] < coords[3], 'bbox corners must be ordered and nonempty')


def compile_image_assets(inputs, measured_assets, operation="image-to-image"):
    """Bind ordered image sources to the measured quote; encode only at POST time."""
    from .assets import inspect_asset
    from .media_probe import validate_image_metadata
    maximum = 1 if operation == 'decompose-layers' else 10
    require(isinstance(inputs, list) and 1 <= len(inputs) <= maximum,
            operation + ' requires 1..' + str(maximum) + ' outer assets')
    for item in inputs:
        require(isinstance(item, dict) and set(item) == {'id', 'kind', 'source', 'purpose'},
                'Each outer asset requires id, kind, source and purpose')
        require(isinstance(item['id'], str) and bool(item['id'].strip()), 'Asset id must be a nonempty string')
        require(item['kind'] == 'image', operation + ' accepts image assets only')
    require(len({item['id'] for item in inputs}) == len(inputs), 'Asset ids must be unique')
    sources = [item['source'] for item in inputs]
    if measured_assets is not None:
        require(isinstance(measured_assets, list) and len(measured_assets) == len(sources),
                'Image sources differ from cost artifact; estimate again')
    assets = []
    for index, source in enumerate(sources):
        measured = measured_assets[index] if measured_assets is not None else None
        if measured is not None:
            require(measured.get('kind') == 'image' and measured.get('source') == source
                    and measured.get('id') == inputs[index]['id'],
                    'Image sources/order differ from cost artifact; estimate again')
        asset = inspect_asset({k: v for k, v in inputs[index].items() if k != 'id'})
        asset['id'] = inputs[index]['id']
        asset['source'] = source
        require(asset['transport'] in ('https', 'local-base64'), 'Image input accepts local paths or HTTPS, not asset IDs')
        if measured is not None:
            metadata = {k: v for k, v in measured.items() if k not in ('id', 'kind', 'source')}
            if asset['transport'] == 'local-base64':
                require(metadata.get('sha256') == asset['sha256'],
                        'Local image changed after estimation; estimate again and reconfirm')
            else:
                asset['metadata'] = metadata
            if 'id' in measured:
                asset['id'] = measured['id']
        if operation == 'decompose-layers':
            from .media_probe import validate_layer_metadata
            validate_layer_metadata(asset['metadata'])
        else:
            validate_image_metadata(asset['metadata'], require_dimensions=measured is not None)
        assets.append(asset)
    return assets


def compile_native_image(spec, measured_assets=None):
    """Validate the selected supplier image body without rewriting its prompt."""
    allowed = {'provider', 'operation', 'original_prompt', 'payload',
               'estimate_context', 'budget_cny', 'budget_usd', 'fx'}
    if spec.get('operation') in ('image-to-image', 'decompose-layers'):
        allowed.add('assets')
    require(not (set(spec) - allowed), 'Unsupported native request envelope fields')
    provider = spec.get('provider')
    require(isinstance(provider, str) and provider in CATALOGS, 'Select a supported supplier explicitly')
    operation = spec.get('operation')
    require_supported_operation(spec)
    internal_operation(spec)
    payload = copy.deepcopy(spec.get('payload'))
    require(isinstance(payload, dict), 'payload must be an object')
    fields = {'model', 'prompt', 'size', 'output_format', 'response_format', 'watermark',
              'background', 'optimize_prompt_options', 'layer_decomposition'}
    if operation in ('image-to-image', 'decompose-layers'):
        fields.add('image')
    require(not (set(payload) - fields), 'Unsupported native image payload fields: ' + str(sorted(set(payload) - fields)))
    models = CATALOGS[provider]['models']
    alias = next((k for k, v in models.items() if v['id'] == payload.get('model')), None)
    require(alias is not None and operation in models[alias]['operations'],
            'payload.model must be an exact image model ID belonging to the selected supplier')
    prompt = payload.get('prompt')
    require(isinstance(prompt, str) and bool(prompt.strip()), 'payload.prompt is required')
    # The skill intentionally exposes a narrower contract than the supplier API.
    require('size' in payload, 'payload.size is required; resolve the documented default before submission')
    fixed = {'output_format': 'png', 'response_format': 'url', 'watermark': False,
             'background': 'opaque', 'layer_decomposition': operation == 'decompose-layers'}
    for key, value in fixed.items():
        require(key in payload and type(payload[key]) is type(value) and payload[key] == value,
                operation + ' requires ' + key + '=' + str(value))
    require('optimize_prompt_options' not in payload, operation + ' must omit optimize_prompt_options')
    if operation in ('image-to-image', 'decompose-layers'):
        require('image' not in payload or payload['image'] == [],
                'Leave payload.image empty or omit it; provide image resources in outer assets')
    assets = compile_image_assets(spec.get('assets'), measured_assets, operation) if operation in ('image-to-image', 'decompose-layers') else []
    if operation in ('image-to-image', 'decompose-layers'):
        from .assets import validate_image_request_size
        validate_image_request_size(assets, payload)
        validate_edit_coordinates(prompt, allow_point=operation != 'decompose-layers')
    params = {'size': payload['size'], **fixed}
    from .cost_quote import compile_cost_inputs
    compile_cost_inputs({'provider': provider, 'model': alias, 'operation': operation, 'input_images': len(assets),
                         'size': params['size']})
    for key in ('budget_cny', 'budget_usd'):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + ' must be positive')
    return {'provider': provider, 'model': alias, 'kind': 'image',
            'operation': operation, 'prompt': prompt, 'assets': assets,
            'parameters': params, 'payload_template': payload,
            'warnings': [], 'quantity': 17 if operation == 'decompose-layers' else 1, 'optimizer': None,
            'original_prompt': spec.get('original_prompt')}


def compile_native_request(spec, measured_assets=None):
    """Native image operations for Volcengine and BytePlus."""
    require_supported_operation(spec)
    if spec['operation'] == 'text-to-image':
        require(measured_assets in (None, []), 'Text-to-image must not include measured assets')
    if spec['operation'] in ('text-to-video', 'image-to-video'):
        from .native_video import compile_native_video
        return compile_native_video(spec, measured_assets)
    return compile_native_image(spec, measured_assets)


def compile_request(spec, measured_assets=None):
    """Compile only the provider-native envelope documented by this skill."""
    require(isinstance(spec, dict), 'Request must be an object')
    require('payload' in spec, 'Submission requires a provider-native payload; legacy request format is not supported')
    return compile_native_request(spec, measured_assets)
