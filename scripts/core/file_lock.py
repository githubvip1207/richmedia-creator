"""使用非阻塞的跨进程目录锁。"""

import contextlib
from pathlib import Path


@contextlib.contextmanager
def lock(jobdir):
    import fcntl

    with open(Path(jobdir) / ".lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
