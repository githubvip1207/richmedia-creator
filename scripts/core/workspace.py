"""Create a private run directory; persist the agent-authored requirement record."""
import datetime as dt
import json
import os
from pathlib import Path

WORK_ROOT = Path('/tmp')


def initialize(content):
    """Validate stdin JSON before creating a run, then save it privately."""
    def reject_constant(value):
        raise ValueError('request.json must use finite JSON numbers')

    try:
        record = json.loads(content, parse_constant=reject_constant)
    except (ValueError, TypeError):
        raise ValueError('Provide a valid JSON object through stdin') from None
    if not isinstance(record, dict):
        raise ValueError('request.json must be a JSON object')
    timestamp = dt.datetime.now()
    while True:
        directory = WORK_ROOT / timestamp.strftime('richmedia-%Y%m%d%H%M%S')
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            timestamp += dt.timedelta(seconds=1)
            continue
        request = directory / 'request.json'
        try:
            with os.fdopen(os.open(str(request), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                           'w', encoding='utf-8') as output:
                output.write(content)
        except BaseException:
            if request.exists():
                request.unlink()
            directory.rmdir()
            raise
        return {'workdir': str(directory)}
