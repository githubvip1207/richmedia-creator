r"""命令行调用

    python3 "$SKILL/scripts/main.py" submit --workdir /absolute/task-dir --request /absolute/task-spec.json --approval-text "用户真实确认原话"
    python3 "$SKILL/scripts/main.py" submit --workdir /absolute/task-dir --approval-text "用户真实确认原话" < /absolute/task-spec.json

    # --workdir：必填，已有任务目录，包含 request.json 和已保存报价。
    # --request：可选，输入任务规范的 JSON 文件；省略时读取 stdin。
    # --approval-text：必填，用户真实确认原话。
    # --accept-uncertain-cost：可选，默认关闭；仅用于用户已明确接受未知费用的情况。

输入文件格式

实际文件为 UTF-8 标准 JSON，根节点为对象；下方 JSONC 的 // 仅用于逐字段说明，写文件时删除注释。

输入文件 --request 指定的 task-spec.json
编码 UTF-8，根节点为 JSON 对象；省略 --request 时可用 < task-spec.json 将同样内容写入 stdin。

```jsonc
{
  "provider": "volcengine", // Provider；必填；明确选择已确认供应商。
  "operation": "image-to-video", // Operation；必填；当前需求的已实现能力。
  "original_prompt": "生成一段狐狸在草地奔跑的视频", // string；必填；与 request.json 保留的完整用户原话一致。
  "payload": { // object；必填；供应商原生正文，各字段与分支说明见 commands/__init__.py。
    "model": "doubao-seedance-2-5-260628", // string；所选供应商的准确模型 ID，不是技能别名。
    "content": [ // TextContent[]?；视频必需；输入时只提供一个文本项，素材由外层 assets 编排。
      {
        "type": "text", // "text"；此输入项是提示词文本。
        "text": "生成一段狐狸在草地奔跑的视频" // string；完整视频提示词；不把 API 参数写成文本旗标。
      }
    ],
    "output_format": "mp4", // string?；输出文件格式；规则见 Parameters.output_format。
    "watermark": false, // boolean?；水印设置；按能力固定要求。
    "resolution": "480p", // string?；视频输出分辨率。
    "ratio": "adaptive", // string?；视频输出比例；部分模式必须 adaptive。
    "duration": 5, // integer?；视频输出时长；自动模式为 -1。
    "generate_audio": false, // boolean?；视频是否生成声音。
    "return_last_frame": false, // boolean?；视频是否返回尾帧图。
    // "service_tier": "default", // string?；视频服务档位；Volcengine 省略；BytePlus 可省略，填写时仅支持 default。
    "tools": [] // Tool[]?；视频允许的搜索工具；空数组关闭。
  },
  "assets": [ // Asset[]?；有序实际素材，须带 id/kind/source/purpose；文生图必须省略此字段；文生视频可省略或传 []。
    {
      "id": "reference-1", // string?；任务内唯一标识；init/submit 必需，cost 可选。
      "kind": "image", // "image" | "video" | "audio"；素材媒体类型。
      "source": "https://example.com/reference.png", // string；实际 HTTPS URL 或本地绝对路径；视频提交只接受 HTTPS。
      "purpose": "参考主体外观" // string?；素材用途；init/submit 必需；估价入口禁止传此字段。
    }
  ],
  "target_asset_id": "main-video", // string?；仅编辑/延长可用，引用 assets 中目标视频 id；多视频时必填，不发送给供应商。
  "budget_cny": 100.0, // number?；正数；按人民币估算范围终点比较的预算，不是供应商扣款限额。
  "budget_usd": 20.0 // number?；正数；按美元估算范围终点比较的预算，不是供应商扣款限额。
}
```

--workdir 中另外读取两个文件：
- request.json：格式与 init.py 的输入文件相同，不重复展开。
- <provider>-priceing.json：格式与 cost.py 的文件输出相同，不重复展开。

标准输出格式

```jsonc
{
  "submission": "/tmp/richmedia-example/submit-001.json" // string；新建 submit-NNN.json 的绝对路径；不是供应商 task_id。
}
```

文件输出格式

<workdir>/payload.json：保存输入 task-spec.json，格式与本文件输入完全相同，不是最终带 Base64 的网络请求，不重复展开。

<workdir>/submit-NNN.json：输入 task-spec.json 的顶层字段原样保留，并增加 response、execution；后续 status/deliver 可增加 queries、result、delivery、delivery_history。

输入规范字段与上面的 task-spec.json 相同，不重复。以下 JSON 仅展示新增字段；
复用对象用 {} 标出位置，实际保存时包含被引用格式的完整内容。queries/result/
delivery/delivery_history 随生命周期出现，不是提交瞬间全部都有。

```jsonc
{
  "response": { // object | null；原始 POST 响应；请求未返回时 null。供应商可扩展字段，已知分支见此模板。
    "id": "video-task-example", // string?；视频任务 ID；同步图片响应可能省略。
    "status": "succeeded", // string?；视频 queried 状态，如 succeeded。
    "created": 1, // integer?；图片响应的创建时间，按供应商格式。
    "data": [ // object[]?；同步图片输出项。
      {
        "url": "https://example.com/output.png", // string?；图片可下载 HTTPS URL。
        "size": "1024x1024", // string?；返回图片的 WIDTHxHEIGHT。
        "output_format": "png", // string?；输出格式，如 png。
        "z_index": 1, // integer?；拆层时的层级，底图为 0。
        "name": "狐狸", // string?；图层名称。
        "description": "示例文本", // string?；图层内容说明。
        "bounding_box": { // object?；图层位置。
          "absolute": [0, 0, 100, 100], // integer[]；底图像素坐标 [left,top,right,bottom]。
          "normalized": [0, 0, 100, 100] // integer[]；归一化 0～1000 坐标。
        },
        "error": { // object?；某个图片输出失败的原因。
          "code": "示例文本", // string?；供应商错误码。
          "message": "示例文本", // string?；经过脱敏的错误说明。
          "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
        }
      }
    ],
    "content": { // object?；视频任务成功后产物链接。
      "video_url": "https://example.com/output.mp4", // string?；视频下载 HTTPS URL。
      "last_frame_url": "https://example.com/last-frame.jpeg" // string?；可选尾帧图下载 URL。
    },
    "usage": { // object?；供应商返回的实际用量。
      "completion_tokens": 1, // integer?；生成消耗 Token，可用于刊例费用核对。
      "total_tokens": 1, // integer?；供应商返回的合计 Token。
      "tool_usage": { // object?；供应商返回的工具用量。
        "web_search": 1 // integer?；实际联网搜索调用次数。
      }
    },
    "error": { // object?；供应商整体请求错误。
      "code": "示例文本", // string?；供应商错误码。
      "message": "示例文本", // string?；经过脱敏的错误说明。
      "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
    }
  },
  "execution": { // object；技能维护的执行状态；不是供应商原始 response。
    "state": "succeeded", // string；submitting/queued/running/succeeded/partial_failed/failed/expired/cancelled/rejected/submission_unknown 等状态。
    "created_at": "2026-10-26T00:00:00+00:00", // string；提交记录创建时间，UTC ISO 8601。
    "updated_at": "2026-10-26T00:00:01+00:00", // string?；状态最近更新时间，UTC ISO 8601。
    "compiled": { // object；验证后的编译方案，status/deliver 根据此对象选择供应商能力模块。
      "provider": "volcengine", // Provider；编译方案所属供应商。
      "model": "seedance-2.5", // string；技能模型别名。
      "kind": "video", // "video"；编译方案媒体类型；图片任务为 image。
      "operation": "text-to-video", // Operation；具体能力标识。
      "mode": "reference", // string?；仅参考视频/延长模式出现。
      "prompt": "生成一段狐狸在草地奔跑的视频", // string；编译后使用的完整提示词。
      "assets": [ // object[]；已编排的有序素材；文生视频为空数组。
        {
          "id": "reference-1", // string?；任务内唯一标识；init/submit 必需，cost 可选。
          "kind": "image", // "image" | "video" | "audio"；素材媒体类型。
          "source": "https://example.com/reference.png", // string；实际 HTTPS URL 或本地绝对路径；视频提交只接受 HTTPS。
          "purpose": "参考主体外观", // string?；素材用途；init/submit 必需；估价入口禁止传此字段。
          "transport": "示例文本", // string?；来源传输方式 https 或 local-base64。
          "role": "示例文本", // string?；素材角色，如 first_frame/reference_video。
          "sha256": "0000000000000000000000000000000000000000000000000000000000000000", // string?；本地素材哈希。
          "metadata": { // Measurement；该素材实测信息对象。
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
        }
      ],
      "parameters": { // Parameters；已验证且会影响编译的参数；仅保留对应能力字段。
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
        // "service_tier": "default", // string?；视频服务档位；Volcengine 省略；BytePlus 可省略，填写时仅支持 default。
        "tools": [ // Tool[]?；视频联网搜索设置；供应商/能力可能限制或省略。
          {
            "type": "web_search" // "web_search"；联网搜索工具类型；空 tools 数组表示关闭。
          }
        ],
        "omni_reference_task_type": "reference" // string?；2.5 原生参考任务类型 reference/edit/extend，按能力编排。
      },
      "payload_template": { // NativePayload；供应商原生请求模板；媒体 URL 位置还可能是 asset_index 占位对象。
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
        // "service_tier": "default", // string?；视频服务档位；Volcengine 省略；BytePlus 可省略，填写时仅支持 default。
        "tools": [ // Tool[]?；视频允许的搜索工具；空数组关闭。
          {
            "type": "web_search" // "web_search"；联网搜索工具类型；空 tools 数组表示关闭。
          }
        ],
        "omni_reference_task_type": "reference" // string?；2.5 原生任务类型，与外层 operation/mode 一致。
      },
      "warnings": ["示例值"], // string[]；编译过程提示。
      "quantity": 1, // integer；当前请求生成目标数量，目前为 1。
      "optimizer": null, // null；兼容保留字段；优化在提交前由工作流完成。
      "original_prompt": "生成一段狐狸在草地奔跑的视频" // string；原始用户需求，与外层记录一致。
    },
    "approval": { // object；本次实际授权记录。
      "text": "生成一段狐狸在草地奔跑的视频", // string；用户真实确认原话；文档示例不能作为真实授权。
      "recorded_at": "示例文本", // string；授权记录时间，UTC ISO 8601。
      "accept_uncertain_cost": false // boolean；是否明确接受未知费用。
    },
    "provider": "volcengine", // Provider；提交供应商。
    "model": "seedance-2.5", // string；技能模型别名。
    "task_id": "video-task-example", // string | null；供应商视频任务 ID；同步图片或尚未返回时可为 null。
    "cost_record": {}, // 完整内容同 cost.py 的报价文件，此处仅省略展开，不表示允许空对象。
    "submission": "/tmp/richmedia-example/submit-001.json", // string；当前 submit-NNN.json 的绝对路径。
    "usage": { // object | null?；最近状态响应中的实际用量。
      "completion_tokens": 1, // integer?；生成消耗 Token，可用于刊例费用核对。
      "total_tokens": 1, // integer?；供应商返回的合计 Token。
      "tool_usage": { // object?；供应商返回的工具用量。
        "web_search": 1 // integer?；实际联网搜索调用次数。
      }
    },
    "error": "示例文本", // string | object | null?；最近错误，可能是字符串或供应商错误对象；成功后可能重置 null。
    "errors": [ // object[]?；图片任务逐项错误。
      {
        "code": "示例文本", // string?；供应商错误码。
        "message": "示例文本", // string?；经过脱敏的错误说明。
        "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
      }
    ],
    "download_complete": false, // boolean?；缓存下载及校验是否完成。
    "delivery_complete": false // boolean?；是否已交付到用户项目目录。
  },
  "queries": [ // object[]?；状态查询后追加的记录，按时间顺序。
    {
      "requested_at": "2026-10-26T00:00:30+00:00", // string；发起 GET 的 UTC ISO 8601 时间。
      "request": { // object；已发出的状态查询请求。
        "method": "GET", // "GET"；只读查询方法。
        "path": "/contents/generations/tasks/video-task-example" // string；供应商状态 API 相对路径。
      },
      "response": { // object | null；本次 GET 原始响应，发送前为 null。
        "id": "video-task-example", // string?；视频任务 ID；同步图片响应可能省略。
        "status": "succeeded", // string?；视频 queried 状态，如 succeeded。
        "created": 1, // integer?；图片响应的创建时间，按供应商格式。
        "data": [ // object[]?；同步图片输出项。
          {
            "url": "https://example.com/output.png", // string?；图片可下载 HTTPS URL。
            "size": "1024x1024", // string?；返回图片的 WIDTHxHEIGHT。
            "output_format": "png", // string?；输出格式，如 png。
            "z_index": 1, // integer?；拆层时的层级，底图为 0。
            "name": "狐狸", // string?；图层名称。
            "description": "示例文本", // string?；图层内容说明。
            "bounding_box": { // object?；图层位置。
              "absolute": [0, 0, 100, 100], // integer[]；底图像素坐标 [left,top,right,bottom]。
              "normalized": [0, 0, 100, 100] // integer[]；归一化 0～1000 坐标。
            },
            "error": { // object?；某个图片输出失败的原因。
              "code": "示例文本", // string?；供应商错误码。
              "message": "示例文本", // string?；经过脱敏的错误说明。
              "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
            }
          }
        ],
        "content": { // object?；视频任务成功后产物链接。
          "video_url": "https://example.com/output.mp4", // string?；视频下载 HTTPS URL。
          "last_frame_url": "https://example.com/last-frame.jpeg" // string?；可选尾帧图下载 URL。
        },
        "usage": { // object?；供应商返回的实际用量。
          "completion_tokens": 1, // integer?；生成消耗 Token，可用于刊例费用核对。
          "total_tokens": 1, // integer?；供应商返回的合计 Token。
          "tool_usage": { // object?；供应商返回的工具用量。
            "web_search": 1 // integer?；实际联网搜索调用次数。
          }
        },
        "error": { // object?；供应商整体请求错误。
          "code": "示例文本", // string?；供应商错误码。
          "message": "示例文本", // string?；经过脱敏的错误说明。
          "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
        }
      },
      "error": "示例文本" // string?；查询失败时的脱敏原因。
    }
  ],
  "result": { // object?；完成下载后保存的缓存结果。
    "files": [ // object[]；下载缓存输出清单。
      {
        "path": "/absolute/output.png", // string；缓存文件绝对路径。
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000", // string；缓存文件内容 SHA-256。
        "kind": "image", // "image" | "video"；媒体类型。
        "verification": {}, // OutputVerification?；完整字段见 commands/__init__.py；不是空对象。
        "metadata": { // VideoMetadata?；视频实测规格。
          "width": 854, // integer；输出视频编码像素宽。
          "height": 480, // integer；输出视频编码像素高。
          "duration": 5, // number；输出视频实测秒数，可能不是整数。
          "codec": "h264", // string | null；输出视频编解码器名称。
          "frame_rate": "24/1", // string | null；ffprobe 平均帧率表达式，例如 24/1。
          "has_audio": false // boolean；输出文件是否包含音轨。
        },
        "origin": { // object；供应商原始输出项，保留链接/图层元数据，剔除 Base64。
          "url": "https://example.com/output.png", // string?；图片可下载 HTTPS URL。
          "size": "1024x1024", // string?；返回图片的 WIDTHxHEIGHT。
          "output_format": "png", // string?；输出格式，如 png。
          "z_index": 1, // integer?；拆层时的层级，底图为 0。
          "name": "狐狸", // string?；图层名称。
          "description": "示例文本", // string?；图层内容说明。
          "bounding_box": { // object?；图层位置。
            "absolute": [0, 0, 100, 100], // integer[]；底图像素坐标 [left,top,right,bottom]。
            "normalized": [0, 0, 100, 100] // integer[]；归一化 0～1000 坐标。
          },
          "error": { // object?；某个图片输出失败的原因。
            "code": "示例文本", // string?；供应商错误码。
            "message": "示例文本", // string?；经过脱敏的错误说明。
            "type": "text" // string?；供应商错误类别；仅供应商提供时出现。
          }
        },
        "provider": "volcengine", // Provider；输出所属供应商。
        "model": "doubao-seedream-5-0-pro-260628", // string；准确模型 ID。
        "task_id": "video-task-example", // string | null；供应商任务 ID，同步图片可为 null。
        "downloaded_at": "示例文本", // string；下载时间，UTC ISO 8601。
        "original": true // boolean；保留供应商原始文件，目前固定 true。
      }
    ],
    "usage": { // object | null；实际 API 用量；缺失时 null。
      "completion_tokens": 1, // integer?；生成消耗 Token，可用于刊例费用核对。
      "total_tokens": 1, // integer?；供应商返回的合计 Token。
      "tool_usage": { // object?；供应商返回的工具用量。
        "web_search": 1 // integer?；实际联网搜索调用次数。
      }
    },
    "actual_billed_amount_cny": null, // null；API 不返回人民币实付账单。
    "billing_currency": "CNY", // "CNY" | "USD"；供应商结算币种。
    "actual_billed_amount": null, // null；API 不返回账户实际扣款。
    "note": "说明文本", // string；交付及账单区分说明。
    "metadata": { // object?；拆层位置元数据缓存。
      "path": "/absolute/delivery/layers.json", // string；layers.json 缓存绝对路径。
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000" // string；位置元数据文件哈希。
    },
    "cost_comparison": { // CostComparison?；生成后刊例费用与预估核对。
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
  },
  "delivery": {}, // 完整内容同 deliver.py 的标准输出，不重复展开。
  "delivery_history": [{}] // 可选；每项与 delivery 同格式，不重复展开。
}
```


失败输出

已捕获异常的 stderr JSON 格式见 __init__.py；命令行参数错误使用 argparse usage 文本。
"""

import copy
import json
from pathlib import Path
from core.validation import require
from providers import consume_quote
from core.cost_record import amount_in
from core.envfile import config_value
from core.dependencies import require_dependencies
from core.operations import require_supported_operation
from core.submission_store import read, write, lock, prior_submission, next_submit_record, now
from providers import get_provider, get_capability
from core.http import ProviderError, response_error, sanitize_response


def validate_requirement(directory, spec, compiled):
    """核对提交内容和参数，使其与当前需求记录一致。"""
    record = read(directory / "request.json")
    require(isinstance(record, dict), "request.json must be an object")
    require(
        isinstance(record.get("intent"), dict)
        and record["intent"].get("operation") == spec["operation"],
        "Submission operation differs from request.json; update the plan and reconfirm",
    )
    require(
        isinstance(record.get("optimized_prompt"), str)
        and compiled["prompt"] == record["optimized_prompt"],
        "Submission prompt differs from request.json optimized_prompt; update the plan and reconfirm",
    )
    require(
        spec.get("original_prompt") == record.get("original_prompt")
        and isinstance(record.get("original_prompt"), str),
        "Submission original_prompt differs from request.json",
    )
    require(isinstance(record.get("providers"), dict), "Supplier plans missing from request.json")
    selected = record["providers"].get(compiled["provider"])
    require(isinstance(selected, dict), "Selected supplier is absent from request.json")
    from core.catalogs import CATALOGS

    expected_model = selected.get("model")
    models = CATALOGS[compiled["provider"]]["models"]
    expected_model = models.get(expected_model, {}).get("id", expected_model)
    require(
        expected_model == compiled["payload_template"]["model"]
        and selected.get("operation") == spec["operation"],
        "Submission model/operation differs from request.json; update the plan and reconfirm",
    )
    if compiled["operation"] in ("reference-to-video", "extend-video"):
        require(
            selected.get("mode") == compiled.get("mode"),
            "Submission mode differs from request.json; update the plan and reconfirm",
        )
    require(
        selected.get("estimate_context") == spec.get("estimate_context"),
        "Submission estimate_context differs from request.json; update the plan and reconfirm",
    )
    require(
        record.get("target_asset_id") == spec.get("target_asset_id"),
        "Submission target_asset_id differs from request.json; update the plan and reconfirm",
    )
    parameters = selected.get("parameters")
    require(isinstance(parameters, dict), "Supplier parameters missing from request.json")
    default_tools = (
        [{"type": "web_search"}]
        if compiled["kind"] == "video" and compiled["provider"] == "volcengine"
        and (compiled["operation"] == "text-to-video" or compiled["model"] == "seedance-2.5")
        else []
    )
    for key, value in parameters.items():
        # 图片构图偏好保留在原提示词中，不通过 API 的 ratio 字段传递。
        if compiled["kind"] == "image" and key == "ratio":
            size = compiled["parameters"]["size"]
            if "x" in size:
                try:
                    width, height = map(int, size.split("x"))
                    numerator, denominator = map(int, value.split(":"))
                except (ValueError, AttributeError):
                    raise ValueError("Invalid image ratio in request.json") from None
                require(
                    width * denominator == height * numerator,
                    "Pixel dimensions differ from request.json ratio",
                )
            continue
        if compiled["kind"] == "video" and key == "tools":
            require(
                compiled["parameters"].get("tools", []) == value,
                "Submission search settings differ from request.json; update and reconfirm",
            )
            continue
        require(
            compiled["parameters"].get(key) == value,
            "Submission parameter "
            + key
            + " differs from request.json; update the plan and reconfirm",
        )
    if compiled["kind"] == "video":
        require(
            parameters.get("tools", default_tools)
            == compiled["parameters"].get("tools", default_tools),
            "Submission search settings differ from request.json; update and reconfirm",
        )
        # 非默认输出及回调设置必须在已确认方案中明确记录。
        for key, default in (('watermark', False), ('return_last_frame', False),
                             ('output_format', 'mp4'), ('callback_url', None),
                             ('safety_identifier', None)):
            if compiled['parameters'].get(key, default) != default:
                require(key in parameters,
                        'Video option ' + key + ' missing from request.json; update the plan and reconfirm')
        required = {"resolution", "duration", "generate_audio"}
        if compiled["operation"] == "text-to-video" or (
            compiled["operation"] == "reference-to-video" and compiled.get("mode") == "reference"
        ):
            required.add("ratio")
        require(
            required <= set(parameters),
            "Video decision parameters missing from request.json; update the plan and reconfirm",
        )
    if compiled["kind"] in ("image", "video"):
        if compiled["kind"] == "image":
            require(
                "size" in parameters, "Image size missing from request.json supplier parameters"
            )
        if spec["operation"] in ("text-to-image", "text-to-video"):
            require(selected.get("assets") == [], "Text generation supplier assets must be empty")
        else:
            catalog = record.get("assets")
            refs = selected.get("assets")
            require(
                isinstance(catalog, list) and all(isinstance(a, dict) for a in catalog),
                "Image asset catalog missing from request.json",
            )
            ids = [a.get("id") for a in catalog]
            require(
                all(isinstance(i, str) and i.strip() for i in ids) and len(set(ids)) == len(ids),
                "Image asset ids must be unique nonempty strings",
            )
            require(
                isinstance(refs, list)
                and all(isinstance(a, dict) and set(a) == {"id"} for a in refs),
                "Supplier assets must contain ordered id references",
            )
            by_id = {a["id"]: a for a in catalog}
            require(all(a["id"] in by_id for a in refs), "Unknown supplier asset reference")
            expected = [by_id[a["id"]] for a in refs]
            actual = compiled["assets"]
            require(
                len(expected) == len(actual)
                and all(
                    e.get("kind") == a["kind"]
                    and e.get("source") == a["source"]
                    and e.get("id") == a.get("id")
                    and e.get("purpose") == a.get("purpose")
                    for e, a in zip(expected, actual)
                ),
                "Submission assets/order differ from request.json or cost artifact; update and reconfirm",
            )


def submit(jobdir, spec, approval_text, accept_uncertain=False):
    d = Path(jobdir).resolve()
    require(
        bool(approval_text.strip()),
        "Record the actual user confirmation; never manufacture approval",
    )
    submitted_input = copy.deepcopy(spec)
    with lock(d):
        prior_submission(d)
        require(
            isinstance(spec, dict) and bool(spec.get("provider")),
            "Select an explicit supplier in the task request",
        )
        get_provider(spec["provider"])
        require_supported_operation(spec)
        cost = read(d / (spec["provider"] + "-priceing.json"))
        spec, compiled, pricing, estimate = consume_quote(spec, cost)
        for unit in ("cny", "usd"):
            if spec.get("budget_" + unit) is not None:
                upper = amount_in(estimate, unit.upper())["max"]
                require(upper is not None, "Cannot compare budget with unknown amount/conversion")
                require(
                    upper <= spec["budget_" + unit],
                    "Estimated amount exceeds budget; revise the request",
                )
        validate_requirement(d, spec, compiled)
        require_dependencies()
        plan = {"compiled": compiled, "estimate": estimate}
        info = get_provider(plan["compiled"]["provider"])
        adapter = info["adapter"]
        capability = get_capability(compiled["provider"], compiled["operation"])
        if plan["estimate"]["amount"]["max"] is None:
            require(
                accept_uncertain,
                "Cost upper estimate unknown; require explicit user acceptance of uncertainty",
            )
        require(bool(config_value(adapter.KEY_ENV)), adapter.KEY_ENV + " is not configured")
        # 先在本地转换素材，检查素材可读性后才记录付费尝试；Base64 正文不写日志。
        # 记录付费尝试前先转换素材，绝不将 Base64 请求正文写入日志。
        payload = capability.build_payload(compiled)
        require(
            len(json.dumps(payload, ensure_ascii=False).encode()) <= 64 * 1024 * 1024,
            "Request exceeds 64 MB",
        )
        # 先落盘 submitting，再开始网络操作；崩溃或中断也留下不可重复提交的审计记录。
        state = {
            "state": "submitting",
            "created_at": now(),
            "compiled": compiled,
            "approval": {
                "text": approval_text,
                "recorded_at": now(),
                "accept_uncertain_cost": accept_uncertain,
            },
            "provider": plan["compiled"]["provider"],
            "model": plan["compiled"]["model"],
            "task_id": None,
        }
        state['cost_record'] = copy.deepcopy(cost)
        record_path = next_submit_record(d)
        state["submission"] = str(record_path)
        record = {**submitted_input, "response": None, "execution": state}
        write(d / "payload.json", submitted_input)
        write(record_path, record)
        try:
            # 本模块唯一的付费网络入口：一次 POST，没有重试循环，也没有备用供应商分支。
            # 本模块唯一的付费网络操作：只执行一次 POST，绝不自动重试。
            result = capability.submit(compiled, payload)
            result = sanitize_response(result, secrets=(compiled["prompt"],))
            record["response"] = result
            write(record_path, record)
            if result.get("error"):
                raise response_error(
                    result["error"], provider_name=info["name"], secrets=(compiled["prompt"],)
                )
            # 视频响应只代表任务已创建，进入 queued；图片响应为同步结果，但仍逐项检查错误。
            if plan["compiled"]["kind"] == "video":
                require(
                    isinstance(result.get("id"), str) and bool(result["id"]),
                    "POST response did not contain task ID",
                )
                state.update(state="queued", task_id=result["id"])
            else:
                state.update(capability.response_state(result, compiled))
        # 有不确定性的供应商错误或响应处理异常保留 submission_unknown；明确拒绝才记 rejected。
        except Exception as exc:
            state.update(
                state=(
                    "submission_unknown"
                    if not isinstance(exc, ProviderError) or exc.uncertain
                    else "rejected"
                ),
                error=(
                    str(exc) if isinstance(exc, (ValueError, ProviderError)) else type(exc).__name__
                ),
            )
            if isinstance(exc, ProviderError) and exc.details is not None:
                record["response"] = {"error": exc.details}
            write(record_path, record)
            raise
        state["updated_at"] = now()
        write(record_path, record)
        return state


def run(args):
    import sys

    if args.request:
        spec = read(args.request)
    else:
        require(not sys.stdin.isatty(), "Supply the request JSON object on stdin")

        def reject_constant(value):
            raise ValueError("Invalid JSON numeric constant: " + value)

        spec = json.loads(sys.stdin.read(), parse_constant=reject_constant)
        require(isinstance(spec, dict), "Request input must be a JSON object")
    state = submit(args.workdir, spec, args.approval_text, args.accept_uncertain_cost)
    return {"submission": state["submission"]}
