r"""命令行调用

    python3 "$SKILL/scripts/main.py" cost --workdir /absolute/task-dir < /absolute/cost-input.json

    # --workdir：必填，init 创建的任务目录，不是输入 JSON 文件路径。
    # <：读取 cost-input.json 文件内容，送入 stdin。

输入文件格式

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

输入文件 /absolute/cost-input.json
编码 UTF-8，根节点为 JSON 对象；< 将文件内容写入 stdin，--workdir 是已有目录而不是该输入文件。

```jsonc
{
  "provider": "volcengine", // Provider；必填；本次估价供应商。
  "model": "doubao-seedance-2-5-260628", // string；必填；本供应商模型别名或准确 ID。
  "operation": "image-to-video", // Operation；必填；已实现能力标识。
  "resolution": "480p", // string?；视频必填，模型支持的输出分辨率。
  "ratio": "adaptive", // string?；视频必填，固定比例或 adaptive。
  "duration": 5, // integer?；视频必填，输出秒数或模型允许的 -1。
  "assets": [ // CostAsset[]?；有素材能力必须提供；纯文本能力省略或 []。
    {
      "id": "reference-1", // string?；可选唯一标识，若提供须与 init/submit 使用同一 id。
      "kind": "image", // "image" | "video" | "audio"；必填；素材类型。
      "source": "https://example.com/reference.png" // string；必填；实际可读的本地绝对路径或 HTTPS URL。
    }
  ]
}
```


按能力选择的其他入参（仅填写适用字段，不与上述示例全部合并）：
```jsonc
{
  "size": "1K", // string；图片能力必填；1K/1.5K/2K 或 WIDTHxHEIGHT，拆层可 auto；视频省略。
  "mode": "reference", // string；reference-to-video 必填 reference/edit；extend-video 必填 before/after；其他能力省略。
  "estimate_context": { // EstimateContext?；补充计费依据；逐字段见 commands/__init__.py。
    "output_dimensions": [854, 480], // [integer, integer]?；有依据的输出像素 [宽, 高]，须与所选规格相容。
    "minimum_billable_tokens": 86400, // number | Pair?；官方门槛；自动时长需要覆盖全范围的一对数值。
    "minimum_tokens_source": "https://docs.volcengine.com/docs/ark/model-pricing", // string?；手动门槛对应官方 HTTPS 文档/计算器；与门槛一起填写。
    "minimum_tokens_spec": { // object?；门槛适用规格；提供时必须与本次估价一致。
      "model": "seedance-2.5", // string；技能模型别名。
      "resolution": "480p", // string；本次输出分辨率。
      "ratio": "16:9", // string；本次比例参数，包括 adaptive。
      "duration": 5 // integer；本次时长参数，包括 -1。
    },
    "target_asset_index": 0, // integer?；编辑/延长的目标在完整 assets 数组中的下标，从 0 开始。
    "preferred_duration": 10 // number?；自动时长中期望的秒数；仅标记费用情景，不改 API 参数。
  }
}
```
这些是同一输入 JSON 对象的条件字段；对应能力支持范围见供应商指南。


标准输出格式

```jsonc
{
  "cost_file": "/tmp/richmedia-example/volcengine-priceing.json", // string；<provider>-priceing.json 的绝对路径，保留当前实际拼写。
  "input": {}, // CostInput；原始输入文件对象的完整副本，与上面的入参相同，不重复展开。
  "calculation": { // Calculation；可还原报价的单价、素材测量、公式及上下文，定义见下。
    "schema_version": 3, // 3；已保存报价结构版本。
    "created_at": "2026-10-26T00:00:00+00:00", // string；UTC ISO 8601 报价创建时间；提交时有效期 24 小时。
    "provider": "volcengine", // Provider；单价所属供应商。
    "model": "seedance-2.5", // string；已解析为技能模型别名。
    "operation": "text-to-video", // Operation；本次计费能力。
    "mode": "reference", // string?；参考视频/延长的具体模式。
    "input_images": 1, // integer；输入图片数量；纯文本为 0。
    "input_video_seconds": [2.0], // number[]；逐个输入视频的实测秒数，无视频为 []。
    "input_audio_seconds": [2.0], // number[]；逐个输入音频的实测秒数，无音频为 []。
    "assets": [ // MeasuredAsset[]；每项含 id?/kind/source（同 CostAsset），以及 Measurement 的扁平字段。
      {
        "id": "reference-1", // string?；可选唯一标识，若提供须与 init/submit 使用同一 id。
        "kind": "image", // "image" | "video" | "audio"；必填；素材类型。
        "source": "https://example.com/reference.png", // string；必填；实际可读的本地绝对路径或 HTTPS URL。
        "width": 854, // integer?；编码像素宽；图片/视频。
        "height": 480, // integer?；编码像素高；图片/视频。
        "display_width": 854, // number?；经旋转与像素宽高比修正的显示宽。
        "display_height": 480, // number?；经旋转与像素宽高比修正的显示高。
        "duration": 5, // number?；视频/音频的实测秒数。
        "duration_basis": "stream_duration", // string?；stream_duration/container_duration/duration_ts_time_base/packet_timestamps。
        "frame_rate": 24, // number?；输入视频实际帧率，不是估价公式的输出帧率。
        "format_name": "mov,mp4", // string?；ffprobe 容器名称，可能是逗号分隔的多个别名。
        "codec_name": "h264", // string?；输入视频/音频编解码器名称。
        "bytes": 1024, // integer?；可取得的文件字节数。
        "mime": "image/png", // string | null?；已识别 MIME；未知可为 null。
        "has_alpha": false, // boolean?；图片像素格式是否包含透明通道。
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000", // string?；本地文件内容哈希；远程素材通常没有。
        "cost_probe_version": 2 // integer?；新版计费素材测量标记，目前为 2。
      }
    ],
    "currency": "CNY", // "CNY" | "USD"；本供应商刊例价币种。
    "pricing": { // object；本次实际采用的价格快照子集。
      "source": "https://docs.volcengine.com/docs/ark/model-pricing", // string；官方价格页 URL。
      "verified_on": "2026-10-26", // string；YYYY-MM-DD 核实日期。
      "basis": "示例计费依据", // string；刊例价范围、是否排除账户优惠等说明。
      "verification_source": "https://example.com/official-pricing.md", // string?；本次完整解析核价使用的官方 Markdown URL。
      "rates": { // ImageRates | VideoRates；本模型单价；两种结构见下。
        "input_after_first": 1.0, // number；首张之后每张输入图费用。
        "single": [0.3, 0.6], // Pair；单图生成的低/高像素档单价。
        "layer": [0.15, 0.3], // Pair；拆层的低/高像素档逐张单价。
        "threshold_pixels": 2610000 // integer；区分低/高档的像素数量；超过门槛进入高档。
      }
    },
    "estimate_context": { // EstimateContext | null；本次补充依据；未提供时 null。
      "output_dimensions": [854, 480], // [integer, integer]?；有依据的输出像素 [宽, 高]，须与所选规格相容。
      "minimum_billable_tokens": 86400, // number | Pair?；官方门槛；自动时长需要覆盖全范围的一对数值。
      "minimum_tokens_source": "https://docs.volcengine.com/docs/ark/model-pricing", // string?；手动门槛对应官方 HTTPS 文档/计算器；与门槛一起填写。
      "minimum_tokens_spec": { // object?；门槛适用规格；提供时必须与本次估价一致。
        "model": "seedance-2.5", // string；技能模型别名。
        "resolution": "480p", // string；本次输出分辨率。
        "ratio": "16:9", // string；本次比例参数，包括 adaptive。
        "duration": 5 // integer；本次时长参数，包括 -1。
      },
      "target_asset_index": 0, // integer?；编辑/延长的目标在完整 assets 数组中的下标，从 0 开始。
      "preferred_duration": 10 // number?；自动时长中期望的秒数；仅标记费用情景，不改 API 参数。
    },
    "fx": { // Fx | null；实际采用的有效汇率；没有有效值时 null。
      "usd_cny": 7.0, // number；正数；1 美元对应的人民币金额。
      "expires_at": "2026-10-27T00:00:00+00:00" // string；带时区 ISO 8601 有效期；提交时也会校验是否过期。
    },
    "notes": ["示例值"], // string[]；公式依据、限制和估价说明。
    "pricing_freshness": { // Freshness；本次价格时效，逐字段见 commands/__init__.py。
      "status": "fresh", // "fresh" | "stale" | "invalid"；7 天以内、过期或日期无效。
      "age_days": 0, // integer | null；距核实日期的 UTC 天数；无法解析时 null。
      "verified_on": "2026-10-26" // string | null；YYYY-MM-DD 核实日期；缺失时 null。
    },
    "pricing_refresh": "示例文本", // string?；自动联网核价失败时的说明；不刷新旧 verified_on。
    "size": "1K", // string?；图片输出尺寸。
    "extra_input_images": 1, // integer?；图片首张之后需计价的输入数量。
    "extra_input_unit_price": 1.0, // number?；每张额外输入图单价，单位为 currency/张。
    "extra_input_cost": 1.0, // number?；额外输入图片合计费用。
    "output_count_range": [1, 17], // Pair?；图片输出张数范围；拆层计数包含底图。
    "output_unit_price_range": [0.15, 0.3], // Pair?；图片逐张低/高像素档单价范围。
    "output_dimensions": [854, 480], // [integer,integer]?；图片显式像素输出尺寸 [宽,高]。
    "output_pixels": 1048576, // integer?；图片显式输出宽乘高。
    "pixel_tier": "low", // "low" | "high"?；图片输出价对应像素档位。
    "resolution": "480p", // string?；视频输出分辨率。
    "ratio": "16:9", // string?；视频输出比例参数。
    "duration": 5, // integer?；视频 API 输出时长参数，可能为 -1。
    "target_asset_index": 0, // integer?；估价选定的完整素材数组下标，从 0 开始。
    "assumed_output_dimensions": [854, 480], // [integer,integer]?；视频首个估算尺寸 [宽,高]，不保证实际输出像素。
    "output_dimension_candidates": [[854, 480]], // [integer,integer][]?；费用范围计算采用的所有输出像素候选。
    "output_dimensions_basis": "official_ratio_table", // string?；official_ratio_table/source_ratio_and_official_table/ provided_estimate/official_adaptive_candidates/source_ratio_area_estimate。
    "assumed_output_duration": [4, 30], // Pair?；视频估算输出秒数范围；固定时两值相等。
    "total_input_video_seconds": 1.0, // number?；输入视频实测总秒数，包含全部参与输入的视频。
    "frames_per_second": 24, // number?；视频费用公式采用的输出帧率，目前为 24。
    "formula_tokens": [48038, 48038], // Pair?；不考虑最低门槛时，时长/像素公式算得的 Token 范围。
    "tokens": [86400, 86400], // [number|null,number|null]?；考虑最低门槛后的计费 Token 估算范围。
    "minimum_billable_tokens": 86400, // number | Pair?；实际采用的最低 Token 或其估算范围。
    "minimum_tokens_source": "https://docs.volcengine.com/docs/ark/model-pricing", // string?；实际采用门槛或公开价格示例的来源 URL。
    "minimum_tokens_evidence": {}, // object?；门槛来源与外推审计记录，见 MinimumEvidence。
    "unit_price_per_million_tokens": 70, // number?；视频刊例价，单位 currency/百万 Token。
    "formula": "billable_tokens * unit_price_per_million_tokens / 1000000", // string；本次图片或视频费用主公式。
    "steps": [ // Step[]；按计算顺序记录中间结果。
      {
        "name": "formula_tokens", // string；计算步骤标识，例如 formula_tokens/total_cost。
        "formula": "billable_tokens * unit_price_per_million_tokens / 1000000", // string；此步骤的公式或计算表达。
        "value": 1.0 // number | Amount | Conversion；中间数值、范围或最终汇率换算结果。
      }
    ]
  },
  "result": { // CostResult；面向确认单的精简报价，定义见下。
    "status": "estimate", // "estimate" | "lower_bound" | "unknown"；当前含假设估算；兼容历史下界/未知。
    "currency": "CNY", // "CNY" | "USD"；原币币种。
    "amount": { // Amount；原币费用范围，min/max 逐字段见 commands/__init__.py。
      "min": 1.0, // number | null；估算范围起点；null 表示未知，不能按 0 理解。
      "max": 2.0 // number | null；估算范围终点；不是账单封顶；null 表示未知。
    },
    "uncertainties": [ // Uncertainty[]；尚未核实、外推或模型自动决定的因素。
      {
        "field": "output_duration", // string；不确定项标识，如 output_duration 或 minimum_billable_tokens。
        "reason": "示例说明：输出时长由模型自动决定" // string；对该项不确定性和估算依据的说明。
      }
    ],
    "range_is_guaranteed": false, // false；明确该区间不是供应商保证的收费上下界。
    "estimate_quality": "extrapolated", // "extrapolated" | "documented_estimate"?；视频采用未校准外推或文档依据估算；均不表示账单保证。
    "scenarios": [ // Scenario[]?；自动时长或拆层数量对应的分情形费用。
      {
        "amount": [1.0, 2.0], // Pair；该情景下的原币费用 [起点,终点]，不是 Amount 对象。
        "basis": "示例计费依据", // string；费用情景依据或拆层逐张计价说明。
        "output_seconds": 10, // number?；视频时长情景的输出秒数。
        "preferred": false, // boolean?；该视频情景是否匹配 preferred_duration。
        "output_count_including_base": 4, // integer?；拆层情景的总输出数量，含底图。
        "conversion": { // object?；存在有效汇率时的情景换算。
          "currency": "CNY", // "CNY" | "USD"；情景换算目标币种。
          "amount": [1.0, 2.0] // Pair；换算后的 [起点,终点]；不是 Amount 对象。
        }
      }
    ],
    "conversion": { // Conversion?；仅存在有效汇率时输出的另一币种报价。
      "currency": "CNY", // "CNY" | "USD"；换算目标币种。
      "amount": { // Amount；换算后的金额范围对象。
        "min": 1.0, // number | null；估算范围起点；null 表示未知，不能按 0 理解。
        "max": 2.0 // number | null；估算范围终点；不是账单封顶；null 表示未知。
      },
      "usd_cny": 7.0, // number；本次使用的 1 美元兑人民币汇率。
      "expires_at": "2026-10-27T00:00:00+00:00" // string；该汇率的带时区 ISO 8601 有效期。
    }
  }
}
```

文件输出格式

<workdir>/<provider>-priceing.json：UTF-8 JSON，内容就是上述 stdout 的 input、calculation、result 三个字段；不含 cost_file，不重复展开。
价格过期时可在任务目录写入 <provider>-pricing-cache.json；格式与 __init__.py 的价格快照相同。

VideoRates 分支（替换 pricing.rates；数组顺序为无视频输入、有视频输入）

```jsonc
{
  "480p": [1.0, 2.0] // Pair；当前输出分辨率对应 [无视频输入单价, 有视频输入单价]，单位 currency/百万 Token。
}
```

失败输出

已捕获异常的 stderr JSON 格式见 __init__.py；命令行参数错误使用 argparse usage 文本。
"""

import json
import sys
from pathlib import Path
from core.exchange_rate import fx_from_env
from providers import calculate_asset_inputs
from core.validation import require
from core.operations import require_supported_operation
from core.submission_store import lock, prior_submission, write


def run(args):
    workdir = Path(args.workdir).resolve(strict=True)
    require(workdir.is_dir(), "--workdir must be an existing task directory")
    require(not sys.stdin.isatty(), "Supply cost inputs as a JSON object on stdin")

    def reject_constant(value):
        raise ValueError("Invalid JSON numeric constant: " + value)

    inputs = json.loads(sys.stdin.read(), parse_constant=reject_constant)
    require(isinstance(inputs, dict), "Cost input must be a JSON object")
    require_supported_operation(inputs)
    if inputs["operation"] == "text-to-image":
        require(not inputs.get("assets"), "Text-to-image must not include input assets")
    from core.pricing import pricing_session
    with pricing_session(workdir):
        quote = calculate_asset_inputs(inputs, fx=fx_from_env())
    target = workdir / (inputs["provider"] + "-priceing.json")
    with lock(workdir):
        prior_submission(workdir)
        write(target, quote)
    return {"cost_file": str(target), **quote}
