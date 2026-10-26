"""对媒体 GET 下载设置等待上限；此处绝不重试生成请求。"""

from core import process
import http.client
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from core.validation import require


def download_with_curl(executable, url, destination):
    """下载媒体时限制连接和停滞等待，不执行生成 POST。"""
    require(
        url.startswith("https://") and (not any((ord(c) < 32 for c in url))),
        "Output URL must be HTTPS without control characters",
    )
    escaped = url.replace("\\", "\\\\").replace('"', '\\"')
    try:
        result = process.run(
            [
                executable,
                "-q",
                "--config",
                "-",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--connect-timeout",
                "15",
                "--speed-limit",
                "1024",
                "--speed-time",
                "20",
                "--max-time",
                "900",
                "--user-agent",
                "richmedia-creator/1.0",
                "--output",
                str(destination),
                "--write-out",
                "%{http_code}",
            ],
            input='url = "' + escaped + '"\n',
            capture_output=True,
            text=True,
            timeout=915,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError("Media transfer exceeded total timeout") from None
    if result.returncode:
        status = result.stdout.strip()
        if status.isdigit() and int(status) >= 400:
            raise urllib.error.HTTPError(url, int(status), "Media HTTP error", {}, None)
        raise OSError("Media transport curl exit %s" % result.returncode)


def download_url(url, destination):
    """仅重试媒体 GET；每次尝试均替换未下载完整的文件。"""
    for attempt in range(3):
        try:
            curl = shutil.which("curl")
            if curl:
                download_with_curl(curl, url, destination)
                return
            request = urllib.request.Request(url, headers={"User-Agent": "richmedia-creator/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response, open(
                destination, "wb"
            ) as f:
                require(response.geturl().startswith("https://"), "Refuse HTTPS downgrade")
                received = 0
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                expected = response.headers.get("Content-Length")
                if expected is not None and received != int(expected):
                    raise http.client.IncompleteRead(b"", max(0, int(expected) - received))
            return
        except (OSError, urllib.error.URLError, http.client.IncompleteRead) as error:
            retryable = not isinstance(error, urllib.error.HTTPError) or error.code in (
                408,
                429,
                500,
                502,
                503,
                504,
            )
            if isinstance(error, urllib.error.HTTPError):
                error.close()
            if not retryable or attempt == 2:
                detail = (
                    "HTTP %s" % error.code
                    if isinstance(error, urllib.error.HTTPError)
                    else (
                        str(error)
                        if str(error).startswith("Media transport curl exit ")
                        else type(error).__name__
                    )
                )
                raise RuntimeError(
                    "Media download failed after %s attempt(s): %s; generation is preserved, retry deliver only"
                    % (attempt + 1, detail)
                ) from None
            time.sleep(2 ** (attempt + 1))
