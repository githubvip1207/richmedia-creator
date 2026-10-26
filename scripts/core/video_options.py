"""视频可选参数的校验；保留已确认取值，不改写供应商请求。"""

from urllib.parse import urlsplit
from core.validation import require


def validate_video_options(body, provider, model):
    """校验当前技能支持的视频输出、回调和用户标识字段。"""
    for key in ('generate_audio', 'watermark', 'return_last_frame'):
        require(type(body[key]) is bool, key + ' must be a boolean')
    if provider == 'volcengine':
        require('service_tier' not in body, 'This video request must omit service_tier')
    elif 'service_tier' in body:
        require(body['service_tier'] == 'default', 'service_tier must be default')
    if model == 'seedance-2.5':
        require(body.get('output_format', 'mp4') in ('mp4', 'mov'),
                'Seedance 2.5 output_format must be mp4 or mov')
    else:
        require('output_format' not in body,
                'Seedance 2.0 series must omit output_format; output is MP4')
    if 'callback_url' in body:
        value = body['callback_url']
        require(isinstance(value, str) and bool(value), 'callback_url must be an HTTPS URL')
        parsed = urlsplit(value)
        require(parsed.scheme == 'https' and bool(parsed.hostname)
                and not parsed.username and not parsed.password,
                'callback_url must be an HTTPS URL without embedded credentials')
    if 'safety_identifier' in body:
        value = body['safety_identifier']
        require(isinstance(value, str) and value.isascii() and 1 <= len(value) <= 64,
                'safety_identifier must be an ASCII string of 1..64 characters')
