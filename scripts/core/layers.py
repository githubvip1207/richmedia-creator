"""校验并导出供应商返回的图层几何信息，不虚构坐标。"""

import re
from core.validation import require


def dimensions(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*x[1-9][0-9]*", value),
        "Layer response requires valid size",
    )
    return tuple(map(int, value.split("x")))


def validate_layer_outputs(entries):
    require(
        isinstance(entries, list) and 1 <= len(entries) <= 17,
        "Layer response must contain 1..17 outputs",
    )
    require(
        all(
            isinstance(e, dict)
            and not e.get("error")
            and type(e.get("z_index")) is int
            and 0 <= e["z_index"] <= 16
            for e in entries
        ),
        "Invalid layer z_index or error",
    )
    indexes = [e["z_index"] for e in entries]
    require(
        len(set(indexes)) == len(indexes) and 0 in indexes,
        "Layer response requires one base and unique z_index values",
    )
    base = next(e for e in entries if e["z_index"] == 0)
    width, height = dimensions(base.get("size"))
    for entry in entries:
        dimensions(entry.get("size"))
        require(entry.get("output_format") == "png", "Layer outputs must be PNG")
        if entry["z_index"] == 0:
            continue
        require(
            all(isinstance(entry.get(key), str) for key in ("name", "description")),
            "Layer response missing name/description",
        )
        box = entry.get("bounding_box")
        require(isinstance(box, dict), "Layer response missing bounding_box")
        for key, xmax, ymax in (("absolute", width, height), ("normalized", 1000, 1000)):
            coords = box.get(key)
            require(
                isinstance(coords, list)
                and len(coords) == 4
                and all(type(v) is int for v in coords),
                "Invalid layer bounding_box." + key,
            )
            left, top, right, bottom = coords
            require(
                0 <= left < right <= xmax and 0 <= top < bottom <= ymax,
                "Layer bounding_box outside output canvas",
            )
    return sorted(entries, key=lambda e: e["z_index"])


def position_metadata(files):
    """生成可移植的配套元数据：使用媒体相对文件名，不包含临时 URL 或 API 用量。"""
    from pathlib import Path

    base = next(f for f in files if f["origin"]["z_index"] == 0)
    width, height = dimensions(base["origin"]["size"])
    return {
        "schema_version": 1,
        "provider": base["provider"],
        "model": base["model"],
        "canvas": {"width": width, "height": height},
        "coordinates": {
            "absolute": "output-base pixels: [left, top, right, bottom]",
            "normalized": "output-base coordinates divided by 1000",
        },
        "layers": [
            {
                "file": Path(f["path"]).name,
                "sha256": f["sha256"],
                **{
                    k: f["origin"][k]
                    for k in (
                        "z_index",
                        "size",
                        "output_format",
                        "bounding_box",
                        "name",
                        "description",
                    )
                    if k in f["origin"]
                },
            }
            for f in sorted(files, key=lambda f: f["origin"]["z_index"])
        ],
    }
