"""download: retrieve existing output media with resumable local manifests."""
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


def valid_media(path, kind, expected_size=None):
    with open(path,'rb') as f:
        head = f.read(32)
    if kind == 'video':
        return len(head)>8 and head[4:8] == b'ftyp'
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
                                   'generation is preserved, retry download only' % (attempt + 1, detail)) from None
            # 第一次失败等待两秒，第二次等待四秒；第三次失败退出，不无限重试。
            time.sleep(2 ** (attempt + 1))


def download(submission):
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
            name = ('%02d-' % i) + entry.get('label','image') + '.' + fmt
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
            require(valid_media(tmp, kind, plan['compiled']['parameters'].get('size')),
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
                             'origin':{k:v for k,v in entry.items() if k != 'b64_json'},
                             'provider':plan['compiled']['provider'], 'model':plan['compiled']['payload_template']['model'],
                             'task_id':state.get('task_id'), 'downloaded_at':now(), 'original':True})
            # 每份文件完成后立即落盘进度，后续下载失败也可复用已完成内容；实际扣费保持未知。
            record['result'] = {'files':manifest,'usage':result.get('usage'), 'actual_billed_amount_cny':None,
                                   'billing_currency':get_provider(plan['compiled']['provider'])['currency'], 'actual_billed_amount':None,
                                   'note':'Original provider outputs preserved; actual paid amount is not returned by this API.'}
            write(record_path, record)
        state['download_complete'] = True
        write(record_path, record)
        return record['result']


def run(args):
    return download(args.submission)
