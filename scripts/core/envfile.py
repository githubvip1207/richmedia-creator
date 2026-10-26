"""项目 .env 配置及汇率有效期；不执行文件，不读取业务环境变量。"""

import datetime as dt
import math
import re
from pathlib import Path

ALLOWED = {"VOLCENGINE_API_KEY", "BYTEPLUS_API_KEY", "USD_CNY", "USD_CNY_EXPIRES_AT"}


def load_project_env(directory=None):
    """返回实际配置文件路径；是否包含所需配置由检查结果单独报告。"""
    path = Path(directory or Path.cwd()) / ".env"
    return str(path.resolve()) if path.is_file() else None


def read_config(directory=None):
    """只解析白名单赋值；保留 export 书写兼容，不做变量插值或执行。"""
    path = load_project_env(directory)
    values = {}
    if path is None:
        return values
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = (key.strip(), value.strip())
        if key not in ALLOWED:
            continue
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            if end < 0 or (
                value[end + 1 :].strip() and (not value[end + 1 :].lstrip().startswith("#"))
            ):
                raise ValueError("Invalid quoted .env value for " + key)
            value = value[1:end]
        else:
            value = re.split("\\s+#", value, maxsplit=1)[0].rstrip()
        values[key] = value
    return values


def config_value(key):
    return read_config().get(key)
