"""Resolve cost inputs from media sources; never submit generation requests."""
import copy
import json
import math
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from .request import require, number


def probe_asset(asset):
    require(isinstance(asset, dict) and {'kind', 'source'} <= set(asset)
            and set(asset) <= {'id', 'kind', 'source'},
            'Each cost asset requires kind/source and an optional id')
    if 'id' in asset:
        require(isinstance(asset['id'], str) and bool(asset['id'].strip()), 'Asset id must be a nonempty string')
    kind, source = asset['kind'], asset['source']
    require(kind in ('image', 'video', 'audio'), 'Invalid cost asset kind')
    require(isinstance(source, str) and bool(source), 'Asset source must be a path or HTTPS URL')
    if source.startswith('https://'):
        url = urlsplit(source)
        require(bool(url.hostname) and not url.username and not url.password,
                'Use an HTTPS URL without embedded credentials')
    else:
        path = Path(source)
        require(path.is_absolute() and path.is_file(),
                'Use an existing absolute media path or HTTPS URL; asset IDs need an accessible original source')
    probe = shutil.which('ffprobe')
    require(probe is not None, 'ffprobe is required to inspect cost assets; run media.py doctor --dependencies')
    try:
        result = subprocess.run([probe, '-v', 'error', '-protocol_whitelist', 'file,http,https,tcp,tls',
                                 '-show_streams', '-show_format', '-of', 'json', source],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise ValueError('Could not inspect cost asset; check media access and ffprobe') from None
    require(result.returncode == 0, 'Could not inspect cost asset; check media access and format')
    try:
        data = json.loads(result.stdout)
        stream = next(s for s in data['streams'] if s.get('codec_type') == ('video' if kind == 'image' else kind))
        metadata = {}
        if kind in ('image', 'video'):
            w, h = stream['width'], stream['height']
            require(type(w) is int and type(h) is int and w > 0 and h > 0, 'Invalid media dimensions')
            metadata.update(width=w, height=h)
        if kind in ('video', 'audio'):
            duration = stream.get('duration')
            if duration in (None, 'N/A'):
                duration = data.get('format', {}).get('duration')
            duration = float(duration)
            require(math.isfinite(duration) and duration > 0, 'Invalid media duration')
            metadata['duration'] = duration
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError):
        raise ValueError('Cost asset has no valid dimensions/duration for its declared kind') from None
    return {**({'id': asset['id']} if 'id' in asset else {}),
            'kind': kind, 'source': source, 'metadata': metadata}


def calculate_asset_inputs(inputs, fx=None):
    from .costing import calculate_inputs
    allowed = {'provider', 'model', 'operation', 'mode', 'size', 'resolution', 'ratio', 'duration', 'assets', 'estimate_context'}
    require(isinstance(inputs, dict), 'Cost input must be a JSON object')
    require(not (set(inputs) - allowed), 'Unknown cost input fields: '+str(sorted(set(inputs)-allowed)))
    for key in ('provider', 'model', 'operation'):
        require(isinstance(inputs.get(key), str) and bool(inputs[key]), key+' must be a nonempty string')
    # Resolve the supplier before any media access. Rates are loaded internally by calculate_inputs.
    from providers import get_provider
    get_provider(inputs['provider'])
    assets = inputs.get('assets', [])
    require(isinstance(assets, list), 'assets must be an array')
    measured = [probe_asset(a) for a in assets]
    resolved = {k: v for k, v in inputs.items() if k not in ('assets', 'estimate_context')}
    resolved['input_images'] = sum(a['kind'] == 'image' for a in measured)
    resolved['input_video_seconds'] = [a['metadata']['duration'] for a in measured if a['kind'] == 'video']
    resolved['input_audio_seconds'] = [a['metadata']['duration'] for a in measured if a['kind'] == 'audio']
    quote = calculate_inputs(resolved, context=inputs.get('estimate_context'), fx=fx, measured_assets=measured)
    quote['input'] = copy.deepcopy(inputs)
    return quote
