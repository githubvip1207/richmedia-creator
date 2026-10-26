"""获取并验证输出项，逐文件保存清单以支持中断恢复。

调用方须持有提交记录锁；输出项和图层处理规则由能力模块提供。
"""

import base64
import os
from pathlib import Path
from core.validation import require
from core.file_hash import sha256_file
from core.submission_store import write, now
from core.layers import position_metadata
from core import download, media_validate


def retrieve_outputs(record, record_path, result, entries, currency, layers=False):
    record_path = Path(record_path)
    d = record_path.parent
    state = record["execution"]
    plan = state
    require(
        state["state"] in ("succeeded", "partial_failed"),
        "Task not completed successfully; query status first",
    )
    state["download_complete"] = False
    write(record_path, record)
    output = d / ("output-" + record_path.stem.split("-")[1])
    legacy_output = d / "outputs" / record_path.stem
    if legacy_output.is_dir() and any(
        (
            Path(f["path"]).parent.resolve() == legacy_output.resolve()
            for f in record.get("result", {}).get("files", [])
        )
    ):
        output = legacy_output
    output.mkdir(mode=448, parents=True, exist_ok=True)
    require(bool(entries), "No downloadable media in response")
    previous = record.get("result", {}).get("files", [])
    manifest = []
    for i, (entry, kind) in enumerate(entries):
        fmt = entry.get(
            "output_format",
            (
                "jpeg"
                if entry.get("label") == "last-frame"
                else plan["compiled"]["parameters"]["output_format"]
            ),
        )
        if kind == "image" and entry.get("z_index", 0) > 0:
            fmt = "png"
        require(fmt in ("png", "jpeg", "mp4", "mov"), "Unexpected output format")
        if plan["compiled"]["kind"] == "image" and not layers:
            require(
                fmt == plan["compiled"]["parameters"]["output_format"],
                "Provider image format differs from confirmed format",
            )
        is_layer = layers
        label = (
            ("base" if entry["z_index"] == 0 else "layer")
            if is_layer
            else entry.get("label", "image")
        )
        name = "%02d-" % i + label + "." + fmt
        path = output / name
        previous_entry = next(
            (x for x in previous if Path(x["path"]).resolve() == path.resolve()), None
        )
        if not (
            previous_entry and path.is_file() and (sha256_file(path) == previous_entry["sha256"])
        ):
            tmp = path.with_suffix(path.suffix + ".part")
            if entry.get("b64_json"):
                tmp.write_bytes(base64.b64decode(entry["b64_json"], validate=True))
            else:
                url = entry.get("url", "")
                require(url.startswith("https://"), "Output URL must be HTTPS")
                download.download_url(url, tmp)
        else:
            tmp = path
        expected_size = entry["size"] if is_layer else plan["compiled"]["parameters"].get("size")
        actual_metadata = media_validate.video_metadata(tmp) if kind == "video" else None
        if actual_metadata:
            valid = True
        else:
            valid = (
                media_validate.valid_media(
                    tmp, kind, expected_size, require_alpha=entry["z_index"] > 0
                )
                if is_layer
                else media_validate.valid_media(tmp, kind)
            )
        require(valid, "Downloaded content is not valid media; retained file for inspection")
        if kind == "image":
            with tmp.open("rb") as stream:
                signature = stream.read(8)
            require(
                fmt == "png"
                and signature == b"\x89PNG\r\n\x1a\n"
                or (fmt == "jpeg" and signature.startswith(b"\xff\xd8\xff")),
                "Downloaded image format differs from confirmed format",
            )
        if tmp != path:
            os.replace(str(tmp), str(path))
        manifest.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "kind": kind,
                "verification": media_validate.verify_spec(
                    path, kind, plan["compiled"], actual_metadata,
                    record.get("estimate_context") or
                    state.get("cost_record", {}).get("calculation", {}).get("estimate_context")),
                **({"metadata": actual_metadata} if actual_metadata else {}),
                "origin": {k: v for k, v in entry.items() if k != "b64_json"},
                "provider": plan["compiled"]["provider"],
                "model": plan["compiled"]["payload_template"]["model"],
                "task_id": state.get("task_id"),
                "downloaded_at": now(),
                "original": True,
            }
        )
        record["result"] = {
            "files": manifest,
            "usage": result.get("usage"),
            "actual_billed_amount_cny": None,
            "billing_currency": currency,
            "actual_billed_amount": None,
            "note": "Original provider outputs preserved; actual paid amount is not returned by this API.",
        }
        write(record_path, record)
    if layers:
        from core.layers import position_metadata

        metadata_path = output / "layers.json"
        write(metadata_path, position_metadata(manifest))
        record["result"]["metadata"] = {
            "path": str(metadata_path),
            "sha256": sha256_file(metadata_path),
        }
    from core.cost_reconcile import reconcile
    audit = reconcile(record, result.get('usage'), manifest)
    record['result']['cost_comparison'] = audit
    state["download_complete"] = True
    write(record_path, record)
    return record["result"]
