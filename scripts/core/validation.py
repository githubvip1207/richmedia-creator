"""与供应商规则无关的基础校验函数。"""

import math


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)
