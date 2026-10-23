# Volcengine 薄适配层：固定国内端点与 VOLCENGINE_API_KEY，将请求交给公共传输实现。
# 不切换至 BytePlus，不复用其密钥、任务或账户素材。
"""Volcengine ModelArk adapter; credentials never fall back to BytePlus."""
from urllib.parse import quote
from .transport import ProviderError, payload
from . import transport

# 固定北京 API 主机；当前适配器只读取 VOLCENGINE_API_KEY。
BASE = 'https://ark.cn-beijing.volces.com/api/v3'
KEY_ENV = 'VOLCENGINE_API_KEY'


# 绑定本供应商固定基础地址、独立密钥变量及显示名称，复用共享传输函数。
# payload 参数仅传递当前请求正文，不改变供应商选择。
def request(method, path, payload=None, *, timeout=None):
    if timeout is not None:
        return transport.request(BASE, KEY_ENV, 'Volcengine', method, path, payload, timeout=timeout)
    return transport.request(BASE, KEY_ENV, 'Volcengine', method, path, payload)


# 对已有任务执行只读 GET；对任务 ID 做路径编码，避免 ID 被解释为额外路径或查询参数。
def status(task_id, *, timeout=None):
    path = '/contents/generations/tasks/' + quote(task_id, safe='')
    return request('GET', path) if timeout is None else request('GET', path, timeout=timeout)
