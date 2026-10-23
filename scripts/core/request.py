# 原生请求入口：校验供应商 API 请求，不改写已确认提示词。
# 此处只做离线检查；远程素材尺寸、可访问性和账户权限不能靠编译结果证明。
"""Compile an explicit operation into a validated request."""
import copy
import json
import math
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
    """Both suppliers currently expose basic text-to-image only."""
    require_supported_operation(spec)
    require(measured_assets in (None, []), 'Text-to-image must not include measured assets')
    return compile_native_image(spec)


def compile_request(spec, measured_assets=None):
    """Compile only the provider-native envelope documented by this skill."""
    require(isinstance(spec, dict), 'Request must be an object')
    require('payload' in spec, 'Submission requires a provider-native payload; legacy request format is not supported')
    return compile_native_request(spec, measured_assets)
