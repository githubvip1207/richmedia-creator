"""Cost-only inputs and artifacts, independent of generation request preparation."""
import copy
import datetime as dt
from .request import compile_request, require, ROOT, CATALOGS, number
from .cost_formula import estimate
from .cost_record import build_record
from .operations import internal_operation
from .envfile import validate_fx
from providers import get_provider


def billing_inputs(compiled):
    p = compiled['parameters']
    result = {'provider': compiled['provider'], 'model': compiled['model'],
              'operation': compiled['operation'],
              'input_images': sum(a['kind'] == 'image' for a in compiled['assets']),
              'input_video_seconds': [a['metadata']['duration'] for a in compiled['assets'] if a['kind'] == 'video'],
              'input_audio_seconds': [a['metadata']['duration'] for a in compiled['assets'] if a['kind'] == 'audio']}
    if compiled.get('mode') is not None:
        result['mode'] = compiled['mode']
    if compiled['kind'] == 'image':
        result['size'] = p['size']
    else:
        result.update({k: p[k] for k in ('resolution', 'ratio', 'duration')})
    return result


def compile_cost_inputs(inputs, measured_assets=None):
    """Validate billing inputs only; no prompt, fake assets or generation payload."""
    provider = inputs['provider']
    get_provider(provider)
    models = CATALOGS[provider]['models']
    model = inputs['model']
    if model not in models:
        model = next((k for k, v in models.items() if v['id'] == model), None)
    require(model is not None, 'Unknown model')
    m = models[model]
    op = internal_operation(inputs)
    require(inputs['operation'] in m['operations'], 'Operation not supported by model')
    count = inputs.get('input_images', 0)
    seconds = inputs.get('input_video_seconds', [])
    audio_seconds = inputs.get('input_audio_seconds', [])
    require(type(count) is int and count >= 0, 'input_images must be a nonnegative integer')
    require(isinstance(seconds, list) and all(number(d) and d > 0 for d in seconds),
            'Provide measured positive seconds for each input video')
    require(isinstance(audio_seconds, list) and all(number(d) and d > 0 for d in audio_seconds),
            'Provide measured positive seconds for each input audio')
    if m['kind'] == 'image':
        require(not seconds and not audio_seconds, 'Image operations accept image assets only')
        low, high = {'text-to-image': (0, 0), 'image-to-image': (1, 10), 'decompose-layers': (1, 1)}[op]
        require(low <= count <= high, 'Invalid input image count for operation')
        size = inputs.get('size')
        sizes = m['sizes'] + (['auto'] if op == 'decompose-layers' else [])
        if size not in sizes:
            import re
            require(op != 'decompose-layers' and isinstance(size, str) and re.fullmatch(r'[1-9][0-9]*x[1-9][0-9]*', size), 'Invalid image size')
            w, h = map(int, size.split('x'))
            require(921600 <= w*h <= 4624220 and 1/16 <= w/h <= 16, 'Image size outside supported pixels/ratio')
        require(not any(inputs.get(k) is not None for k in ('resolution', 'ratio', 'duration')), 'Image costs require size, not video settings')
        params = {'size': size}
    else:
        require(inputs.get('size') is None, 'Video costs require resolution, not image size')
        resolution, ratio, duration = (inputs.get(k) for k in ('resolution', 'ratio', 'duration'))
        require(resolution in m['resolutions'], 'Invalid resolution')
        from .request import RATIOS
        locked = model == 'seedance-2.5' and op in ('first-frame', 'first-last-frame', 'edit-video', 'extend-video')
        require(ratio in (['adaptive'] if locked else RATIOS), 'Invalid ratio for operation')
        require(type(duration) is int and (duration == -1 or 4 <= duration <= m['max_duration']), 'Invalid duration')
        require(not (model == 'seedance-2.5' and op == 'edit-video') or duration == -1, 'Seedance 2.5 editing requires duration=-1')
        require(count <= m['limits']['image'] and len(seconds) <= m['limits']['video']
                and len(audio_seconds) <= m['limits']['audio'], 'Too many input assets')
        minimum_seconds = 4 if model == 'seedance-2.5' and op == 'edit-video' else 2
        require(all(minimum_seconds <= d <= m['max_duration'] for d in seconds) and sum(seconds) <= m['max_duration'], 'Input video duration outside model limits')
        require(all(2 <= d <= m['max_duration'] for d in audio_seconds)
                and sum(audio_seconds) <= m['max_duration'], 'Input audio duration outside model limits')
        if op == 'text-to-video':
            require(count == 0 and not seconds and not audio_seconds, 'Text-to-video has no input assets')
        elif op in ('first-frame', 'first-last-frame'):
            require(count == (1 if op == 'first-frame' else 2) and not seconds and not audio_seconds, 'Invalid first/last frame input count')
        elif op == 'reference-to-video':
            require(bool(count or seconds or audio_seconds), 'Reference generation requires assets')
            require(model == 'seedance-2.5' or bool(count or seconds), '2.0 cannot use audio-only reference')
        elif op in ('edit-video', 'extend-video'):
            require(bool(seconds), 'Editing/extension needs measured input video durations')
        params = {'resolution': resolution, 'ratio': ratio, 'duration': duration}
    assets = (measured_assets if measured_assets is not None else
              [{'kind': 'image'} for _ in range(count)] +
              [{'kind': 'video', 'metadata': {'duration': d}} for d in seconds] +
              [{'kind': 'audio', 'metadata': {'duration': d}} for d in audio_seconds])
    return {'provider': provider, 'model': model, 'kind': m['kind'], 'operation': inputs['operation'],
            **({'mode': inputs['mode']} if inputs.get('mode') is not None else {}),
            'parameters': params, 'assets': assets}


def calculate_inputs(inputs, pricing=None, context=None, fx=None, measured_assets=None):
    from . import submission_store as store
    compiled = compile_cost_inputs(inputs, measured_assets)
    info = get_provider(compiled['provider'])
    pricing = pricing or store.read(ROOT/'models'/info['pricing'])
    detail = estimate(compiled, context, pricing, fx)
    return build_record(inputs, compiled, billing_inputs(compiled), pricing, detail, context, fx, store.now())


def consume_quote(spec, quote):
    """Reuse saved formula inputs and result, without loading or calculating new prices."""
    require(isinstance(quote, dict) and set(quote) == {'input', 'calculation', 'result'},
            'Cost artifact format changed; run main.py estimate-cost again')
    calculation, result = quote['calculation'], quote['result']
    require(calculation.get('schema_version') == 3, 'Cost artifact format changed; run main.py estimate-cost again')
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(calculation['created_at'])
    require(dt.timedelta(0) <= age <= dt.timedelta(hours=24), 'Cost artifact expired; run main.py estimate-cost again')
    s = copy.deepcopy(spec)
    if 'estimate_context' not in s and calculation.get('estimate_context') is not None:
        s['estimate_context'] = copy.deepcopy(calculation['estimate_context'])
    if 'fx' not in s and calculation.get('fx') is not None:
        s['fx'] = copy.deepcopy(calculation['fx'])
    if s.get('fx') is not None:
        validate_fx(s['fx'])
    compiled = compile_request(s, measured_assets=calculation['assets'] if 'payload' in s else None)
    billing = billing_inputs(compiled)
    require(all(calculation.get(k) == v for k, v in billing.items())
            and s.get('estimate_context') == calculation.get('estimate_context')
            and s.get('fx') == calculation.get('fx'),
            'Request differs from cost artifact; run main.py estimate-cost again')
    info = get_provider(compiled['provider'])
    require(calculation['provider'] == compiled['provider'] and result['currency'] == info['currency'],
            'Cost artifact supplier mismatch')
    return s, compiled, calculation['pricing'], result
