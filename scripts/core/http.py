"""官方 Ark REST 传输，不使用 SDK 的重试策略，也不接受自定义凭证端点。"""

import json
from core.envfile import config_value
import re
import urllib.error
import urllib.request


class ProviderError(RuntimeError):

    def __init__(self, message, uncertain=False, details=None):
        super().__init__(message)
        self.uncertain = uncertain
        self.details = details


def sanitized(value, secrets=()):
    """保留诊断信息，同时移除密钥、签名 URL 和内嵌媒体。"""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for secret in secrets:
        if isinstance(secret, str) and secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub("data:[^\\s]+", "<media>", text, flags=re.I)
    text = re.sub("https?://[^\\s<>]+", "<url>", text)
    text = re.sub("(?i)(bearer\\s+)[^\\s,;]+", "\\1<redacted>", text)
    text = re.sub(
        "(?i)(api[_-]?key|token|password)(\\s*[:=]\\s*)[^\\s,;]+", "\\1\\2<redacted>", text
    )
    return text[:500]


def response_error(
    error,
    *,
    http_status=None,
    request_id="",
    provider_name="Provider",
    secrets=(),
    is_submission=False
):
    """统一处理 HTTP 错误和同步响应顶层的错误对象。"""
    secrets = tuple(secrets) + tuple(
        (config_value(k) for k in ("VOLCENGINE_API_KEY", "BYTEPLUS_API_KEY"))
    )
    error = error if isinstance(error, dict) else {"message": error}
    details = {
        "code": sanitized(error.get("code", "unknown"), secrets),
        "message": sanitized(error.get("message", "Provider returned no error message"), secrets),
        "request_id": sanitized(request_id or error.get("request_id", ""), secrets),
    }
    if http_status is not None:
        details["http_status"] = http_status
    prefix = provider_name + (" HTTP " + str(http_status) if http_status is not None else " error")
    message = (
        prefix
        + "; code="
        + details["code"]
        + "; message="
        + details["message"]
        + "; request_id="
        + details["request_id"]
    )
    return ProviderError(
        message,
        uncertain=is_submission
        and http_status is not None
        and (http_status >= 500 or http_status in (408, 429)),
        details=details,
    )


def sanitize_response(result, *, secrets=()):
    """保留成功媒体字段，替换所有供应商错误对象以完成脱敏。"""
    if isinstance(result, list):
        return [sanitize_response(item, secrets=secrets) for item in result]
    if not isinstance(result, dict):
        return result
    return {
        key: (
            response_error(value, secrets=secrets).details
            if key == "error" and value
            else sanitize_response(value, secrets=secrets)
        )
        for key, value in result.items()
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(base, key_env, provider_name, method, path, payload=None, *, timeout=None):
    key = config_value(key_env)
    if not key:
        raise ValueError(key_env + " is not configured; configure it outside chat and source files")
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    if data is not None and len(data) > 64 * 1024 * 1024:
        raise ValueError("Request exceeds 64 MB; use approved HTTPS asset URLs")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    request_timeout = 180 if method == "POST" else 25
    if timeout is not None:
        request_timeout = min(request_timeout, timeout)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=request_timeout) as response:
            result = json.load(response)
            if not isinstance(result, dict):
                raise ValueError("Non-object API response")
            return result
    except urllib.error.HTTPError as e:
        rid = e.headers.get("X-Request-Id", "")
        error = {}
        try:
            body = json.loads(e.read())
            error = body.get("error", {}) if isinstance(body, dict) else {}
        except (ValueError, AttributeError):
            pass
        finally:
            e.close()
        secrets = [key]
        if isinstance(payload, dict):
            secrets.append(payload.get("prompt"))
            secrets.extend(
                (item.get("text") for item in payload.get("content", []) if isinstance(item, dict))
            )
        raise response_error(
            error,
            http_status=e.code,
            request_id=rid,
            provider_name=provider_name,
            secrets=secrets,
            is_submission=method == "POST",
        ) from None
    except (OSError, ValueError) as e:
        detail = type(e).__name__
        if isinstance(e, OSError):
            reason = getattr(e, "reason", e)
            reason_type = type(reason).__name__
            reason_text = str(reason).replace("\r", " ").replace("\n", " ")
            reason_text = re.sub("https?://[^\\s<>]+", "<url>", reason_text)
            reason_text = re.sub("(?i)(bearer\\s+)[^\\s,;]+", "\\1<redacted>", reason_text)
            reason_text = re.sub(
                "(?i)(api[_-]?key|token|password)(\\s*[:=]\\s*)[^\\s,;]+",
                "\\1\\2<redacted>",
                reason_text,
            )
            detail = reason_type + ": " + reason_text[:240]
        raise ProviderError(
            provider_name
            + " transport/response failure ("
            + detail
            + "); do not automatically resubmit",
            uncertain=method == "POST",
        ) from None
