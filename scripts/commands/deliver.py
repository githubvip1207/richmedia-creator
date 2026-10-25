"""deliver: retrieve, validate and publish final outputs to the user directory."""
import base64
import http.client
import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path
from core.request import require
from core.submission_store import read, write, lock, submission_path, now
from core.assets import sha256_file
from providers import get_provider


def video_metadata(path):
    """Inspect actual decoded frames, dimensions, duration and audio presence."""
    probe = shutil.which('ffprobe')
    require(probe is not None, 'ffprobe is required to validate downloaded videos')
    try:
        with open(path, 'rb') as stream:
            head = stream.read(12)
        require(len(head) >= 12 and head[4:8] == b'ftyp', 'Invalid MP4/MOV container')
        result = subprocess.run([probe, '-v', 'error', '-count_frames', '-show_streams',
                                 '-show_format', '-of', 'json', str(path)],
                                capture_output=True, text=True, timeout=60)
        data = json.loads(result.stdout)
        stream = next(s for s in data['streams'] if s.get('codec_type') == 'video')
        duration = float(data.get('format', {}).get('duration', stream.get('duration', 0)))
        require(result.returncode == 0 and not result.stderr.strip() and duration > 0
                and stream.get('width', 0) > 0 and stream.get('height', 0) > 0
                and int(stream.get('nb_read_frames', 0)) > 0, 'Invalid video stream')
        return {'width': stream['width'], 'height': stream['height'], 'duration': duration,
                'codec': stream.get('codec_name'), 'frame_rate': stream.get('avg_frame_rate'),
                'has_audio': any(s.get('codec_type') == 'audio' for s in data['streams'])}
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, StopIteration):
        raise ValueError('Downloaded video has no valid decodable video stream') from None


def valid_media(path, kind, expected_size=None, require_alpha=False):
    with open(path,'rb') as f:
        head = f.read(32)
    if kind == 'video':
        if not (len(head)>8 and head[4:8] == b'ftyp'):
            return False
        try:
            video_metadata(path)
            return True
        except ValueError:
            return False
    if not (head.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or
            (head.startswith(b'RIFF') and head[8:12] == b'WEBP')):
        return False
    probe = shutil.which('ffprobe')
    require(probe is not None, 'ffprobe is required to validate downloaded images')
    try:
        result = subprocess.run(
            [probe, '-v', 'error', '-select_streams', 'v:0', '-show_streams',
             '-show_frames', '-of', 'json', str(path)],
            capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        if require_alpha:
            formats = [stream.get('pix_fmt', '') for stream in data.get('streams', [])]
            if not any(fmt in ('rgba', 'bgra', 'argb', 'abgr', 'ya8', 'ya16be', 'ya16le')
                       or fmt.startswith(('yuva', 'gbrap')) for fmt in formats):
                return False
        if expected_size and 'x' in expected_size:
            width, height = map(int, expected_size.split('x'))
            if not any(s.get('width') == width and s.get('height') == height
                       for s in data.get('streams', [])):
                return False
        return (result.returncode == 0 and not result.stderr.strip()
                and any(s.get('width', 0) > 0 and s.get('height', 0) > 0
                        for s in data.get('streams', []))
                and bool(data.get('frames')))
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return False


def download_with_curl(executable, url, destination):
    """Fetch media with bounded connection/stall waits, never a generation POST."""
    require(url.startswith('https://') and not any(ord(c) < 32 for c in url),
            'Output URL must be HTTPS without control characters')
    # Keep signed URLs out of process arguments and suppress ~/.curlrc settings.
    escaped = url.replace('\\', '\\\\').replace('"', '\\"')
    try:
        result = subprocess.run(
            [executable, '-q', '--config', '-', '--location', '--fail', '--silent',
             '--show-error', '--proto', '=https', '--proto-redir', '=https',
             '--connect-timeout', '15', '--speed-limit', '1024', '--speed-time', '20',
             '--max-time', '900', '--user-agent', 'richmedia-creator/1.0',
             '--output', str(destination), '--write-out', '%{http_code}'],
            input='url = "' + escaped + '"\n', capture_output=True, text=True, timeout=915)
    except subprocess.TimeoutExpired:
        raise TimeoutError('Media transfer exceeded total timeout') from None
    if result.returncode:
        status = result.stdout.strip()
        if status.isdigit() and int(status) >= 400:
            raise urllib.error.HTTPError(url, int(status), 'Media HTTP error', {}, None)
        # curl stderr may contain a signed URL; expose only the numeric exit code.
        raise OSError('Media transport curl exit %s' % result.returncode)


def download_url(url, destination):
    """Retry only media GETs; each attempt replaces any incomplete file."""
    for attempt in range(3):
        try:
            curl = shutil.which('curl')
            if curl:
                download_with_curl(curl, url, destination)
                return
            # Without curl, retain urllib compatibility with a bounded read wait.
            # 媒体 URL 已包含下载授权，不附加 API Key；30 秒是每次阻塞读取的超时，不是整个下载总时长。
            # No API credentials on media downloads. Timeout is per blocking read.
            # Identify this client explicitly; do not attach supplier API credentials.
            request = urllib.request.Request(url, headers={'User-Agent': 'richmedia-creator/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response, open(destination, 'wb') as f:
                require(response.geturl().startswith('https://'), 'Refuse HTTPS downgrade')
                received = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                # 声明了 Content-Length 时核对实际字节数，避免把提前结束的传输当作完整文件。
                expected = response.headers.get('Content-Length')
                if expected is not None and received != int(expected):
                    raise http.client.IncompleteRead(b'', max(0, int(expected) - received))
            return
        except (OSError, urllib.error.URLError, http.client.IncompleteRead) as error:
            # 只重试传输类错误和指定临时 HTTP 状态；404 等永久错误不重试。
            retryable = not isinstance(error, urllib.error.HTTPError) or error.code in (408, 429, 500, 502, 503, 504)
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if not retryable or attempt == 2:
                detail = ('HTTP %s' % error.code if isinstance(error, urllib.error.HTTPError)
                          else str(error) if str(error).startswith('Media transport curl exit ')
                          else type(error).__name__)
                raise RuntimeError('Media download failed after %s attempt(s): %s; '
                                   'generation is preserved, retry deliver only' % (attempt + 1, detail)) from None
            # 第一次失败等待两秒，第二次等待四秒；第三次失败退出，不无限重试。
            time.sleep(2 ** (attempt + 1))


def _download(submission):
    record_path = submission_path(submission)
    d = record_path.parent
    with lock(d):
        record = read(record_path)
        state = record['execution']
        result = record.get('response')
        if state['compiled']['kind'] == 'video':
            result = next((q['response'] for q in reversed(record.get('queries', []))
                           if isinstance(q.get('response'), dict) and q['response'].get('id', state['task_id']) == state['task_id']), result)
        plan = state
        require(state['state'] in ('succeeded','partial_failed'), 'Task not completed successfully; query status first')
        # 旧完成标记不能代表本次检查结果；失败时保留 false，完整清单仍用于恢复。
        state['download_complete'] = False
        write(record_path, record)
        output = d/('output-' + record_path.stem.split('-')[1])
        # Existing downloaded submissions keep their old paths and hash-based reuse.
        legacy_output = d/'outputs'/record_path.stem
        if legacy_output.is_dir() and any(Path(f['path']).parent.resolve() == legacy_output.resolve() for f in record.get('result', {}).get('files', [])):
            output = legacy_output
        output.mkdir(mode=0o700,parents=True,exist_ok=True)
        # 图片保留每个非错误 data 项；视频同时处理主视频和可选末帧。
        if plan['compiled']['kind'] == 'image':
            if plan['compiled'].get('operation') == 'decompose-layers':
                from core.layers import validate_layer_outputs
                entries = [(x, 'image') for x in validate_layer_outputs(result.get('data'))]
            else:
                entries = [(x,'image') for x in result.get('data',[]) if not x.get('error')]
        else:
            c = result.get('content',{})
            entries = [({'url':c['video_url'],'label':'video'},'video')] if c.get('video_url') else []
            if c.get('last_frame_url'):
                entries.append(({'url':c['last_frame_url'],'label':'last-frame'},'image'))
        require(bool(entries), 'No downloadable media in response')
        previous = record.get('result', {}).get('files', [])
        manifest = []
        for i,(entry,kind) in enumerate(entries):
            fmt = entry.get('output_format', 'jpeg' if entry.get('label') == 'last-frame' else plan['compiled']['parameters']['output_format'])
            # 透明图层即使计划默认 JPEG，也强制按供应商图层 PNG 格式保存。
            if kind == 'image' and entry.get('z_index',0) > 0:
                fmt = 'png'
            require(fmt in ('png','jpeg','mp4','mov'), 'Unexpected output format')
            if plan['compiled'].get('operation') in ('text-to-image', 'image-to-image'):
                require(fmt == plan['compiled']['parameters']['output_format'],
                        'Provider image format differs from confirmed format')
            is_layer = plan['compiled'].get('operation') == 'decompose-layers'
            label = ('base' if entry['z_index'] == 0 else 'layer') if is_layer else entry.get('label', 'image')
            name = ('%02d-' % i) + label + '.' + fmt
            path = output/name
            # 清单哈希与磁盘内容一致才跳过下载，不能仅凭文件名存在就假定完整。
            previous_entry = next((x for x in previous if Path(x['path']).resolve() == path.resolve()), None)
            if not (previous_entry and path.is_file() and sha256_file(path) == previous_entry['sha256']):
                tmp = path.with_suffix(path.suffix+'.part')
                # 同步图片可从 Base64 恢复；URL 下载只接受 HTTPS，先写临时 .part 文件。
                if entry.get('b64_json'):
                    tmp.write_bytes(base64.b64decode(entry['b64_json'],validate=True))
                else:
                    url = entry.get('url','')
                    require(url.startswith('https://'), 'Output URL must be HTTPS')
                    download_url(url, tmp)
            else:
                tmp = path
            expected_size = entry['size'] if is_layer else plan['compiled']['parameters'].get('size')
            actual_metadata = video_metadata(tmp) if kind == 'video' else None
            if actual_metadata:
                valid = True
            else:
                valid = (valid_media(tmp, kind, expected_size, require_alpha=entry['z_index'] > 0)
                         if is_layer else valid_media(tmp, kind, expected_size))
            require(valid,
                    'Downloaded content is not valid media; retained file for inspection')
            if kind == 'image':
                with tmp.open('rb') as stream:
                    signature = stream.read(8)
                require((fmt == 'png' and signature == b'\x89PNG\r\n\x1a\n')
                        or (fmt == 'jpeg' and signature.startswith(b'\xff\xd8\xff')),
                        'Downloaded image format differs from confirmed format')
            if tmp != path:
                os.replace(str(tmp), str(path))
            # 清单保留供应商、模型、任务、原始图层元数据和哈希；剔除庞大 Base64 正文。
            manifest.append({'path':str(path),'sha256':sha256_file(path),'kind':kind,
                             **({'metadata': actual_metadata} if actual_metadata else {}),
                             'origin':{k:v for k,v in entry.items() if k != 'b64_json'},
                             'provider':plan['compiled']['provider'], 'model':plan['compiled']['payload_template']['model'],
                             'task_id':state.get('task_id'), 'downloaded_at':now(), 'original':True})
            # 每份文件完成后立即落盘进度，后续下载失败也可复用已完成内容；实际扣费保持未知。
            record['result'] = {'files':manifest,'usage':result.get('usage'), 'actual_billed_amount_cny':None,
                                   'billing_currency':get_provider(plan['compiled']['provider'])['currency'], 'actual_billed_amount':None,
                                   'note':'Original provider outputs preserved; actual paid amount is not returned by this API.'}
            write(record_path, record)
        if plan['compiled'].get('operation') == 'decompose-layers':
            from core.layers import position_metadata
            metadata_path = output/'layers.json'
            write(metadata_path, position_metadata(manifest))
            record['result']['metadata'] = {'path': str(metadata_path), 'sha256': sha256_file(metadata_path)}
        state['download_complete'] = True
        write(record_path, record)
        return record['result']



def deliver(submission, destination=None):
    """Deliver verified media and optional layer metadata, never process files."""
    from commands.status import status, status_result
    record_path = submission_path(submission)
    destination = Path(destination or Path.cwd()).resolve(strict=True)
    require(destination.is_dir(), 'Delivery destination must be an existing directory')
    require(destination != record_path.parent and record_path.parent not in destination.parents,
            'Deliver to the user project directory, not the temporary task directory')
    with lock(record_path.parent):
        record = read(record_path)
        record['execution']['delivery_complete'] = False
        write(record_path, record)
    checked = status_result(status(record_path))
    require(checked['success'], checked['error'] or 'Generation not successful; cannot deliver')
    _download(record_path)
    with lock(record_path.parent):
        record = read(record_path)
        result = record['result']
        require(record['execution'].get('download_complete') is True, 'Media retrieval is incomplete')
        sources = [*result['files']]
        if result.get('metadata'):
            sources.append(result['metadata'])
        for item in sources:
            require(Path(item['path']).is_file() and sha256_file(item['path']) == item['sha256'],
                    'Cached output changed; retry deliver')
        previous = record.get('delivery')
        directory = Path(previous['directory']) if previous else None
        reusable = (directory is not None and directory.is_dir() and not directory.is_symlink()
                    and directory.parent == destination
                    and all((not (directory/Path(item['path']).name).exists()
                             and not (directory/Path(item['path']).name).is_symlink())
                            or ((directory/Path(item['path']).name).is_file()
                                and not (directory/Path(item['path']).name).is_symlink()
                                and sha256_file(directory/Path(item['path']).name) == item['sha256'])
                            for item in sources))
        if not reusable:
            base = 'richmedia-' + record_path.parent.name + '-' + record_path.stem
            counter = 0
            while True:
                directory = destination/(base + ('-' + str(counter) if counter else ''))
                try:
                    directory.mkdir(mode=0o700)
                    break
                except FileExistsError:
                    counter += 1
            if previous:
                record.setdefault('delivery_history', []).append(previous)
        delivered = {'directory': str(directory), 'files': [], 'delivered_at': now()}
        record['delivery'] = delivered
        write(record_path, record)
        for item in sources:
            target = directory/Path(item['path']).name
            if not target.exists():
                # Exclusive creation preserves user files, including during retries.
                with open(item['path'], 'rb') as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                    output.flush()
                    os.fsync(output.fileno())
            require(sha256_file(target) == item['sha256'], 'Delivered file checksum mismatch')
            final = {'path': str(target), 'sha256': item['sha256']}
            if item is result.get('metadata'):
                delivered['metadata'] = final
            else:
                final.update({k: item[k] for k in ('kind', 'provider', 'model', 'metadata') if k in item})
                delivered['files'].append(final)
            write(record_path, record)
        record['execution']['delivery_complete'] = True
        write(record_path, record)
        return delivered


def run(args):
    return deliver(args.submission)
