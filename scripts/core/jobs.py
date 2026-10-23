# 任务生命周期：每次确认只提交一次，保留编号记录；终态后可再次确认并提交。
# 先持久化状态再发出付费 POST；运行中或结果未知时阻止新提交。
"""Confirmed submissions with numbered records and persistent recovery state."""
import base64
import contextlib
import copy
import re
import datetime as dt
import http.client
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path
from .request import require
from .costing import consume_quote
from .cost_record import amount_in
from .assets import sha256_file
from providers import get_provider
from providers.transport import ProviderError
from .envfile import config_value


# 按 UTF-8 读取 JSON 文件；不执行其中的内容，不自动恢复或重新提交任务。
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


# 先写权限为 0600 的同目录临时文件，flush/fsync 后通过 os.replace 原子替换。
# 减少中断时留下半份 JSON 的风险，并限制其他用户读取可能含签名 URL 的状态文件。
def write(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(str(tmp), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))


# 以带时区的 UTC ISO 时间保存审计事件；展示用户本地时间属于调用方职责。
def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


# 按 CODEX_HOME 或默认 .codex，以及 .agents 两个位置列出 sd25-pe 候选入口。
def dependency_paths():
    codex = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex')))
    return [codex/'skills/sd25-pe/SKILL.md', Path.home()/'.agents/skills/sd25-pe/SKILL.md']


# 对任务目录的 .lock 加非阻塞排他文件锁，防止多个进程并发提交或覆盖状态。
# 退出时释放锁；持久化提交记录 负责跨进程退出后的重复提交保护。
@contextlib.contextmanager
def lock(jobdir):
    # 文件锁防并发，持久化状态防重启后的重复提交，两者承担不同职责。
    # flock automatically releases on process exit; the job state prevents resubmission after a crash.
    import fcntl
    with open(Path(jobdir)/'.lock', 'a') as f:
        fcntl.flock(f,fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(f,fcntl.LOCK_UN)


def submission_records(directory):
    return sorted((p for p in Path(directory).glob('submit-*.json')
                   if re.fullmatch(r'submit-[0-9]+\.json', p.name)),
                  key=lambda p: int(p.stem.split('-')[1]))


def submission_path(target):
    path = Path(target).resolve()
    if path.is_dir():
        records = submission_records(path)
        require(bool(records), 'No submission record found')
        return records[-1]
    require(path.is_file() and re.fullmatch(r'submit-[0-9]+\.json', path.name),
            'Provide an existing submit-NNN.json file')
    return path


def prior_submission(directory):
    """Block a new attempt until every prior submission has a known terminal outcome."""
    previous = None
    for path in submission_records(directory):
        previous = read(path)['execution']
        require(previous.get('state') in ('succeeded', 'partial_failed', 'rejected', 'failed', 'expired', 'cancelled'),
                'This task was already attempted and is active or its submission outcome unknown; query/reconcile it before a new submission')
    return previous


def next_submit_record(directory):
    """Called under the workdir lock; never overwrite a numbered submission record."""
    numbers = [int(match.group(1)) for path in directory.glob('submit-*.json')
               if (match := re.fullmatch(r'submit-([0-9]+)\.json', path.name))]
    return directory / ('submit-%03d.json' % (max(numbers, default=0) + 1))


# 验证真实确认文本、任务与已有成本、依赖及供应商密钥。
# 先写 submitting 状态再仅发出一次付费 POST；异常时保留 rejected 或 submission_unknown，绝不重发。
def submit(jobdir, spec, approval_text, accept_uncertain=False):
    d = Path(jobdir).resolve()
    require(bool(approval_text.strip()), 'Record the actual user confirmation; never manufacture approval')
    submitted_input = copy.deepcopy(spec)
    with lock(d):
        prior_submission(d)
        require(isinstance(spec,dict) and bool(spec.get('provider')), 'Select an explicit supplier in the task request')
        get_provider(spec['provider'])
        cost = read(d/spec['provider']/'cost.json')
        spec, compiled, pricing, estimate = consume_quote(spec,cost)
        for unit in ('cny','usd'):
            if spec.get('budget_'+unit) is not None:
                upper = amount_in(estimate, unit.upper())['max']
                require(upper is not None, 'Cannot compare budget with unknown amount/conversion')
                require(upper <= spec['budget_'+unit], 'Estimated amount exceeds budget; revise the request')
        plan = {'compiled':compiled,'estimate':estimate}
        info = get_provider(plan['compiled']['provider'])
        adapter = info['adapter']
        if plan['compiled']['model'] == 'seedance-2.5':
            from .preflight import skill_status
            require(skill_status()['status'] == 'ok', 'Required sd25-pe missing; run doctor --dependencies')
        if plan['estimate']['amount']['max'] is None:
            require(accept_uncertain, 'Cost upper estimate unknown; require explicit user acceptance of uncertainty')
        require(bool(config_value(adapter.KEY_ENV)), adapter.KEY_ENV + ' is not configured')
        # 先在本地转换素材，检查素材可读性后才记录付费尝试；Base64 正文不写日志。
        # Materialize before recording a paid attempt, but never log Base64 payloads.
        payload = adapter.payload(plan)
        require(len(json.dumps(payload,ensure_ascii=False).encode()) <= 64*1024*1024, 'Request exceeds 64 MB')
        # 先落盘 submitting，再开始网络操作；崩溃或中断也留下不可重复提交的审计记录。
        state = {'state':'submitting', 'created_at':now(), 'compiled':compiled,
                 'approval':{'text':approval_text,'recorded_at':now(),'accept_uncertain_cost':accept_uncertain},
                 'provider':plan['compiled']['provider'],'model':plan['compiled']['model'], 'task_id':None}
        record_path = next_submit_record(d)
        state['submission'] = str(record_path)
        record = {**submitted_input, 'response': None, 'execution': state}
        write(record_path, record)
        try:
            # 本模块唯一的付费网络入口：一次 POST，没有重试循环，也没有备用供应商分支。
            # The only paid network action in this module; exactly one POST, never retried.
            endpoint = '/images/generations' if plan['compiled']['kind'] == 'image' else '/contents/generations/tasks'
            result = adapter.request('POST',endpoint,payload)
            record['response'] = result
            write(record_path, record)
            # 视频响应只代表任务已创建，进入 queued；图片响应为同步结果，但仍逐项检查错误。
            if plan['compiled']['kind'] == 'video':
                require(isinstance(result.get('id'),str) and bool(result['id']), 'POST response did not contain task ID')
                state.update(state='queued',task_id=result['id'])
            else:
                require(isinstance(result.get('data'),list) and bool(result['data']), 'Image response missing output data')
                errors = [x.get('error') for x in result['data'] if x.get('error')]
                image_state = 'failed' if len(errors) == len(result['data']) else ('partial_failed' if errors else 'succeeded')
                state.update(state=image_state,usage=result.get('usage'), errors=errors)
        # 有不确定性的供应商错误或响应处理异常保留 submission_unknown；明确拒绝才记 rejected。
        except Exception as exc:
            state.update(state='submission_unknown' if not isinstance(exc,ProviderError) or exc.uncertain else 'rejected',
                         error=str(exc) if isinstance(exc,(ValueError,ProviderError)) else type(exc).__name__)
            write(record_path, record)
            raise
        state['updated_at'] = now()
        write(record_path, record)
        return state


# 在固定供应商上查询已有视频任务，使用单调时钟把单次等待限制在 0..600 秒。
# 图片同步请求或缺少任务 ID 时只返回现存状态，不通过查询创建新生成。
def status(submission, wait=0):
    path = submission_path(submission)
    with lock(path.parent):
        record = read(path)
        state = record['execution']
        adapter = get_provider(state['compiled']['provider'])['adapter']
        if state['compiled']['kind'] == 'image' or not state.get('task_id'):
            return state
        wait = min(max(wait, 0), 600)
        deadline = time.monotonic() + wait
        while True:
            # 不在截止时间后开始新查询；单次请求超时不超过剩余等待时间。
            if wait:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return state
                result = query_submission(record, path, adapter, state['task_id'], timeout=min(25, remaining))
            else:
                result = query_submission(record, path, adapter, state['task_id'])
            require(result.get('id', state['task_id']) == state['task_id'], 'Provider returned a different task ID')
            state.update(state=result.get('status','unknown'), updated_at=now(), usage=result.get('usage'), error=result.get('error'))
            write(path, record)
            remaining = deadline - time.monotonic()
            if state['state'] not in ('queued','running') or not wait or remaining <= 0:
                return state
            time.sleep(min(10, remaining))


def query_submission(record, path, adapter, task_id, timeout=None):
    """Retain every status GET separately; keep the original POST response unchanged."""
    from urllib.parse import quote
    query = {'requested_at': now(), 'request': {'method': 'GET',
             'path': '/contents/generations/tasks/' + quote(task_id, safe='')}, 'response': None}
    record.setdefault('queries', []).append(query)
    write(path, record)
    try:
        query['response'] = adapter.status(task_id) if timeout is None else adapter.status(task_id, timeout=timeout)
    except Exception as exc:
        query['error'] = str(exc) if isinstance(exc, ProviderError) else type(exc).__name__
        write(path, record)
        raise
    write(path, record)
    return query['response']


# 检查 PNG/JPEG/WebP 或 MP4/MOV 容器的基本文件头，排除明显的错误页面。
# 这只是格式初筛，不能证明媒体完整解码、画面质量或业务内容符合要求。
def valid_media(path, kind):
    with open(path,'rb') as f:
        head = f.read(32)
    if kind == 'video':
        return len(head)>8 and head[4:8] == b'ftyp'
    return head.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or (head.startswith(b'RIFF') and head[8:12]==b'WEBP')


# 只为已有媒体的 GET 提供最多三次下载尝试，重试时覆盖不完整临时文件。
# 每次阻塞读取超时 120 秒，按 64 KiB 分块写入；核对 Content-Length，失败后等待 2/4 秒。
def download_url(url, destination):
    """Retry only media GETs; each attempt replaces any incomplete file."""
    for attempt in range(3):
        try:
            # 媒体 URL 已包含下载授权，不附加 API Key；120 秒是每次阻塞读取的超时，不是整个下载总时长。
            # No API credentials on media downloads. Timeout is per blocking read.
            with urllib.request.urlopen(url, timeout=120) as response, open(destination, 'wb') as f:
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
                          else type(error).__name__)
                raise RuntimeError('Media download failed after %s attempt(s): %s; '
                                   'generation is preserved, retry download only' % (attempt + 1, detail)) from None
            # 第一次失败等待两秒，第二次等待四秒；第三次失败退出，不无限重试。
            time.sleep(2 ** (attempt + 1))


# 从已成功或部分失败响应收集所有可交付媒体，保留图层及末帧，而非只处理首张。
# 已有文件哈希匹配则复用；否则先写 .part，经文件头检查后原子改名，并逐份更新恢复清单。
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
        output = d/'outputs'/record_path.stem
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
            name = ('%02d-' % i) + entry.get('label','image') + '.' + fmt
            path = output/name
            # 清单哈希与磁盘内容一致才跳过下载，不能仅凭文件名存在就假定完整。
            previous_entry = next((x for x in previous if x['path'] == str(path)), None)
            if not (previous_entry and path.is_file() and sha256_file(path) == previous_entry['sha256']):
                tmp = path.with_suffix(path.suffix+'.part')
                # 同步图片可从 Base64 恢复；URL 下载只接受 HTTPS，先写临时 .part 文件。
                if entry.get('b64_json'):
                    tmp.write_bytes(base64.b64decode(entry['b64_json'],validate=True))
                else:
                    url = entry.get('url','')
                    require(url.startswith('https://'), 'Output URL must be HTTPS')
                    download_url(url, tmp)
                require(valid_media(tmp,kind), 'Downloaded content is not expected media; retained .part for inspection')
                os.replace(str(tmp),str(path))
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
