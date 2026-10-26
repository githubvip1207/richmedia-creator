"""定义估价和提交共用的七种公开能力及其模式。"""

OPERATIONS = {
    "text-to-image": {},
    "image-to-image": {},
    "decompose-layers": {},
    "text-to-video": {},
    "image-to-video": {},
    "reference-to-video": {"reference": "reference-to-video", "edit": "edit-video"},
    "extend-video": {"before": "extend-video", "after": "extend-video"},
}


def internal_operation(spec):
    """将公开能力及模式转换为内部校验和 API 路由类型。"""
    operation = spec.get("operation")
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError("operation must be one of: " + ", ".join(OPERATIONS))
    if operation == "image-to-video":
        if "mode" in spec:
            raise ValueError(
                "image-to-video does not accept mode; use one or two ordered image assets"
            )
        assets = spec.get("assets")
        count = len(assets) if isinstance(assets, list) else spec.get("input_images")
        if type(count) is not int or count not in (1, 2):
            raise ValueError("image-to-video requires one or two ordered image assets")
        return "first-frame" if count == 1 else "first-last-frame"
    modes = OPERATIONS[operation]
    mode = spec.get("mode")
    if modes:
        if not isinstance(mode, str) or mode not in modes:
            raise ValueError(operation + " requires mode: " + ", ".join(modes))
        return modes[mode]
    if mode is not None:
        raise ValueError(operation + " does not accept mode")
    return operation


def require_supported_operation(spec):
    """实际执行与估价采用相同的能力支持范围。"""
    if spec.get("provider") not in ("volcengine", "byteplus") or spec.get("operation") not in (
        "text-to-image",
        "image-to-image",
        "decompose-layers",
        "text-to-video",
        "image-to-video",
        "reference-to-video",
        "extend-video",
    ):
        raise ValueError(
            "Select one of the seven implemented capabilities for Volcengine or BytePlus"
        )
