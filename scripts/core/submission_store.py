"""Shared submission files, atomic writes and cross-process locks."""
import contextlib
import datetime as dt
import json
import os
import re
from pathlib import Path
from .request import require


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


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


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


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


