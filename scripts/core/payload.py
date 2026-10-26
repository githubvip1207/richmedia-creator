"""将有序素材引用回填到已验证的 API 请求模板。"""

import json
from core.media_base64 import materialize


def payload(plan):
    data = json.loads(json.dumps(plan["compiled"]["payload_template"]))
    assets = plan["compiled"]["assets"]
    if plan["compiled"].get("native_payload"):
        return data
    if plan["compiled"]["kind"] == "image":
        if assets:
            data["image"] = [materialize(a) for a in assets]
    else:
        for item in data["content"]:
            for key in ("image_url", "video_url", "audio_url"):
                if key in item:
                    item[key]["url"] = materialize(assets[item[key]["url"]["asset_index"]])
    return data
