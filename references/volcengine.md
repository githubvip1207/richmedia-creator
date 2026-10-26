# Volcengine

## 能力列表

“支持模型（价格从高到低）”使用 `>` 表示价格由高到低，依据本供应商当前维护的价目表在同等输出规格下排序。用户未指定模型时，先筛选满足当前模式、素材及全部生成要求的模型，再按本表价格顺序选择其中最便宜的模型；本供应商独立选择，不要求与其他供应商采用同一模型。用户指定模型时，本供应商仅在支持该模型且满足需求时参与估价，否则说明排除原因，不替换为其他模型。最终费用以本次成本预估为准，价目表更新时同步维护排序。

| 能力 | 支持模式 | 支持模型（价格从高到低） | 详细说明 |
|---|---|---|---|---|
| 文生图 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | [文生图](volcengine/text-to-image.md) |
| 图生图 | 单图编辑、多图融合、局部编辑 | Seedream 5.0 Pro > Seedream 5.0 Flash | [图生图](volcengine/image-to-image.md) |
| 图层拆分 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | [图层拆分](volcengine/decompose-layers.md) |
| 文生视频 | — | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | [文生视频](volcengine/text-to-video.md) |
| 图生视频 | 首帧、首尾帧 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | [图生视频](volcengine/image-to-video.md) |
| 参考生视频 | 参考生成、视频编辑 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini；纯音频参考仅 Seedance 2.5 | [参考生视频](volcengine/reference-to-video.md) |
| 视频延长 | 向前延长、向后延长 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | [视频延长](volcengine/extend-video.md) |

同一能力下，不同模式或模型的素材要求、参数和限制，见对应能力的调用要求。

## 模型列表

| 模型 | 类型 | 调用别名 | 模型 ID | 输出分辨率 / 尺寸档位 | 输出时长上限 | 输出格式 |
|---|---|---|---|---|---|---|
| Seedance 2.5 | 视频 | `seedance-2.5` | `doubao-seedance-2-5-260628` | 480p、720p、1080p | 30 秒 | mp4、mov |
| Seedance 2.0 | 视频 | `seedance-2.0` | `doubao-seedance-2-0-260128` | 480p、720p、1080p、4k | 15 秒 | mp4 |
| Seedance 2.0 Fast | 视频 | `seedance-2.0-fast` | `doubao-seedance-2-0-fast-260128` | 480p、720p | 15 秒 | mp4 |
| Seedance 2.0 Mini | 视频 | `seedance-2.0-mini` | `doubao-seedance-2-0-mini-260615` | 480p、720p | 15 秒 | mp4 |
| Seedream 5.0 Pro | 图片 | `seedream-5.0-pro` | `doubao-seedream-5-0-pro-260628` | 1K、1.5K、2K | 不适用 | png、jpeg |
| Seedream 5.0 Flash | 图片 | `seedream-5.0-flash` | `doubao-seedream-5-0-flash-260915` | 1K、1.5K、2K | 不适用 | png、jpeg |

## 预估成本

按已确定的生成方案填写计费 JSON，通过 `cost` 的标准输入传入。实际文件为 UTF-8 标准 JSON，写文件前删除示例中的 `//` 注释。脚本自行读取 `models/volcengine-pricing.json` 中的单价与计费依据，并测量素材；不传生成 API 的 `payload`、单价、最低 Token、素材实测数据或最终金额。

### 文生图、图生图计费

#### 计算公式

```text
额外输入图片数量 = max(输入图片数量 − 1, 0)
输入费用 = 额外输入图片数量 × 额外输入单价
输出费用 = 输出图片数量 × 对应像素档位单价
预计费用 = 输入费用 + 输出费用
```

#### 输入要求

```jsonc
{
  "provider": "volcengine", // 必填：本次供应商。
  "model": "seedream-5.0-pro", // 必填：已确定的模型别名或准确 ID。
  "operation": "image-to-image", // 必填：文生图 text-to-image；图生图 image-to-image。
  "size": "1K", // 必填：输出尺寸档位或 WIDTHxHEIGHT；按对应模型支持范围填写。
  "assets": [ // 图生图必填，按实际使用顺序提供；文生图省略或传 []。
    {
      "id": "product", // 可选；关联初始化/提交素材时使用相同 id。
      "kind": "image", // 必填：图片能力只接受 image。
      "source": "/absolute/path/product.png" // 必填：真实本地绝对路径或可访问的 HTTPS URL。
    }
  ]
}
```

脚本自动统计输入图片数量、探测尺寸并选择费率。1K/1.5K 按低像素档、2K 按高像素档估算；明确 WIDTHxHEIGHT 时计算面积后与价格文件的像素阈值比较。当前单次按一张输出估价，不传手填数量或素材 `purpose`；额外输入图是否收费取决于该模型价格配置。

### 图层拆分计费

#### 计算公式

```text
实际费用 = 底图费用 + 各输出图层费用之和
估算起点 = 1 × 低像素档拆层输出单价
估算终点 = 17 × 高像素档拆层输出单价
```

#### 输入要求

```jsonc
{
  "provider": "volcengine", // 必填：本次供应商。
  "model": "seedream-5.0-flash", // 必填：支持拆层的模型别名或准确 ID。
  "operation": "decompose-layers", // 必填：图层拆分，不传 mode。
  "size": "1K", // 必填：已确定的输出尺寸，支持范围见能力指南；可明确指定 auto。
  "assets": [ // 必填：只能有一张待拆分图片。
    {
      "id": "layer-source", // 可选；关联初始化/提交素材时使用相同 id。
      "kind": "image", // 必填：待拆分素材类型。
      "source": "/absolute/path/product.png" // 必填：真实本地绝对路径或可访问的 HTTPS URL。
    }
  ]
}
```

未来图层数量及各层像素无法提前确定，由脚本按含底图的 1～17 份输出和像素档位估算，并提供 1、4、8、17 份费用情景。不要填写未来图层数量或把输出 size 当作所有图层的实际尺寸；估算数量不代表模型承诺的输出数量。

### 文生视频、图生视频、参考生视频、视频延长计费

#### 计算公式

```text
参与计费时长 = 所有输入视频的实测时长之和 + 输出视频时长
公式 Token = 向上取整(参与计费时长 × 输出宽 × 输出高 × 24 ÷ 1024)
无视频输入：计费 Token = 公式 Token
有视频输入：计费 Token = max(公式 Token, 本规格的最低计费 Token)
预计费用 = 计费 Token × 对应模型/分辨率/输入类型的每百万 Token 单价 ÷ 1,000,000
```

#### 输入要求

```jsonc
{
  "provider": "volcengine", // 必填：本次供应商。
  "model": "seedance-2.5", // 必填：已确定的视频模型别名或准确 ID。
  "operation": "image-to-video", // 必填：text-to-video/image-to-video/reference-to-video/extend-video。
  // "mode": "reference", // 参考生视频必填 reference/edit；视频延长必填 before/after；文生/图生视频省略。
  "resolution": "480p", // 必填：已确定且模型支持的输出分辨率。
  "ratio": "adaptive", // 必填：图生视频、延长及 2.5 编辑使用 adaptive；其他模式按能力要求填写。
  "duration": 4, // 必填：输出秒数或模型允许的 -1；2.5 编辑必须 -1；延长时指新增输出时长。
  "assets": [ // 文生视频省略或 []；图生视频为一张首帧或按首帧、尾帧顺序两张图。
    { // 参考生成提供有序参考素材；编辑/延长必须有视频；具体组合见能力指南。
      "id": "first-frame", // 可选；关联初始化/提交素材时使用相同 id。
      "kind": "image", // 必填：实际素材类型 image/video/audio；本例为首帧图片。
      "source": "/absolute/path/first-frame.png" // 必填：真实本地绝对路径或 HTTPS URL；脚本自动测量时长和尺寸。
    }
  ],
  // 多视频编辑/延长时必填：引用 assets 中目标视频的 id；单视频时可省略。
  // "target_asset_id": "main-video",
  "estimate_context": { // 条件字段：仅填写满足下列条件的项；全部不适用时省略整个对象，不传给生成 API。
    // "preferred_duration": 10, // 仅 duration=-1 且用户明确期望秒数时填写；只标记费用情景，不控制实际时长。
    // "output_dimensions": [854, 480] // 仅脚本无法自动确定输出像素、且有官方明确尺寸依据时填写；不是输入素材尺寸。
  }
}
```

- 按注释中的条件启用字段并替换实际值；本例为固定时长图生视频，可省略 `estimate_context`。成本探测可使用本地素材，正式提交时按能力指南要求提供素材地址。
- 计费时长仅合计输入视频，图片和音频不计入。自动输出时长按模型有效范围估价；2.5 编辑按目标时长及约 0.4 秒差异估算。
- adaptive 输出像素按首帧或目标视频的显示比例查表或推算；最低 Token 优先使用价格文件中的官方门槛，缺少时按公开示例估算。`estimate_quality=extrapolated` 表示包含未校准外推，须说明误差限制。
- 根据 `uncertainties` 说明假设、`scenarios` 展示费用情景；生成后通过 `cost_comparison` 核对刊例费用。估算区间不是收费保证，刊例核算不等于实际扣款。

## 能力使用指南

按当前能力读取对应文档；每份文档包含该能力的生成要求和生成步骤。

| 能力 | operation | 使用指南 |
|---|---|---|
| 文生图 | `text-to-image` | [文生图](volcengine/text-to-image.md) |
| 图生图 | `image-to-image` | [图生图](volcengine/image-to-image.md) |
| 图层拆分 | `decompose-layers` | [图层拆分](volcengine/decompose-layers.md) |
| 文生视频 | `text-to-video` | [文生视频](volcengine/text-to-video.md) |
| 图生视频 | `image-to-video` | [图生视频](volcengine/image-to-video.md) |
| 参考生视频 | `reference-to-video` | [参考生视频](volcengine/reference-to-video.md) |
| 视频延长 | `extend-video` | [视频延长](volcengine/extend-video.md) |

## 官方文档

- [模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh) — 模型 ID 与规格。
- [模型价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh) — 计费规则与官方单价。
- [图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh) — 维护脚本时核对参数及响应。
- [Seedream Pro/Flash 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh) — 模型能力与使用说明。
- [Volcengine 创建视频任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)
- [交互式图片编辑](https://docs.volcengine.com/docs/ark/seedream-5-0-pro-editing-guide?lang=zh) — 局部编辑与区域表达。
- [Volcengine Seedance 2.5](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)
