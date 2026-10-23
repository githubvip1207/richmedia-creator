"""doctor: repair dependencies or the project's exchange-rate configuration."""
import datetime as dt
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from core.envfile import fx_state, FX_URL
from core import dependencies
from .check import check


def run_installer(command):
    """不把安装器输出直接回显，避免外部配置或日志中的敏感信息进入诊断结果。"""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def repair_dependencies():
    results = []
    if dependencies.skill_status()['status'] != 'ok':
        if not shutil.which('npx'):
            results.append({'item': 'sd25-pe', 'status': 'failed', 'reason': 'npx is unavailable; install Node.js/npm first'})
        else:
            ok = run_installer(['npx', '--yes', 'skills@latest', 'add', 'https://arkdocs.tos-cn-beijing.volces.com/skills/',
                                '--skill', 'sd25-pe', '--global', '--yes'])
            results.append({'item': 'sd25-pe', 'status': 'repaired' if ok and dependencies.skill_status()['status'] == 'ok' else 'failed'})
    if not shutil.which('ffprobe'):
        if not shutil.which('brew'):
            results.append({'item': 'ffprobe', 'status': 'failed', 'reason': 'Homebrew is unavailable; install FFmpeg using your system package manager'})
        else:
            ok = run_installer(['brew', 'install', 'ffmpeg'])
            results.append({'item': 'ffprobe', 'status': 'repaired' if ok and shutil.which('ffprobe') else 'failed'})
    return results


def save_exchange_rate(rate, expiry):
    """原子更新两个汇率项，保留其他配置、行尾注释及换行风格；失败时不覆盖原文件。"""
    path = Path.cwd() / '.env'
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlinked .env')
    original = path.read_bytes() if path.exists() else b''
    text = original.decode('utf-8')
    newline = '\r\n' if '\r\n' in text else '\n'
    values = {'USD_CNY': str(rate), 'USD_CNY_EXPIRES_AT': expiry}
    import re
    found = set()
    output = []
    pattern = re.compile(r'^(\s*(?:export\s+)?)(USD_CNY|USD_CNY_EXPIRES_AT)(\s*=\s*)(.*?)(\r?\n)?$')
    for line in text.splitlines(keepends=True):
        match = pattern.match(line)
        if not match:
            output.append(line)
            continue
        prefix, key, separator, old, ending = match.groups()
        # 保留空白后开始的行尾注释；被引号包住的 # 属于原值，不当作注释。
        comment = re.search(r'\s+#.*$', old)
        suffix = comment.group() if comment else ''
        output.append(prefix + key + separator + values[key] + suffix + (ending or ''))
        found.add(key)
    updated = ''.join(output)
    for key, value in values.items():
        if key not in found:
            if updated and not updated.endswith(('\n', '\r')):
                updated += newline
            updated += key + '=' + value + newline
    fd, temp = tempfile.mkstemp(prefix='.env-fx-', dir=str(path.parent))
    try:
        os.fchmod(fd, (path.stat().st_mode & 0o777) if path.exists() else 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(updated.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        # 避免下载汇率期间其他进程修改配置后被静默覆盖。
        if (path.read_bytes() if path.exists() else b'') != original:
            raise ValueError('.env changed during update; retry exchange-rate repair')
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def update_exchange_rate():
    """固定使用 ECB 数据源的 USD/CNY；缓存有效期为数据日期 UTC 零点起七天。"""
    from core.envfile import validate_fx
    # 显式客户端标识与 JSON 接收类型，避免默认 Python 标识被公开接口网关拒绝。
    request = urllib.request.Request(FX_URL, headers={'User-Agent': 'RichMedia-Creator/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get('base', '').upper() != 'USD' or result.get('quote', '').upper() != 'CNY':
        raise ValueError('Unexpected exchange-rate currency pair')
    observation = dt.date.fromisoformat(result['date'])
    today = dt.datetime.now(dt.timezone.utc).date()
    if observation > today:
        raise ValueError('Exchange-rate observation is in the future')
    expiry = dt.datetime.combine(observation + dt.timedelta(days=7), dt.time.min, tzinfo=dt.timezone.utc).isoformat()
    fx = validate_fx({'usd_cny': result['rate'], 'expires_at': expiry})
    save_exchange_rate(fx['usd_cny'], expiry)
    return {'item': 'exchange_rate', 'status': 'repaired', 'rate': fx['usd_cny'],
            'expires_at': expiry, 'data_date': observation.isoformat(), 'source': FX_URL}


def doctor(dependencies=False, exchange_rate=False):
    """无选项时修复缺失依赖及异常汇率；定向参数只处理指定类别，最后始终复查。"""
    all_items = not dependencies and not exchange_rate
    results = repair_dependencies() if dependencies or all_items else []
    if exchange_rate or (all_items and fx_state()['status'] != 'ok'):
        try:
            results.append(update_exchange_rate())
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            detail = ('HTTP ' + str(error.code)) if isinstance(error, urllib.error.HTTPError) else type(error).__name__
            results.append({'item': 'exchange_rate', 'status': 'failed', 'reason': 'Could not obtain a valid fresh rate (' + detail + '); previous .env values were preserved'})
    report = check()
    return {'repairs': results, 'check': report,
            'note': 'Missing API keys must be supplied locally. No media generation was submitted.'}


def run(args):
    return doctor(args.dependencies, args.exchange_rate)
