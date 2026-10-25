"""Resolve cost inputs from media sources; never submit generation requests."""
import copy
import json
import math
import mimetypes
from .assets import sha256_file, image_mime, validate_image_request_size
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from .request import require


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
    local_hash = sha256_file(source) if not source.startswith('https://') else None
    probe = shutil.which('ffprobe')
    require(probe is not None, 'ffprobe is required to inspect cost assets; run main.py doctor --dependencies')
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
            if kind == 'image':
                metadata['mime'] = {'png': 'image/png', 'mjpeg': 'image/jpeg'}.get(stream.get('codec_name'))
                byte_size = data.get('format', {}).get('size')
                if byte_size is not None and str(byte_size).isdigit():
                    metadata['bytes'] = int(byte_size)
                pixel_format = stream.get('pix_fmt', '')
                metadata['has_alpha'] = pixel_format in ('rgba', 'bgra', 'argb', 'abgr', 'ya8', 'ya16be', 'ya16le') or pixel_format.startswith(('yuva', 'gbrap'))
        if kind in ('video', 'audio'):
            duration = stream.get('duration')
            if duration in (None, 'N/A'):
                duration = data.get('format', {}).get('duration')
            duration = float(duration)
            require(math.isfinite(duration) and duration > 0, 'Invalid media duration')
            metadata['duration'] = duration
    except (ValueError, TypeError, KeyError, StopIteration, AttributeError):
        raise ValueError('Cost asset has no valid dimensions/duration for its declared kind') from None
    if local_hash is not None:
        require(sha256_file(source) == local_hash, 'Local asset changed during inspection; estimate again')
        metadata.update(sha256=local_hash, bytes=Path(source).stat().st_size,
                        mime=image_mime(source) if kind == 'image' else mimetypes.guess_type(source)[0])
    return {**({'id': asset['id']} if 'id' in asset else {}),
            'kind': kind, 'source': source, 'metadata': metadata}


def calculate_asset_inputs(inputs, fx=None):
    from .cost_quote import calculate_inputs
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
    if inputs['operation'] in ('image-to-image', 'decompose-layers'):
        maximum = 1 if inputs['operation'] == 'decompose-layers' else 10
        require(1 <= len(assets) <= maximum and all(isinstance(a, dict) and a.get('kind') == 'image' for a in assets),
                inputs['operation'] + ' requires 1..' + str(maximum) + ' image assets')
    if inputs['operation'] == 'text-to-video':
        require(assets == [], 'Text-to-video must not include assets')
    if inputs['operation'] == 'image-to-video':
        from .operations import internal_operation
        mode = internal_operation(inputs)
        require(len(assets) == (1 if mode == 'first-frame' else 2)
                and all(isinstance(a, dict) and a.get('kind') == 'image' for a in assets),
                'Image-to-video requires ordered first/last image frames')
    measured = [probe_asset(a) for a in assets]
    if inputs['operation'] in ('image-to-image', 'decompose-layers'):
        for asset in measured:
            if inputs['operation'] == 'decompose-layers':
                validate_layer_metadata(asset['metadata'])
            else:
                validate_image_metadata(asset['metadata'])
        validate_image_request_size(measured)
    if inputs['operation'] == 'image-to-video':
        from .native_video import validate_frame_metadata
        for asset in measured:
            require(asset['kind'] == 'image', 'Image-to-video accepts image frames only')
            validate_frame_metadata(asset['metadata'])
        validate_image_request_size(measured)
    resolved = {k: v for k, v in inputs.items() if k not in ('assets', 'estimate_context')}
    resolved['input_images'] = sum(a['kind'] == 'image' for a in measured)
    resolved['input_video_seconds'] = [a['metadata']['duration'] for a in measured if a['kind'] == 'video']
    resolved['input_audio_seconds'] = [a['metadata']['duration'] for a in measured if a['kind'] == 'audio']
    quote = calculate_inputs(resolved, context=inputs.get('estimate_context'), fx=fx, measured_assets=measured)
    quote['input'] = copy.deepcopy(inputs)
    return quote


def validate_image_metadata(metadata, require_dimensions=True):
    """Seedream reference image limits; remote byte size may remain unverified."""
    width, height = metadata.get('width'), metadata.get('height')
    if width is not None or height is not None or require_dimensions:
        require(type(width) is int and type(height) is int and min(width, height) > 14
                and width * height <= 36000000 and 1/16 <= width/height <= 16,
                'Image dimensions outside supported reference limits')
    if 'bytes' in metadata:
        require(type(metadata['bytes']) is int and 0 <= metadata['bytes'] <= 30*1024*1024,
                'Image exceeds 30 MB limit')
    if metadata.get('mime') is not None:
        require(metadata['mime'] in ('image/jpeg', 'image/png', 'image/webp', 'image/bmp',
                                    'image/x-ms-bmp', 'image/tiff', 'image/gif', 'image/heic', 'image/heif'),
                'Unsupported input image format')


def validate_layer_metadata(metadata):
    """Layer inputs use stricter format and minimum pixel limits than editing."""
    validate_image_metadata(metadata)
    require(metadata['width'] * metadata['height'] >= 262144,
            'Layer input must have at least 262144 pixels')
    require(metadata.get('mime') in ('image/png', 'image/jpeg'),
            'Layer input must be verified PNG or JPEG')
