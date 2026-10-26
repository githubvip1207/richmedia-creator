"""在分配 Base64 内容前预估编码后的图片请求大小。"""

import json


def validate_image_request_size(assets, template=None):
    """提交前检查 JSON 和数据 URI 的大小，不预先分配 Base64 内容。"""
    body = dict(template or {})
    images, encoded_bytes = ([], 0)
    for asset in assets:
        metadata = asset.get("metadata", {})
        if asset["source"].startswith("https://"):
            images.append(asset["source"])
        else:
            images.append("data:" + metadata["mime"] + ";base64,")
            encoded_bytes += 4 * ((metadata["bytes"] + 2) // 3)
    body["image"] = images
    if len(json.dumps(body, ensure_ascii=False).encode()) + encoded_bytes > 64 * 1024 * 1024:
        raise ValueError(
            "Request exceeds 64 MB after Base64 encoding; use approved HTTPS asset URLs"
        )
