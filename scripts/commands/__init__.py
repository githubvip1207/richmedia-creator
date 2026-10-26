r"""公共文件与嵌套 JSON 格式（本文件不对应命令行子命令）。

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

运行上下文
cwd 是项目目录；.env 从 cwd 读取，deliver 的默认交付目标也是 cwd。
.env 使用 UTF-8 KEY=VALUE 文本，不是 JSON；不要把示例占位符当真实密钥：

```dotenv
VOLCENGINE_API_KEY=<在本地填写实际密钥>
BYTEPLUS_API_KEY=<在本地填写实际密钥>
USD_CNY=7.0
USD_CNY_EXPIRES_AT=2026-10-27T00:00:00+00:00
```
VOLCENGINE_API_KEY/ BYTEPLUS_API_KEY 是各供应商自己的密钥，检查输出不回显其值。
USD_CNY 表示 1 美元兑人民币；USD_CNY_EXPIRES_AT 是带时区 ISO 8601 到期时间。

JSON 字段中的 provider 为 volcengine 或 byteplus；operation 为 text-to-image、
image-to-image、decompose-layers、text-to-video、image-to-video、reference-to-video、
extend-video 七种能力之一。例子中的 volcengine、seedance-2.5 和 480p 也可作为对应动态键的示例。

Amount（JSON 字段模板；按能力选用）

```jsonc
{
  "min": 1.0, // number | null；估算范围起点；null 表示未知，不能按 0 理解。
  "max": 2.0 // number | null；估算范围终点；不是账单封顶；null 表示未知。
}
```


Fx（JSON 字段模板；按能力选用）

```jsonc
{
  "usd_cny": 7.0, // number；正数；1 美元对应的人民币金额。
  "expires_at": "2026-10-27T00:00:00+00:00" // string；带时区 ISO 8601 有效期；提交时也会校验是否过期。
}
```


Freshness（JSON 字段模板；按能力选用）

```jsonc
{
  "status": "fresh", // "fresh" | "stale" | "invalid"；7 天以内、过期或日期无效。
  "age_days": 0, // integer | null；距核实日期的 UTC 天数；无法解析时 null。
  "verified_on": "2026-10-26" // string | null；YYYY-MM-DD 核实日期；缺失时 null。
}
```


Asset（JSON 字段模板；按能力选用）

```jsonc
{
  "id": "reference-1", // string?；任务内唯一标识；init/submit 必需，cost 可选。
  "kind": "image", // "image" | "video" | "audio"；素材媒体类型。
  "source": "https://example.com/reference.png", // string；实际 HTTPS URL 或本地绝对路径；视频提交只接受 HTTPS。
  "purpose": "参考主体外观" // string?；素材用途；init/submit 必需；估价入口禁止传此字段。
}
```


AssetRef（JSON 字段模板；按能力选用）

```jsonc
{
  "id": "reference-1" // string；引用顶层同名 id；顺序与模型输入顺序一致。
}
```


Measurement（JSON 字段模板；按能力选用）

```jsonc
{
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
```


EstimateContext（JSON 字段模板；按能力选用）

```jsonc
{
  "output_dimensions": [854, 480], // [integer, integer]?；有依据的输出像素 [宽, 高]，须与所选规格相容。
  "preferred_duration": 10 // number?；自动时长中期望的秒数；仅标记费用情景，不改 API 参数。
}
```


Parameters（JSON 字段模板；按能力选用）

```jsonc
{
  "size": "1K", // string?；图片尺寸档位或 WIDTHxHEIGHT；拆层还可用 auto。
  "ratio": "16:9", // string?；构图比例；视频还可用 adaptive，图片不直接发送 ratio 字段。
  "resolution": "480p", // string?；视频分辨率，如 480p/720p/1080p/4k，须模型支持。
  "duration": 5, // integer?；视频输出秒数；-1 表示模型自动决定。
  "generate_audio": false, // boolean?；是否生成视频声音。
  "watermark": false, // boolean?；是否添加水印；具体能力可能要求固定值。
  "return_last_frame": false, // boolean?；是否返回视频对应尾帧图。
  "output_format": "png", // string?；图片 png/jpeg，视频 mp4/mov，受模型限制。
  "response_format": "url", // string?；图片响应形式，当前原生生成要求 url。
  "background": "opaque", // string?；图片背景参数，如 opaque；按对应能力规则。
  "layer_decomposition": false, // boolean?；是否拆分图层；须与 operation 一致。
  "service_tier": "default", // string?；视频服务档位；当前为 default，2.0-mini 必须省略。
  "tools": [ // Tool[]?；Volcengine 2.5 或纯文本视频可启用；2.0 系列含素材时必须 []；BytePlus 省略。
    {
      "type": "web_search" // "web_search"；联网搜索工具类型；空 tools 数组表示关闭。
    }
  ],
  "omni_reference_task_type": "reference" // string?；2.5 原生参考任务类型 reference/edit/extend，按能力编排。
}
```


NativePayload（JSON 字段模板；按能力选用）

```jsonc
{
  "model": "doubao-seedance-2-5-260628", // string；所选供应商的准确模型 ID，不是技能别名。
  "prompt": "生成一段狐狸在草地奔跑的视频", // string?；图片必需；必须与 request.json.optimized_prompt 一致。
  "content": [ // TextContent[]?；视频必需；输入时只提供一个文本项，素材由外层 assets 编排。
    {
      "type": "text", // "text"；此输入项是提示词文本。
      "text": "生成一段狐狸在草地奔跑的视频" // string；完整视频提示词；不把 API 参数写成文本旗标。
    }
  ],
  "image": [], // []?；图生图/拆层只能省略或传空数组；输入图片全部放在外层 assets，由编译器填入。
  "size": "1K", // string?；图片输出尺寸；规则见 Parameters.size。
  "output_format": "png", // string?；输出文件格式；规则见 Parameters.output_format。
  "response_format": "url", // string?；图片响应形式；规则见 Parameters.response_format。
  "watermark": false, // boolean?；水印设置；按能力固定要求。
  "background": "opaque", // string?；图片背景设置；按能力固定要求。
  "layer_decomposition": false, // boolean?；图片图层拆分开关。
  "resolution": "480p", // string?；视频输出分辨率。
  "ratio": "16:9", // string?；视频输出比例；部分模式必须 adaptive。
  "duration": 5, // integer?；视频输出时长；自动模式为 -1。
  "generate_audio": false, // boolean?；视频是否生成声音。
  "return_last_frame": false, // boolean?；视频是否返回尾帧图。
  "service_tier": "default", // string?；视频服务档位；部分模型不接受该字段。
  "tools": [ // Tool[]?；视频允许的搜索工具；空数组关闭。
    {
      "type": "web_search" // "web_search"；联网搜索工具类型；空 tools 数组表示关闭。
    }
  ],
  "omni_reference_task_type": "reference" // string?；2.5 原生任务类型，与外层 operation/mode 一致。
}
```


价格快照文件 models/<provider>-pricing.json（UTF-8 标准 JSON 对象）

```jsonc
{
  "verified_on": "2026-10-26", // string；YYYY-MM-DD，价格最近核实日期。
  "source": "https://example.com/reference.png", // string；供应商官方定价页 URL。
  "currency": "CNY", // "CNY" | "USD"；volcengine 为 CNY，byteplus 为 USD。
  "provider": "volcengine", // Provider?；可选显式供应商标识；部分既有快照未保存。
  "basis": "示例计费依据", // string；公开刊例价格适用范围及未包含费用说明。
  "verification_source": "https://example.com/official-pricing.md", // string?；成功核价使用的官方 Markdown URL。
  "minimum_token_estimation": {}, // object；官方最低用量规则、公开价格示例及核实日期；逐字段格式见对应供应商文档的“预估成本”。
  "video": { // object；按视频模型别名索引费率。
    "seedance-2.5": { // VideoRates；视频模型费率，各分辨率数组按无/有视频输入排序。
      "480p": [1.0, 2.0] // Pair；当前输出分辨率对应 [无视频输入单价, 有视频输入单价]，单位 currency/百万 Token。
    }
  },
  "image": { // object；按图片模型别名索引费率。
    "seedream-5.0-pro": { // ImageRates；图片模型逐张费率及像素门槛。
      "input_after_first": 1.0, // number；首张之后每张输入图费用。
      "single": [0.3, 0.6], // Pair；单图生成的低/高像素档单价。
      "layer": [0.15, 0.3], // Pair；拆层的低/高像素档逐张单价。
      "threshold_pixels": 2610000 // integer；区分低/高档的像素数量；超过门槛进入高档。
    }
  }
}
```


提交记录文件 submit-NNN.json

格式见 submit.py 的“文件输出格式”；status/deliver 读取同一个文件，不重复展开。

编译模板内媒体 URL 占位对象（仅内部 payload_template，非手写原生 API 入参）

```jsonc
{
  "asset_index": 1 // integer；compiled.assets 内的素材下标，从 0 开始；POST 前解析真实来源。
}
```


失败响应

```jsonc
{
  "error": "示例文本" // string；除 status 外，已捕获运行异常写 stderr 的说明；退出码 1。
}
```

status 的错误输出见 status.py：stdout {"success": false, "error": "原因"}。
argparse 参数解析错误是 stderr usage 文本、退出码 2，不是 JSON。

OutputVerification（下载/交付文件的 verification；可解码不等于符合确认规格）
```jsonc
{
  "status": "mismatch", // "matched" | "mismatch" | "not_checked"；可观察的尺寸、时长、音轨是否符合确认参数；不代表内容质量通过。
  "differences": [ // object[]；全部检测到的规格差异，无差异为空数组。
    {
      "field": "duration", // string；差异字段 dimensions/resolution/duration/has_audio/size。
      "expected": 5, // number | string | boolean | integer[]；确认参数或对应官方像素尺寸。
      "actual": 2 // number | string | boolean | integer[]；文件实测值。
    }
  ]
}
```
保留不符规格的供应商原件供用户检查；发现 mismatch 时必须说明具体差异，不得描述为规格验收通过，不自动付费重生成。


最低门槛来源（MinimumEvidence，以下为字段格式，按 method 选择适用字段）
```jsonc
{
  "method": "public_example_scaled", // string；configured_official_table/public_example_rounded/public_example_scaled。
  "specification": { // object?；使用配置中官方门槛行时记录适用规格。
    "model": "seedance-2.5", // string；模型别名。
    "resolution": "480p", // string；输出分辨率。
    "ratio": "16:9", // string；输出比例参数。
    "duration": 5 // number；输出秒数参数，自动为 -1。
  },
  "source": "https://docs.volcengine.com/docs/ark/model-pricing", // string；采用的官方门槛或公开价格示例来源。
  "verified_on": "2026-10-25", // string?；实际采用的门槛行或公开示例核实日期，YYYY-MM-DD。
  "anchor_duration": 5, // number?；公开示例输出秒数。
  "anchor_dimensions": [854, 480], // integer[]?；公开示例输出 [宽,高]。
  "anchor_amount": 3.63, // number?；示例最低价格，供应商原币。
  "anchor_rate": 42, // number?；示例当时的每百万 Token 原币单价。
  "formula": "(published_minimum_price ± rounding) / anchor_rate * 1000000 * output_seconds / 5 * output_area / anchor_area", // string?；从公开金额反推及跨规格外推公式。
  "table_source": "https://bytedance.larkoffice.com/wiki/H0fUwHPxtiHayOk6CVpcZzKqnHJ", // string?；应优先核对的官方最低 Token 表。
  "extrapolation_error": "uncalibrated", // "uncalibrated" | "not_applicable"；公开示例的跨规格外推误差尚未定量校准，同规格反推不涉及外推。
  "interval_covers": ["published_price_rounding"] // string[]；当前数值区间覆盖公开价格舍入；不包含未知外推误差。
}
```

"""
