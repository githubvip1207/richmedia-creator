# BytePlus

## 模型列表

| 模型 | 类型 | 调用别名 | 模型 ID | 输出分辨率 / 尺寸档位 | 输出时长上限 | 输出格式 |
|---|---|---|---|---|---|---|
| Seedance 2.5 | 视频 | `seedance-2.5` | `dreamina-seedance-2-5-260628` | 480p、720p、1080p | 30 秒 | mp4、mov |
| Seedance 2.0 | 视频 | `seedance-2.0` | `dreamina-seedance-2-0-260128` | 480p、720p、1080p、4k | 15 秒 | mp4 |
| Seedance 2.0 Fast | 视频 | `seedance-2.0-fast` | `dreamina-seedance-2-0-fast-260128` | 480p、720p | 15 秒 | mp4 |
| Seedance 2.0 Mini | 视频 | `seedance-2.0-mini` | `dreamina-seedance-2-0-mini-260615` | 480p、720p | 15 秒 | mp4 |
| Seedream 5.0 Pro | 图片 | `seedream-5.0-pro` | `dola-seedream-5-0-pro-260628` | 1K、1.5K、2K | 不适用 | png、jpeg |
| Seedream 5.0 Flash | 图片 | `seedream-5.0-flash` | `dola-seedream-5-0-flash-260915` | 1K、1.5K、2K | 不适用 | png、jpeg |

## 能力列表

“支持模型（价格从高到低）”使用 `>` 表示价格由高到低，依据本供应商当前维护的价目表在同等输出规格下排序。用户未指定模型时，先筛选满足当前模式、素材及全部生成要求的模型，再按本表价格顺序选择其中最便宜的模型；本供应商独立选择，不要求与其他供应商采用同一模型。用户指定模型时，本供应商仅在支持该模型且满足需求时参与估价，否则说明排除原因，不替换为其他模型。最终费用以本次成本预估为准，价目表更新时同步维护排序。

| 能力 | 支持模式 | 支持模型（价格从高到低） | 脚本实现 | 详细说明 |
|---|---|---|---|---|
| 文生图 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [文生图](byteplus/text-to-image.md) |
| 图生图 | 单图编辑、多图融合、局部编辑 | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [图生图](byteplus/image-to-image.md) |
| 图层拆分 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [图层拆分](byteplus/decompose-layers.md) |
| 文生视频 | — | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 已实现 | [文生视频](byteplus/text-to-video.md) |
| 图生视频 | 首帧、首尾帧 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 已实现 | [图生视频](byteplus/image-to-video.md) |
| 参考生视频 | 参考生成、视频编辑 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini；纯音频参考仅 Seedance 2.5 | 已实现 | [参考生视频](byteplus/reference-to-video.md) |
| 视频延长 | 向前延长、向后延长 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 已实现 | [视频延长](byteplus/extend-video.md) |

同一能力下，不同模式或模型的素材要求、参数和限制，见对应能力的调用要求。视频联网搜索当前未实现，不纳入本供应商方案。

## 预估成本

共同规则见[成本估算与核对](cost-estimation.md)：官方门槛优先，读取失败时使用有来源的估算并标明假设；不要仅因缺少精确门槛或 adaptive 尺寸就停止估价。

BytePlus 使用独立美元价目表；有有效汇率时仅采用脚本返回的换算金额，没有有效汇率时仅展示美元原币。根据能力和用户要求构建成本参数 JSON；Python 脚本读取供应商单价描述文件，检查素材并解析计费所需的数据，最后按本节公式计算。不要让大模型填写图片数量、素材实测尺寸、素材实测时长、单价或最终金额。

### 文生图、图生图计费

#### 计算公式

```text
额外输入图片数量 = max(输入图片数量 − 1, 0)
输出费用 = 一张输出图片对应像素档位的单价
输入费用 = 额外输入图片数量 × 模型的额外输入图片单价
预计费用 = 输出费用 + 输入费用
```

#### 估价输入

根据前两步的信息组织如下 JSON 内容，作为 cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "byteplus", // 必需：供应商；Python 据此读取 models/byteplus-pricing.json，不传单价或价格文件路径
  "model": "seedream-5.0-pro", // 必需：模型别名或准确 ID；Python 读取该模型的输出费率、额外输入费率和像素阈值
  "operation": "image-to-image", // 必需：文生图为 text-to-image，图生图为 image-to-image
  "size": "1K", // 必需：1K、1.5K 使用低像素档，2K 使用高像素档；准确 WxH 由 Python 计算宽×高后与费率阈值比较
  "assets": [ // 文生图省略或传 []；单图编辑 1 张、多图融合 2～10 张、局部编辑 1～10 张
    {
      "id": "product", // 素材标识：与初始化记录中的 id 一致，仅用于关联，不参与计费
      "kind": "image", // 必需：此处仅接受图片，Python 检查并统计输入数量，不传手工张数
      "source": "/absolute/path/product.png" // 必需：实际本地绝对路径或可访问 HTTPS URL；Python 读取素材尺寸，输入图尺寸不代替输出尺寸
    },
    {
      "id": "background", // 素材标识：与初始化记录中的 id 一致，仅用于关联，不参与计费
      "kind": "image", // 本例为多图融合的第二张参考图
      "source": "/absolute/path/background.png" // 替换为实际背景素材地址；Python 保留 id 便于关联素材，按 kind、source 读取媒体信息
    }
  ]
  // Pro 从第二张输入图收取附加费；Flash 是否收取由单价文件的 input_after_first 决定。
  // 不传图片实测尺寸、输入数量或最终金额；由 Python 解析素材、读取单价并按上述公式计算。
}
```

### 图层拆分计费

#### 计算公式

```text
实际费用 = 底图费用 + 每张输出图层的费用
生成前按可能的 1～17 份输出及像素档位估算：
最低预计费用 = 一张低像素档图层输出的单价
最高预计费用 = 17 × 一张高像素档图层输出的单价
```

#### 估价输入

根据前两步的信息组织如下 JSON 内容，作为 cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "byteplus", // 必需：供应商；Python 自行读取 models/byteplus-pricing.json，不传单价或文件路径
  "model": "seedream-5.0-flash", // 必需：模型别名或准确 ID；Python 读取该模型的 layer 费率
  "operation": "decompose-layers", // 必需：图层拆分，不提供 mode
  "size": "1K", // 必需：与已确定的输出规格一致；用户未指定时默认最小尺寸，支持明确指定 auto；不能据此确定各张未来图层的尺寸
  "assets": [ // 必需：只能提供 1 张待拆分图片，Python 校验数量并读取尺寸
    {
      "id": "layer-source", // 素材标识：与初始化记录中的 id 一致，仅用于关联，不参与计费
      "kind": "image", // 必需：图层拆分只接受图片
      "source": "/absolute/path/product.png" // 必需：实际本地绝对路径或可访问 HTTPS URL；Python 通过 id 关联本次拆分素材
    }
  ]
  // 不传未来图层数量或每层像素：生成前无法确定，Python 按 1～17 份输出及全部像素档位计算费用范围。
  // 此范围不是承诺输出 17 张；不能用一张图的费用代表整次拆分。
}
```

### 文生视频、图生视频、参考生视频、视频延长计费

#### 计算公式

```text
参与计算的时长 = 所有输入视频总时长 + 输出视频时长
公式 Token = 向上取整(参与计算的时长 × 输出宽 × 输出高 × 24 ÷ 1024)
无视频输入：计费 Token = 公式 Token
有视频输入：计费 Token = max(公式 Token, 本规格的最低计费 Token)
预计费用 = 计费 Token × 每百万 Token 单价 ÷ 1,000,000
```

#### 估价输入

根据前两步的信息组织如下 JSON 内容，作为 cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "byteplus", // 必需：供应商；Python 自行读取 models/byteplus-pricing.json
  "model": "seedance-2.5", // 必需：模型别名或准确 ID；Python 根据模型、分辨率及有无视频输入选择单价
  "operation": "image-to-video", // 必需：文生视频、图生视频、参考生视频或视频延长
  // "mode": "reference", // 参考生视频必需：reference / edit；视频延长必需：before / after；文生视频和图生视频省略
  "resolution": "480p", // 必需：所选模型支持的分辨率；与模型和比例共同确定输出宽高，不直接复用输入像素
  "ratio": "adaptive", // 必需：图生视频固定 adaptive；其他任务按所选模型和能力的比例限制填写
  "duration": 4, // 必需：输出秒数，或模型允许的 -1；2.5 编辑必须为 -1，Python 读取目标时长后估算 [源时长-0.4, 源时长]
  "assets": [ // 文生视频省略或传 []；首帧 1 张图、首尾帧按顺序 2 张；参考生成必须有素材；编辑/延长必须有视频
    {
      "id": "first-frame", // 素材标识：与初始化记录中的 id 一致，仅用于关联，不参与计费
      "kind": "image", // 必需：image/video/audio；2.0 不支持纯音频参考，Python 校验各类型数量及音视频时长
      "source": "/absolute/path/first-frame.png" // 必需：实际本地绝对路径或 HTTPS URL；Python 用 ffprobe 读取宽高和时长，不传实测元数据，id 仅用于关联素材
    }
  ],
  "estimate_context": { // 条件字段：仅有补充计费依据时填写；本例无额外依据可省略整个对象；这些内容不传给生成 API
    // "target_asset_index": 0, // 多视频编辑/延长时明确目标；从 0 开始，针对整个 assets 数组，必须与提示词目标一致；单视频或首帧由 Python 自动确定
    // "output_dimensions": [854, 480] // 仅在无法自动推导且有官方依据时填写 [输出宽, 输出高]；不是输入图尺寸，不保证实际输出像素
    // minimum_billable_tokens：有官方表格/计算器对应行时优先填写；缺少时脚本使用有来源的公开示例估算。无视频输入无需填写。
    // 固定输出时长填写一个正数；自动时长填写覆盖完整时长范围的 [门槛下界, 门槛上界]，不得将示例数值当作真实门槛。
    // minimum_tokens_source：填写上述门槛对应的官方表格或计算器 HTTPS URL；与 minimum_billable_tokens 一起提供。
    // minimum_tokens_spec：手动门槛同时绑定 {model, resolution, ratio, duration}，值与本次规格一致。
    // preferred_duration：自动时长任务可填需求中期望的秒数，只标记费用情景，不改变 API 的 duration=-1。
  }
  // Python 将全部输入视频的实测时长求和；图片、音频时长不加入该时长，输出帧率按 24 FPS 估算。
  // 2.5 自适应首帧/首尾帧按第一张图的比例查官方输出像素表；编辑/延长按目标视频比例查表，不直接使用输入素材像素。
  // 例如首帧为 1280×720、输出 480p 时，使用 854×480 估算；近似标准比例允许取整误差；任意比例按素材显示比例和同分辨率像素面积推算，模型自行选择比例时覆盖官方候选尺寸；假设写入 result.uncertainties。
  // duration=-1：2.5 编辑使用上述目标时长范围；多个视频未指定目标时覆盖所有候选。其他任务按模型允许的 4～30 秒或 4～15 秒范围计算两端费用。
  // 含视频输入但未取得最低用量表时，按 models/video-cost-evidence.json 中的官方5秒最低价格示例反推；其他时长/像素按比例外推，明确标注 public_example_scaled，不冒充已核实门槛或保证上下界。
  // 输出尺寸规则：https://docs.byteplus.com/en/docs/modelark/create-video-generation-task-api
  // 最低计费门槛来源：https://docs.byteplus.com/en/docs/modelark/model-pricing
}
```

## 能力使用指南

按当前能力读取对应文档；每份文档包含该能力的生成要求和生成步骤。

| 能力 | operation | 使用指南 |
|---|---|---|
| 文生图 | `text-to-image` | [文生图](byteplus/text-to-image.md) |
| 图生图 | `image-to-image` | [图生图](byteplus/image-to-image.md) |
| 图层拆分 | `decompose-layers` | [图层拆分](byteplus/decompose-layers.md) |
| 文生视频 | `text-to-video` | [文生视频](byteplus/text-to-video.md) |
| 图生视频 | `image-to-video` | [图生视频](byteplus/image-to-video.md) |
| 参考生视频 | `reference-to-video` | [参考生视频](byteplus/reference-to-video.md) |
| 视频延长 | `extend-video` | [视频延长](byteplus/extend-video.md) |

## 官方来源

- [Seedream Pro/Flash 教程](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro) — 模型能力与使用说明。
- [交互式图片编辑](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro-editing-guide) — 局部编辑与区域表达。
- [图片 API](https://docs.byteplus.com/en/docs/modelark/image-generation-api) — 维护脚本时核对参数及响应。
- [模型列表](https://docs.byteplus.com/en/docs/modelark/model-list) — 模型 ID 与规格。
- [模型价格](https://docs.byteplus.com/en/docs/modelark/model-pricing) — 计费规则与官方单价。
- [BytePlus 创建视频任务](https://docs.byteplus.com/en/docs/modelark/create-video-generation-task-api)
- [BytePlus Seedance 2.5](https://docs.byteplus.com/en/docs/modelark/seedance-2-5)
- [BytePlus Seedance 2.0 系列](https://docs.byteplus.com/en/docs/modelark/seedance-2-0)
- [BytePlus 查询视频任务](https://docs.byteplus.com/en/docs/modelark/get-video-generation-task-api)
