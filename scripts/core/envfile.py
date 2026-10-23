"""项目 .env 配置及汇率有效期；不执行文件，不读取业务环境变量。"""
import datetime as dt
import math
import re
from pathlib import Path

ALLOWED = {'VOLCENGINE_API_KEY', 'BYTEPLUS_API_KEY', 'USD_CNY', 'USD_CNY_EXPIRES_AT'}
FX_URL = 'https://api.frankfurter.dev/v2/providers/ecb/rate/usd/cny'


def load_project_env(directory=None):
    """返回实际配置文件路径；是否包含所需配置由检查结果单独报告。"""
    path = Path(directory or Path.cwd()) / '.env'
    return str(path.resolve()) if path.is_file() else None


def read_config(directory=None):
    """只解析白名单赋值；保留 export 书写兼容，不做变量插值或执行。"""
    path = load_project_env(directory)
    values = {}
    if path is None:
        return values
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        if '=' not in line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if key not in ALLOWED:
            continue
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (value[end + 1:].strip() and not value[end + 1:].lstrip().startswith('#')):
                raise ValueError('Invalid quoted .env value for ' + key)
            value = value[1:end]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def config_value(key):
    return read_config().get(key)


def parse_expiry(value):
    """到期时间必须带时区，避免依赖主机本地时区。"""
    expiry = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError('Exchange rate expiration must include a timezone')
    return expiry


def validate_fx(fx):
    if not isinstance(fx, dict) or set(fx) != {'usd_cny', 'expires_at'}:
        raise ValueError('fx requires usd_cny and expires_at')
    rate = fx['usd_cny']
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError('Exchange rate must be a finite positive number')
    if parse_expiry(fx['expires_at']) <= dt.datetime.now(dt.timezone.utc):
        raise ValueError('Exchange rate expired; run doctor --exchange-rate')
    return fx


def fx_state():
    """诊断缺失、无效、过期与有效，任何异常均不泄露密钥。"""
    values = read_config()
    if not values.get('USD_CNY') or not values.get('USD_CNY_EXPIRES_AT'):
        return {'status': 'missing', 'action': 'Run doctor --exchange-rate or use native-currency quotes'}
    try:
        fx = {'usd_cny': float(values['USD_CNY']), 'expires_at': values['USD_CNY_EXPIRES_AT']}
        validate_fx(fx)
    except (ValueError, TypeError, AttributeError, OverflowError):
        try:
            expired = parse_expiry(values['USD_CNY_EXPIRES_AT']) <= dt.datetime.now(dt.timezone.utc)
        except (ValueError, TypeError, AttributeError, OverflowError):
            expired = False
        return {'status': 'expired' if expired else 'invalid', 'action': 'Run doctor --exchange-rate or use native-currency quotes'}
    return {'status': 'ok', 'expires_at': fx['expires_at']}


def fx_from_env():
    """函数名沿用调用入口，但数据仅来自 .env；无有效汇率时返回 None。"""
    if fx_state()['status'] != 'ok':
        return None
    values = read_config()
    return {'usd_cny': float(values['USD_CNY']), 'expires_at': values['USD_CNY_EXPIRES_AT']}
