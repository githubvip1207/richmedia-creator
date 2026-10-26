"""管理提交标识、时间戳和重复提交保护。"""

import datetime as dt
import re
from pathlib import Path
from core.validation import require
from core.file_io import read, write
from core.file_lock import lock


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def submission_records(directory):
    return sorted(
        (
            p
            for p in Path(directory).glob("submit-*.json")
            if re.fullmatch("submit-[0-9]+\\.json", p.name)
        ),
        key=lambda p: int(p.stem.split("-")[1]),
    )


def submission_path(target):
    path = Path(target).resolve()
    if path.is_dir():
        records = submission_records(path)
        require(bool(records), "No submission record found")
        return records[-1]
    require(
        path.is_file() and re.fullmatch("submit-[0-9]+\\.json", path.name),
        "Provide an existing submit-NNN.json file",
    )
    return path


def prior_submission(directory):
    """此前所有提交均有明确终态后，才允许开始新的提交尝试。"""
    previous = None
    for path in submission_records(directory):
        previous = read(path)["execution"]
        require(
            previous.get("state")
            in ("succeeded", "partial_failed", "rejected", "failed", "expired", "cancelled"),
            "This task was already attempted and is active or its submission outcome unknown; query/reconcile it before a new submission",
        )
    return previous


def next_submit_record(directory):
    """须在持有任务目录锁时调用，绝不覆盖已有编号的提交记录。"""
    numbers = [
        int(match.group(1))
        for path in directory.glob("submit-*.json")
        if (match := re.fullmatch("submit-([0-9]+)\\.json", path.name))
    ]
    return directory / ("submit-%03d.json" % (max(numbers, default=0) + 1))
