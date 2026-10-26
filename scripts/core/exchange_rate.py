"""获取美元兑人民币汇率、校验有效期，并原子更新项目配置。"""

import datetime as dt
import json
import math
import os
import tempfile
import urllib.request
from pathlib import Path
from core.envfile import read_config

FX_URL = "https://api.frankfurter.dev/v2/providers/ecb/rate/usd/cny"


def parse_expiry(value):
    """到期时间必须带时区，避免依赖主机本地时区。"""
    expiry = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise ValueError("Exchange rate expiration must include a timezone")
    return expiry


def validate_fx(fx):
    if not isinstance(fx, dict) or set(fx) != {"usd_cny", "expires_at"}:
        raise ValueError("fx requires usd_cny and expires_at")
    rate = fx["usd_cny"]
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("Exchange rate must be a finite positive number")
    if parse_expiry(fx["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
        raise ValueError("Exchange rate expired; run doctor --exchange-rate")
    return fx


def fx_state():
    """诊断缺失、无效、过期与有效，任何异常均不泄露密钥。"""
    values = read_config()
    if not values.get("USD_CNY") or not values.get("USD_CNY_EXPIRES_AT"):
        return {
            "status": "missing",
            "action": "Run doctor --exchange-rate or use native-currency quotes",
        }
    try:
        fx = {"usd_cny": float(values["USD_CNY"]), "expires_at": values["USD_CNY_EXPIRES_AT"]}
        validate_fx(fx)
    except (ValueError, TypeError, AttributeError, OverflowError):
        try:
            expired = parse_expiry(values["USD_CNY_EXPIRES_AT"]) <= dt.datetime.now(dt.timezone.utc)
        except (ValueError, TypeError, AttributeError, OverflowError):
            expired = False
        return {
            "status": "expired" if expired else "invalid",
            "action": "Run doctor --exchange-rate or use native-currency quotes",
        }
    return {"status": "ok", "expires_at": fx["expires_at"]}


def fx_from_env():
    """函数名沿用调用入口，但数据仅来自 .env；无有效汇率时返回 None。"""
    if fx_state()["status"] != "ok":
        return None
    values = read_config()
    return {"usd_cny": float(values["USD_CNY"]), "expires_at": values["USD_CNY_EXPIRES_AT"]}


def save_exchange_rate(rate, expiry):
    """原子更新两个汇率项，保留其他配置、行尾注释及换行风格；失败时不覆盖原文件。"""
    path = Path.cwd() / ".env"
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked .env")
    original = path.read_bytes() if path.exists() else b""
    text = original.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    values = {"USD_CNY": str(rate), "USD_CNY_EXPIRES_AT": expiry}
    import re

    found = set()
    output = []
    pattern = re.compile(
        "^(\\s*(?:export\\s+)?)(USD_CNY|USD_CNY_EXPIRES_AT)(\\s*=\\s*)(.*?)(\\r?\\n)?$"
    )
    for line in text.splitlines(keepends=True):
        match = pattern.match(line)
        if not match:
            output.append(line)
            continue
        prefix, key, separator, old, ending = match.groups()
        comment = re.search("\\s+#.*$", old)
        suffix = comment.group() if comment else ""
        output.append(prefix + key + separator + values[key] + suffix + (ending or ""))
        found.add(key)
    updated = "".join(output)
    for key, value in values.items():
        if key not in found:
            if updated and (not updated.endswith(("\n", "\r"))):
                updated += newline
            updated += key + "=" + value + newline
    fd, temp = tempfile.mkstemp(prefix=".env-fx-", dir=str(path.parent))
    try:
        os.fchmod(fd, path.stat().st_mode & 511 if path.exists() else 384)
        with os.fdopen(fd, "wb") as stream:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if (path.read_bytes() if path.exists() else b"") != original:
            raise ValueError(".env changed during update; retry exchange-rate repair")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def update_exchange_rate():
    """固定使用 ECB 数据源的 USD/CNY；缓存有效期为数据日期 UTC 零点起七天。"""
    request = urllib.request.Request(
        FX_URL, headers={"User-Agent": "RichMedia-Creator/1.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if (
        not isinstance(result, dict)
        or result.get("base", "").upper() != "USD"
        or result.get("quote", "").upper() != "CNY"
    ):
        raise ValueError("Unexpected exchange-rate currency pair")
    observation = dt.date.fromisoformat(result["date"])
    today = dt.datetime.now(dt.timezone.utc).date()
    if observation > today:
        raise ValueError("Exchange-rate observation is in the future")
    expiry = dt.datetime.combine(
        observation + dt.timedelta(days=7), dt.time.min, tzinfo=dt.timezone.utc
    ).isoformat()
    fx = validate_fx({"usd_cny": result["rate"], "expires_at": expiry})
    save_exchange_rate(fx["usd_cny"], expiry)
    return {
        "item": "exchange_rate",
        "status": "repaired",
        "rate": fx["usd_cny"],
        "expires_at": expiry,
        "data_date": observation.isoformat(),
        "source": FX_URL,
    }
