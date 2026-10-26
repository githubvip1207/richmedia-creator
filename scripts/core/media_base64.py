"""将未变化的本地媒体转换为数据 URI，远程素材来源保持原样。"""

import base64
import hashlib


def materialize(asset):
    if asset["transport"] != "local-base64":
        return asset["source"]
    with open(asset["source"], "rb") as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError("Local asset changed after confirmation; update the task and reconfirm")
    return "data:" + asset["metadata"]["mime"] + ";base64," + base64.b64encode(data).decode("ascii")
