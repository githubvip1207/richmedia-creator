# 素材检查与提交前转换：本地文件保持只读，记录原始文件哈希及可测元数据。
# 不实现上传或素材 ID 创建；Base64 只在提交阶段生成，不能用于本地视频。
"""Read-only asset inspection; original files are never rewritten."""
import base64
import hashlib
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse


# 分块读取原始文件并计算 SHA256，避免一次将整个文件载入内存。
# 该哈希用于在批准之后、提交之前识别本地素材是否被替换。
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def image_mime(path):
    """Identify supported local image containers from bytes, never the filename."""
    with open(path, 'rb') as stream:
        head = stream.read(4096)
    signatures = ((b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'),
                  (b'GIF87a', 'image/gif'), (b'GIF89a', 'image/gif'),
                  (b'BM', 'image/bmp'), (b'II\x2a\x00', 'image/tiff'),
                  (b'MM\x00\x2a', 'image/tiff'), (b'II\x2b\x00', 'image/tiff'),
                  (b'MM\x00\x2b', 'image/tiff'))
    for signature, mime in signatures:
        if head.startswith(signature):
            return mime
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    if head[4:8] == b'ftyp':
        box_size = int.from_bytes(head[:4], 'big')
        if 16 <= box_size <= len(head):
            brands = {head[8:12]} | {head[i:i+4] for i in range(16, box_size-3, 4)}
            heic = {b'heic', b'heix', b'hevc', b'hevx', b'heim', b'heis', b'hevm', b'hevs'}
            if not brands & {b'avif', b'avis'}:
                if brands & heic:
                    return 'image/heic'
                if brands & {b'mif1', b'msf1'}:
                    return 'image/heif'
    raise ValueError('Unsupported input image format; file content must be a supported image')


def validate_image_request_size(assets, template=None):
    """Check JSON/data-URI size without allocating Base64 before submission."""
    body = dict(template or {})
    images, encoded_bytes = [], 0
    for asset in assets:
        metadata = asset.get('metadata', {})
        if asset['source'].startswith('https://'):
            images.append(asset['source'])
        else:
            images.append('data:' + metadata['mime'] + ';base64,')
            encoded_bytes += 4 * ((metadata['bytes'] + 2) // 3)
    body['image'] = images
    if len(json.dumps(body, ensure_ascii=False).encode()) + encoded_bytes > 64*1024*1024:
        raise ValueError('Request exceeds 64 MB after Base64 encoding; use approved HTTPS asset URLs')


# 复制并检查素材字段，区分远程 HTTPS、供应商 asset:// 和本地文件三种输入路径。
# 本地图片或音频补充 MIME、字节数、哈希及可获取的 ffprobe 信息；远程事实不自动补猜。
def inspect_asset(asset):
    a = dict(asset)
    # 字段白名单防止把未经支持的素材控制项混入已任务配置。
    allowed = {'kind', 'source', 'role', 'purpose', 'metadata', 'provenance'}
    if set(a) - allowed:
        raise ValueError('Unknown asset fields: ' + str(sorted(set(a) - allowed)))
    if a.get('kind') not in ('image', 'video', 'audio'):
        raise ValueError('Asset kind must be image/video/audio')
    if not isinstance(a.get('purpose'), str) or not a['purpose'].strip():
        raise ValueError('Each asset needs a purpose')
    source = a.get('source', '')
    if not isinstance(source, str) or not source:
        raise ValueError('Each asset needs a source')
    a['metadata'] = dict(a.get('metadata', {}))
    parsed = urlparse(source)
    # 远程输入只检查地址结构；此路径不抓取媒体，不能声称尺寸或可访问性已核验。
    if parsed.scheme in ('https', 'asset'):
        if parsed.scheme == 'https' and (not parsed.hostname or parsed.username or parsed.password):
            raise ValueError('Invalid HTTPS asset URL')
        if parsed.scheme == 'asset' and not parsed.netloc:
            raise ValueError('Invalid asset:// ID')
        a['transport'] = parsed.scheme
        return a
    if parsed.scheme or not Path(source).is_absolute():
        raise ValueError('Use absolute local paths, HTTPS URLs or asset:// IDs; no inline Base64')
    path = Path(source).resolve(strict=True)
    if not path.is_file():
        raise ValueError('Asset must be a file')
    # 供应商视频输入不支持本地 Base64；直接阻止，不擅自上传或转码。
    if a['kind'] == 'video':
        raise ValueError('Video API accepts HTTPS/asset://, not local video Base64. Upload to your approved storage first, then re-plan with its URL.')
    a['source'] = str(path)
    a['transport'] = 'local-base64'
    # 本地原始文件与后续计划绑定；记录字节数而不保存文件正文。
    a['sha256'] = sha256_file(path)
    a['metadata']['bytes'] = path.stat().st_size
    mime = image_mime(path) if a['kind'] == 'image' else mimetypes.guess_type(str(path))[0]
    if not mime or not mime.startswith(a['kind'] + '/'):
        raise ValueError('Unrecognized asset MIME type')
    a['metadata']['mime'] = mime
    # 已有 ffprobe 时才提取真实媒体信息；缺失时不自动安装、不编造尺寸或时长。
    if shutil.which('ffprobe'):
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                 '-of', 'json', str(path)], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise ValueError('ffprobe could not decode local asset: ' + path.name)
        probe = json.loads(result.stdout)
        stream = next((s for s in probe.get('streams', []) if s.get('codec_type') == ('video' if a['kind'] == 'image' else a['kind'])), {})
        if not stream:
            raise ValueError('ffprobe found no matching media stream: ' + path.name)
        for k in ('width', 'height'):
            if k in stream:
                a['metadata'][k] = stream[k]
        # 只有已识别的透明像素格式才记为带 Alpha；不根据扩展名推断透明度。
        pixel_format = stream.get('pix_fmt', '')
        if a['kind'] == 'image':
            a['metadata']['has_alpha'] = pixel_format in ('rgba','bgra','argb','abgr','ya8','ya16be','ya16le') or pixel_format.startswith(('yuva','gbrap'))
        if a['kind'] == 'audio':
            duration = probe.get('format', {}).get('duration', stream.get('duration'))
            if duration:
                a['metadata']['duration'] = float(duration)
    return a


# 提交时才把本地素材变成 data URI；远程 URL 和素材 ID 原样返回。
# 编码前重新核对哈希，文件已变更则阻止提交，要求更新任务并确认。
def materialize(asset):
    if asset['transport'] != 'local-base64':
        return asset['source']
    with open(asset['source'], 'rb') as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != asset['sha256']:
        raise ValueError('Local asset changed after confirmation; update the task and reconfirm')
    return 'data:' + asset['metadata']['mime'] + ';base64,' + base64.b64encode(data).decode('ascii')
