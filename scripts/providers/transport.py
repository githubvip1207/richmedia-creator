# 共享 HTTPS 传输：凭证只发送到固定供应商主机，禁止携带凭证重定向。
# 付费 POST 不自动重试；错误只保留脱敏摘要，避免响应回显密钥、素材 URL 或请求正文。
"""Official Ark REST transport. No SDK retry policy and no custom credential endpoint."""
import json
from core.envfile import config_value
import re
import urllib.error
import urllib.request
from core.assets import materialize

# 供应商错误类型：uncertain 标记提交是否可能已被接受或计费。
# 该标记指导恢复状态，不能凭错误就擅自进行下一次付费尝试。
class ProviderError(RuntimeError):
    # 保留脱敏错误摘要与结果不确定性；不把完整 HTTP 响应正文写入异常。
    def __init__(self, message, uncertain=False, details=None):
        super().__init__(message)
        self.uncertain = uncertain
        self.details = details


def sanitized(value, secrets=()):
    """Retain diagnostic text while removing keys, signed URLs and inline media."""
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, '<redacted>')
    text = re.sub(r'data:[^\s]+', '<media>', text, flags=re.I)
    text = re.sub(r'https?://[^\s<>]+', '<url>', text)
    text = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1<redacted>', text)
    text = re.sub(r'(?i)(api[_-]?key|token|password)(\s*[:=]\s*)[^\s,;]+',
                  r'\1\2<redacted>', text)
    return text[:500]


def response_error(error, *, http_status=None, request_id='', provider_name='Provider', secrets=(), is_submission=False):
    """Normalize both HTTP errors and a synchronous top-level error response."""
    secrets = tuple(secrets) + tuple(config_value(k) for k in ('VOLCENGINE_API_KEY', 'BYTEPLUS_API_KEY'))
    error = error if isinstance(error, dict) else {'message': error}
    details = {'code': sanitized(error.get('code', 'unknown'), secrets),
               'message': sanitized(error.get('message', 'Provider returned no error message'), secrets),
               'request_id': sanitized(request_id or error.get('request_id', ''), secrets)}
    if http_status is not None:
        details['http_status'] = http_status
    prefix = provider_name + (' HTTP ' + str(http_status) if http_status is not None else ' error')
    message = prefix + '; code=' + details['code'] + '; message=' + details['message'] + '; request_id=' + details['request_id']
    return ProviderError(message, uncertain=is_submission and http_status is not None and (http_status >= 500 or http_status in (408, 429)), details=details)


def sanitize_response(result, *, secrets=()):
    """Preserve successful media fields; replace all provider error objects."""
    if isinstance(result, list):
        return [sanitize_response(item, secrets=secrets) for item in result]
    if not isinstance(result, dict):
        return result
    return {key: (response_error(value, secrets=secrets).details
                  if key == 'error' and value else sanitize_response(value, secrets=secrets))
            for key, value in result.items()}


# 禁止认证请求重定向，避免 Authorization 请求头被转发至其他主机。
class NoRedirect(urllib.request.HTTPRedirectHandler):
    # 返回 None 使 urllib 拒绝自动跟随跳转，而不是重建携带密钥的请求。
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward the API credential to redirected destinations.


# 用所选供应商密钥构造 JSON 请求，限制请求体为 64 MiB，且只接受对象响应。
# POST 超时 180 秒、其他请求 25 秒；任何失败都交回调用方处理，不在此循环重试。
def request(base, key_env, provider_name, method, path, payload=None, *, timeout=None):
    # 只读取 .env 中当前适配器指定的密钥配置，缺失时在构造网络请求之前停止。
    key = config_value(key_env)
    if not key:
        raise ValueError(key_env + ' is not configured; configure it outside chat and source files')
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    if data is not None and len(data) > 64*1024*1024:
        raise ValueError('Request exceeds 64 MB; use approved HTTPS asset URLs')
    # Authorization 只附加给固定 API 主机；不把密钥写到 payload、计划或错误消息。
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'})
    request_timeout = 180 if method == 'POST' else 25
    if timeout is not None:
        request_timeout = min(request_timeout, timeout)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=request_timeout) as response:
            result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError('Non-object API response')
            return result
    # 已收到 HTTP 错误时仍不重试生成；只提取状态、错误码和请求 ID 供排查。
    except urllib.error.HTTPError as e:
        # 完整响应正文可能回显私有 URL 或输入参数，因此不保存或直接打印错误正文。
        # Do not print raw responses: provider errors can echo input URLs/payloads/secrets.
        rid = e.headers.get('X-Request-Id', '')
        error = {}
        try:
            body = json.loads(e.read())
            error = body.get('error', {}) if isinstance(body, dict) else {}
        except (ValueError, AttributeError):
            pass
        finally:
            e.close()
        # Never retain the raw body. Known request text is redacted if echoed by the API.
        secrets = [key]
        if isinstance(payload, dict):
            secrets.append(payload.get('prompt'))
            secrets.extend(item.get('text') for item in payload.get('content', []) if isinstance(item, dict))
        raise response_error(error, http_status=e.code, request_id=rid,
                             provider_name=provider_name, secrets=secrets, is_submission=method == 'POST') from None
    # 传输失败或非预期 JSON 响应不能证明生成未发生；POST 均按结果未知处理。
    except (OSError, ValueError) as e:
        detail = type(e).__name__
        if isinstance(e, OSError):
            reason = getattr(e, 'reason', e)
            reason_type = type(reason).__name__
            # 保留有用的底层诊断，同时去掉换行、URL、Bearer 及常见密钥字段的敏感值。
            reason_text = str(reason).replace('\r', ' ').replace('\n', ' ')
            reason_text = re.sub(r'https?://[^\s<>]+', '<url>', reason_text)
            reason_text = re.sub(r'(?i)(bearer\s+)[^\s,;]+', r'\1<redacted>', reason_text)
            reason_text = re.sub(r'(?i)(api[_-]?key|token|password)(\s*[:=]\s*)[^\s,;]+',
                                 r'\1\2<redacted>', reason_text)
            detail = reason_type + ': ' + reason_text[:240]
        # POST 的 5xx、408、429 保守标记为不确定；调用方据此保留恢复状态。
        raise ProviderError(provider_name + ' transport/response failure ('+detail+'); do not automatically resubmit',
                            uncertain=method == 'POST') from None


# 深拷贝任务配置的 API 模板，把素材索引替换成远程地址或刚编码的本地 data URI。
# 不修改原配置，也不持久化含 Base64 的完整提交正文。
def payload(plan):
    data = json.loads(json.dumps(plan['compiled']['payload_template']))
    assets = plan['compiled']['assets']
    if plan['compiled'].get('native_payload'):
        return data
    # 图片用独立 image 数组；视频按 content 中的 asset_index 回填并保留角色。
    if plan['compiled']['kind'] == 'image':
        if assets:
            data['image'] = [materialize(a) for a in assets]
    else:
        for item in data['content']:
            for key in ('image_url','video_url','audio_url'):
                if key in item:
                    item[key]['url'] = materialize(assets[item[key]['url']['asset_index']])
    return data
