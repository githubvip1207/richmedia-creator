r"""命令行调用

    python3 "$SKILL/scripts/main.py" deliver --submission /absolute/submit-001.json

    # --submission：必填，由 submit 生成的提交记录 JSON 文件。
    # 交付目标为当前项目目录；CLI 没有 --destination 参数。

输入文件格式

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

--submission 指向 submit-NNN.json，必须使用 submit 自动保存的完整记录；
不能仅提供 task_id，也不是原始 task-spec.json。
该文件与 submit.py 的文件输出完全相同，JSON 格式统一见 submit.py 的“文件输出格式”，此处不重复。
其中 execution.compiled 决定供应商与能力，execution.task_id 用于视频查询；
视频交付还使用 queries 中最近一次成功响应的 content.video_url。

标准输出格式

```jsonc
{
  "directory": "/absolute/delivery", // string；实际交付子目录绝对路径，不覆盖用户已有文件。
  "files": [ // DeliveredFile[]；仅已验证媒体文件；不包含过程记录、输入素材或 layers.json。
    {
      "path": "/absolute/delivery/output.mp4", // string；交付文件绝对路径。
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000", // string；交付文件内容 SHA-256。
      "verification": {}, // OutputVerification?；完整字段见 commands/__init__.py；不是空对象。
      "kind": "video", // "image" | "video"?；从输出清单继承的媒体类型；正常交付会提供。
      "provider": "volcengine", // Provider?；从输出清单继承的供应商标识。
      "model": "doubao-seedance-2-5-260628", // string?；从输出清单继承的准确模型 ID。
      "metadata": { // VideoMetadata?；视频实测规格；图像通常省略。
        "width": 854, // integer；输出视频编码像素宽。
        "height": 480, // integer；输出视频编码像素高。
        "duration": 5, // number；输出视频实测秒数，可能不是整数。
        "codec": "h264", // string | null；输出视频编解码器名称。
        "frame_rate": "24/1", // string | null；ffprobe 平均帧率表达式，例如 24/1。
        "has_audio": false // boolean；输出文件是否包含音轨。
      }
    }
  ],
  "delivered_at": "2026-10-26T00:01:00+00:00", // string；交付记录创建时间，UTC ISO 8601。
  "metadata": { // object?；图层拆分时额外输出的位置元数据文件信息。
    "path": "/absolute/delivery/layers.json", // string；layers.json 的交付绝对路径。
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000" // string；位置元数据文件 SHA-256。
  },
  "cost_comparison": { // CostComparison?；生成后费用核对结果，旧交付记录可能没有。
    "status": "compared", // "compared" | "partial" | "unavailable"；完整核对、部分核对或缺少历史报价。
    "reason": "示例说明：输出时长由模型自动决定", // string?；部分/无法核对的原因；unavailable 时可仅返回此字段及 status。
    "currency": "CNY", // "CNY" | "USD"?；核对使用的报价原币。
    "estimated_amount": { // Amount?；提交时原币报价范围；定义见 commands/__init__.py。
      "min": 1.0, // number | null；估算范围起点；null 表示未知，不能按 0 理解。
      "max": 2.0 // number | null；估算范围终点；不是账单封顶；null 表示未知。
    },
    "outputs": [ // OutputObservation[]?；逐个实际输出的规格或单价。
      {
        "dimensions": [1024, 1024], // [integer,integer] | null?；图片实测 [宽,高]；无法读取时 null。
        "unit_price": 1.0, // number?；图片尺寸可读取时的对应像素档单价。
        "unit_price_range": [0.15, 0.3] // Pair?；图片尺寸无法读取时保留的低/高像素档单价范围。
      }
    ],
    "actual_billed_amount": null, // null?；API 不提供账户实付账单，不能用刊例核算代替。
    "basis": "示例计费依据", // string?；按提交时刊例单价核算、区别于实付账单的说明。
    "actual_tokens": 1, // integer?；视频 API usage.completion_tokens 实际值。
    "estimated_tokens": [86400, 86400], // Pair | null?；视频提交时计费 Token 估算范围。
    "usage_cost_at_list_price": 1.0, // number?；视频实际 Token 乘以提交时刊例单价的费用。
    "difference_percent_outside_estimate": 1.0, // number | null?；金额超出估算范围百分比；范围内 0，低于范围为负。
    "token_difference_percent_outside_estimate": 1.0, // number | null?；视频 Token 超出其估算范围百分比。
    "assumed_dimensions": [854, 480], // [integer,integer] | null?；视频原先假定的输出 [宽,高]。
    "assumed_duration": [4, 30], // Pair | null?；视频原先假定的输出秒数范围。
    "output_count": 2, // integer?；图片/图层实际输出数量，拆层含底图。
    "observed_output_cost_at_list_price": { // Amount?；图片按实际数量/像素档及额外输入图费计算的刊例费用。
      "min": 1.0, // number | null；估算范围起点；null 表示未知，不能按 0 理解。
      "max": 2.0 // number | null；估算范围终点；不是账单封顶；null 表示未知。
    }
  }
}
```

文件输出格式

- <directory>/ 下的媒体文件：PNG/JPEG 图片或 MP4/MOV 视频，路径见标准输出 files[].path；不是 JSON 文件。
- 更新 submit-NNN.json：增加下载结果 result 和交付记录 delivery；delivery 与上述标准输出完全相同，不重复描述。
- 图层拆分额外输出 <directory>/layers.json，格式如下；metadata.path 指向该文件。

```jsonc
{
  "schema_version": 1, // 1；图层元数据结构版本。
  "provider": "volcengine", // Provider；生成图层的供应商。
  "model": "doubao-seedream-5-0-pro-260628", // string；准确模型 ID。
  "canvas": { // object；底图画布尺寸。
    "width": 854, // integer；底图像素宽。
    "height": 480 // integer；底图像素高。
  },
  "coordinates": { // object；坐标解释说明，值为字符串。
    "absolute": "output-base pixels: [left, top, right, bottom]", // string；像素框 [left,top,right,bottom] 的坐标系说明。
    "normalized": "output-base coordinates divided by 1000" // string；归一化框的坐标系说明。
  },
  "layers": [ // object[]；按 z_index 排序的底图与图层清单。
    {
      "file": "01-layer.png", // string；对应媒体相对文件名，可与交付目录一起移动。
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000", // string；对应媒体文件内容哈希。
      "z_index": 1, // integer?；供应商输出层级，0 为底图，其他值为图层。
      "size": "1024x1024", // string?；供应商返回的图层 WIDTHxHEIGHT。
      "output_format": "png", // string?；图层格式，目前 PNG。
      "bounding_box": { // object?；前景图层在底图上的位置，底图可不提供。
        "absolute": [0, 0, 100, 100], // integer[]；以底图像素计的 [left,top,right,bottom]。
        "normalized": [0, 0, 100, 100] // integer[]；0～1000 范围内的 [left,top,right,bottom]。
      },
      "name": "狐狸", // string?；供应商提供的图层名称，底图可省略。
      "description": "示例文本" // string?；供应商提供的图层内容说明，底图可省略。
    }
  ]
}
```

失败输出

已捕获异常的 stderr JSON 格式见 __init__.py；命令行参数错误使用 argparse usage 文本。
"""

from core.delivery_files import publish_outputs
import os
import shutil
from pathlib import Path
from core.validation import require
from core.submission_store import read, write, lock, submission_path, now
from core.file_hash import sha256_file
from providers import capability_for_record


def _download(submission):
    path = submission_path(submission)
    with lock(path.parent):
        record = read(path)
        return capability_for_record(record).deliver(record, path)


def deliver(submission, destination=None):
    """交付验证通过的媒体及可选图层元数据，不交付过程文件。"""
    from commands.status import status, status_result

    record_path = submission_path(submission)
    destination = Path(destination or Path.cwd()).resolve(strict=True)
    require(destination.is_dir(), "Delivery destination must be an existing directory")
    require(
        destination != record_path.parent and record_path.parent not in destination.parents,
        "Deliver to the user project directory, not the temporary task directory",
    )
    with lock(record_path.parent):
        record = read(record_path)
        record["execution"].setdefault("delivery_complete", False)
        write(record_path, record)
        cached = record["execution"].get("download_complete") is True
        if cached:
            items = list(record.get("result", {}).get("files", []))
            if record.get("result", {}).get("metadata"):
                items.append(record["result"]["metadata"])
            cached = bool(items) and all(Path(f["path"]).is_file() and sha256_file(f["path"]) == f["sha256"] for f in items)
        if not cached:
            record["execution"]["delivery_complete"] = False
            write(record_path, record)
    if cached:
        return publish_outputs(record_path, destination)
    checked = status_result(status(record_path))
    require(checked["success"], checked["error"] or "Generation not successful; cannot deliver")
    _download(record_path)
    return publish_outputs(record_path, destination)


def run(args):
    return deliver(args.submission)
