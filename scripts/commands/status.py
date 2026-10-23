"""status: query an existing submission; images use their saved local state."""
import json
import time
from core.request import require
from core.submission_store import read, write, lock, submission_path, now
from providers import get_provider
from providers.transport import ProviderError


def status_result(state):
    if state.get('state') == 'succeeded':
        return {'success': True, 'error': None}
    error = state.get('error') or state.get('errors')
    if error:
        if isinstance(error, dict):
            error = error.get('message') or json.dumps(error, ensure_ascii=False)
        elif isinstance(error, list):
            error = '；'.join(str(item.get('message') or json.dumps(item, ensure_ascii=False))
                             if isinstance(item, dict) else str(item) for item in error)
        return {'success': False, 'error': str(error)}
    status = state.get('state', 'unknown')
    if status in ('queued', 'running'):
        error = '任务尚未完成（状态：' + status + '），可继续查询'
    elif status in ('submitting', 'submission_unknown', 'unknown'):
        error = '生成结果尚未确定（状态：' + status + '），需核对供应商记录'
    else:
        error = '任务未成功（状态：' + status + '），供应商未提供具体原因'
    return {'success': False, 'error': error}


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


def run(args):
    return status_result(status(args.submission, args.wait))
