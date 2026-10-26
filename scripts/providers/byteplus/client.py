# BytePlus 薄适配层：固定海外端点与 BYTEPLUS_API_KEY，保持供应商账户隔离。
# 与国内适配器共享传输实现，仅使用 BYTEPLUS_API_KEY。
"""BytePlus 适配器；供应商和账户均与火山引擎独立。"""

from urllib.parse import quote
from core.http import ProviderError
from core.payload import payload
from core import http as transport

# 固定海外 API 主机；KEY_ENV 与国内密钥变量不同，不做跨供应商回退。
BASE = "https://ark.ap-southeast.bytepluses.com/api/v3"
KEY_ENV = "BYTEPLUS_API_KEY"


# 绑定本供应商固定基础地址、独立密钥变量及显示名称，复用共享传输函数。
# payload 参数仅传递当前请求正文，不改变供应商选择。
def request(method, path, payload=None, *, timeout=None):
    if timeout is not None:
        return transport.request(BASE, KEY_ENV, "BytePlus", method, path, payload, timeout=timeout)
    return transport.request(BASE, KEY_ENV, "BytePlus", method, path, payload)


# 对已有任务执行只读 GET；对任务 ID 做路径编码，避免 ID 被解释为额外路径或查询参数。
def status(task_id, *, timeout=None):
    path = status_path(task_id)
    return request("GET", path) if timeout is None else request("GET", path, timeout=timeout)


def status_path(task_id):
    return "/contents/generations/tasks/" + quote(task_id, safe="")
