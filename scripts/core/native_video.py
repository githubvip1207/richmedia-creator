"""Provider-native Seedance text and keyframe video requests."""
import copy
import re
from .request import CATALOGS, require, number, compile_image_assets


def validate_frame_metadata(metadata):
    from .media_probe import validate_image_metadata
    validate_image_metadata(metadata)
    w, h = metadata['width'], metadata['height']
    require(300 <= min(w, h) and max(w, h) <= 6000 and 0.4 <= w/h <= 2.5,
            'Video frame dimensions must be 300..6000 px with aspect ratio 0.4..2.5')
    require(metadata.get('bytes', 0) < 30*1024*1024, 'Video frame must be less than 30 MB')


def compile_native_video(spec, measured_assets=None):
    from .operations import internal_operation
    from .cost_quote import compile_cost_inputs
    allowed = {'provider', 'operation', 'original_prompt', 'payload', 'assets',
               'estimate_context', 'budget_cny', 'budget_usd', 'fx'}
    require(not set(spec) - allowed, 'Unsupported native video envelope fields')
    provider = spec.get('provider')
    require(provider in CATALOGS, 'Select a supported supplier explicitly')
    op = internal_operation(spec)
    body = copy.deepcopy(spec.get('payload'))
    require(isinstance(body, dict), 'payload must be an object')
    fields = {'model', 'content', 'resolution', 'ratio', 'duration', 'generate_audio', 'watermark',
              'return_last_frame', 'output_format', 'service_tier', 'tools'}
    require(not set(body) - fields, 'Unsupported native video payload fields: ' + str(sorted(set(body) - fields)))
    models = CATALOGS[provider]['models']
    alias = next((k for k, v in models.items() if v['id'] == body.get('model')), None)
    require(alias is not None and models[alias]['kind'] == 'video'
            and spec['operation'] in models[alias]['operations'],
            'payload.model must be an exact video model ID belonging to the selected supplier')
    content = body.get('content')
    require(isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict)
            and set(content[0]) == {'type', 'text'} and content[0]['type'] == 'text',
            'payload.content must contain exactly one text item; provide ordered frames in outer assets')
    prompt = content[0]['text']
    require(isinstance(prompt, str) and bool(prompt.strip()), 'Video prompt is required')
    require(not re.search(r'--(?:rs|rt|dur|resolution|ratio|duration|frames|seed|cf|camerafixed|camera_fixed|wm|watermark)\b', prompt),
            'Inline API parameter flags are unsupported; resolve settings in payload before confirmation')
    # Volcengine Mini text-to-video rejects service_tier, including default.
    omit_service_tier = (provider == 'volcengine' and alias == 'seedance-2.0-mini'
                         and spec['operation'] == 'text-to-video')
    required_fields = ('resolution', 'ratio', 'duration', 'generate_audio', 'watermark', 'return_last_frame')
    if omit_service_tier:
        require('service_tier' not in body, 'Volcengine Mini text-to-video must omit service_tier')
    else:
        required_fields += ('service_tier',)
    for key in required_fields:
        require(key in body, 'payload.' + key + ' is required; resolve documented defaults before submission')
    if spec['operation'] == 'image-to-video':
        require(body['ratio'] == 'adaptive', 'Image-to-video requires ratio=adaptive')
    for key in ('generate_audio', 'watermark', 'return_last_frame'):
        require(type(body[key]) is bool, key + ' must be a boolean')
    fixed_fields = {'watermark': False, 'return_last_frame': False}
    if not omit_service_tier:
        fixed_fields['service_tier'] = 'default'
    for key, value in fixed_fields.items():
        require(type(body[key]) is type(value) and body[key] == value,
                'Video generation requires ' + key + '=' + str(value))
    if alias == 'seedance-2.5':
        require(body.get('output_format') == 'mp4', 'Seedance 2.5 requires output_format=mp4')
    else:
        require('output_format' not in body, 'Seedance 2.0 series must omit output_format; output is MP4')
    if provider == 'volcengine':
        body.setdefault('tools', [{'type': 'web_search'}])
    if 'tools' in body:
        from .video_tools import validate_video_tools
        validate_video_tools(provider, spec['operation'], body['tools'])
    inputs = spec.get('assets', [])
    require(isinstance(inputs, list), 'assets must be an array')
    if op == 'text-to-video':
        require(inputs == [] and measured_assets in (None, []), 'Text-to-video must not include assets')
        assets = []
    else:
        count = 1 if op == 'first-frame' else 2
        require(len(inputs) == count, 'Incorrect first/last frame count')
        assets = compile_image_assets(inputs, measured_assets)
        for index, asset in enumerate(assets):
            validate_frame_metadata(asset['metadata'])
            asset['role'] = 'first_frame' if index == 0 else 'last_frame'
            body['content'].append({'type': 'image_url', 'image_url': {'url': {'asset_index': index}},
                                    'role': asset['role']})
    params = {k: v for k, v in body.items() if k not in ('model', 'content')}
    params['output_format'] = body.get('output_format', 'mp4')
    compile_cost_inputs({'provider': provider, 'model': alias, 'operation': spec['operation'],
                         **{k: params[k] for k in ('resolution', 'ratio', 'duration')}, 'input_images': len(assets)})
    for key in ('budget_cny', 'budget_usd'):
        if key in spec:
            require(number(spec[key]) and spec[key] > 0, key + ' must be positive')
    return {'provider': provider, 'model': alias, 'kind': 'video', 'operation': spec['operation'],
            'prompt': prompt, 'assets': assets,
            'parameters': params, 'payload_template': body, 'warnings': [], 'quantity': 1,
            'optimizer': None, 'original_prompt': spec.get('original_prompt')}
