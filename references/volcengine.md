# Volcengine

## 模型列表

| 模型 | 类型 | 调用别名 | 模型 ID | 输出分辨率 / 尺寸档位 | 输出时长上限 | 输出格式 |
|---|---|---|---|---|---|---|
| Seedance 2.5 | 视频 | `seedance-2.5` | `doubao-seedance-2-5-260628` | 480p、720p、1080p | 30 秒 | mp4、mov |
| Seedance 2.0 | 视频 | `seedance-2.0` | `doubao-seedance-2-0-260128` | 480p、720p、1080p、4k | 15 秒 | mp4 |
| Seedance 2.0 Fast | 视频 | `seedance-2.0-fast` | `doubao-seedance-2-0-fast-260128` | 480p、720p | 15 秒 | mp4 |
| Seedance 2.0 Mini | 视频 | `seedance-2.0-mini` | `doubao-seedance-2-0-mini-260615` | 480p、720p | 15 秒 | mp4 |
| Seedream 5.0 Pro | 图片 | `seedream-5.0-pro` | `doubao-seedream-5-0-pro-260628` | 1K、1.5K、2K | 不适用 | png、jpeg |
| Seedream 5.0 Flash | 图片 | `seedream-5.0-flash` | `doubao-seedream-5-0-flash-260915` | 1K、1.5K、2K | 不适用 | png、jpeg |

## 能力列表

“支持模型（价格从高到低）”使用 `>` 表示价格由高到低，依据本供应商当前维护的价目表在同等输出规格下排序。用户未指定模型时，先筛选满足当前模式、素材及全部生成要求的模型，再按本表价格顺序选择其中最便宜的模型；本供应商独立选择，不要求与其他供应商采用同一模型。用户指定模型时，本供应商仅在支持该模型且满足需求时参与估价，否则说明排除原因，不替换为其他模型。最终费用以本次成本预估为准，价目表更新时同步维护排序。

| 能力 | 支持模式 | 支持模型（价格从高到低） | 脚本实现 | 详细说明 |
|---|---|---|---|---|
| 文生图 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [文生图](#文生图operationtext-to-image) |
| 图生图 | 单图编辑、多图融合、局部编辑 | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [图生图](#图生图operationimage-to-image) |
| 图层拆分 | — | Seedream 5.0 Pro > Seedream 5.0 Flash | 已实现 | [图层拆分](#图层拆分operationdecompose-layers) |
| 文生视频 | — | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 已实现 | [文生视频](#文生视频operationtext-to-video) |
| 图生视频 | 首帧、首尾帧 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 已实现 | [图生视频](#图生视频operationimage-to-video) |
| 参考生视频 | 参考生成、视频编辑 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini；纯音频参考仅 Seedance 2.5 | 未实现 | — |
| 视频延长 | 向前延长、向后延长 | Seedance 2.5 > Seedance 2.0 > Seedance 2.0 Fast > Seedance 2.0 Mini | 未实现 | — |

同一能力下，不同模式或模型的素材要求、参数和限制，见对应能力的调用要求。

## 预估成本

根据能力和用户要求构建成本参数 JSON；Python 脚本读取供应商单价描述文件，检查素材并解析计费所需的数据，最后按本节公式计算。不要让大模型填写图片数量、素材实测尺寸、素材实测时长、单价或最终金额。

### 文生图、图生图计费

#### 计算公式

```text
额外输入图片数量 = max(输入图片数量 − 1, 0)
输出费用 = 一张输出图片对应像素档位的单价
输入费用 = 额外输入图片数量 × 模型的额外输入图片单价
预计费用 = 输出费用 + 输入费用
```

#### 估价输入

根据前两步的信息组织如下 JSON 内容，作为 estimate-cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "volcengine", // 必需：供应商；Python 据此读取 models/volcengine-pricing.json，不传单价或价格文件路径
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

根据前两步的信息组织如下 JSON 内容，作为 estimate-cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "volcengine", // 必需：供应商；Python 自行读取 models/volcengine-pricing.json，不传单价或文件路径
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

根据前两步的信息组织如下 JSON 内容，作为 estimate-cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "volcengine", // 必需：供应商；Python 自行读取 models/volcengine-pricing.json
  "model": "seedance-2.5", // 必需：模型别名或准确 ID；Python 根据模型、分辨率及有无视频输入选择单价
  "operation": "image-to-video", // 必需：text-to-video 文生视频、image-to-video 图生视频、reference-to-video 参考生视频、extend-video 视频延长
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
    // minimum_billable_tokens：含视频输入时，从官方表格或计算器核实本模型、分辨率、比例、输出时长的最低 Token；无视频输入无需填写。
    // 固定输出时长填写一个正数；自动时长填写覆盖完整时长范围的 [门槛下界, 门槛上界]，不得将示例数值当作真实门槛。
    // minimum_tokens_source：填写上述门槛对应的官方表格或计算器 HTTPS URL；与 minimum_billable_tokens 一起提供。
  }
  // Python 将全部输入视频的实测时长求和；图片、音频时长不加入该时长，输出帧率按 24 FPS 估算。
  // 2.5 自适应首帧/首尾帧按第一张图的比例查官方输出像素表；编辑/延长按目标视频比例查表，不直接使用输入素材像素。
  // 例如首帧为 1280×720、输出 480p 时，使用 854×480 估算；任意比例或模型自行决定的比例无法可靠推导时返回 unknown，并在 result.uncertainties 中说明原因。
  // duration=-1：2.5 编辑使用上述目标时长范围；多个视频未指定目标时覆盖所有候选。其他任务按模型允许的 4～30 秒或 4～15 秒范围计算两端费用。
  // 含视频输入但缺少已核实最低门槛时，只返回 lower_bound，上界未知；不能当作完整报价，更不能编造门槛。
  // 输出尺寸规则：https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh
  // 最低计费门槛来源：https://docs.volcengine.com/docs/ark/model-pricing?lang=zh
}
```

## 能力使用指南

### 文生图（`operation=text-to-image`）

#### 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 必需 | 参考模型列表中的尺寸约束；用户未指定时默认最小尺寸；已指定时按用户要求 |

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。

#### 生成步骤

以下步骤在用户需要文生图且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "text-to-image", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "生成一张正方形熊猫图片", // 流程记录：用户原始提示词，不提交给供应商
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录后原样提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用 Pro 时替换为对应 ID
       "prompt": "一只熊猫坐在草坡上，柔和自然光，写实摄影，不添加文字。构图比例偏好：1:1。", // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
       "size": "1K", // 必需：1K、1.5K、2K，或符合像素及比例限制的 WxH；用户未指定时默认最小尺寸
       "output_format": "png", // 固定：PNG
       "response_format": "url", // 固定：返回 URL
       "watermark": false, // 固定：不加平台水印
       "background": "opaque", // 固定：不启用透明背景
       "layer_decomposition": false // 固定：文生图不启用图层拆分；optimize_prompt_options 固定省略
     }
   }
   ```
2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态，如果失败则提示用户，如果成功则继续交付。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终媒体交付到启动本技能时所在的当前项目目录，图层拆分同时交付位置元数据，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。


### 图生图（`operation=image-to-image`）

#### 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 必需 | 参考模型列表中的尺寸约束；用户未指定时默认最小尺寸；已指定时按用户要求 |
| `assets` | 必需 | 单图编辑 1 张；多图融合 2～10 张；局部编辑 1～10 张。按确认顺序提供本地绝对路径或 HTTPS URL，可混用。 |

- 素材要求

支持 JPEG、PNG、WebP、BMP、TIFF、GIF、HEIC、HEIF。每张图片不超过 30 MiB，宽高均大于 14 px，总像素不超过 3600 万，宽高比为 1/16～16。素材来源须为本地绝对路径或可访问的 HTTPS URL，按下方示例填写外层 `assets`。

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。

图生图提示词须结合实际参考图，明确修改项、保留项及各图片用途；多图按输入顺序称“图片1”“图片2”。

- 局部编辑

局部编辑可用自然语言指明区域，或使用用户已标注的参考图。使用 `<point>x y</point>`、`<bbox>x1 y1 x2 y2</bbox>` 时，坐标须为 0～999 的归一化整数，框从左上到右下且面积非零；先核对实际区域，不编造坐标。此能力不提供独立 mask 参数，也不保证区域外像素完全不变；交付前仍需核验。

#### 生成步骤

以下步骤在用户需要图生图且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。以下示例为单图编辑；多图融合时按顺序扩展外层 `assets` 数组，在最终提示词中说明每张参考图的用途。局部编辑使用同一结构，将已核实的区域和保留要求写入提示词。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "image-to-image", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "把图片背景改为草地，保留熊猫外观", // 流程记录：用户原始提示词，不提交给供应商
     "assets": [ // 必需：本方案使用的素材，按输入顺序排列，由脚本解析，不直接提交给供应商
       {
         "id": "panda", // 必需：任务内唯一标识，供供应商引用；不是供应商素材 ID
         "kind": "image", // 必需：image、video 或 audio；本能力仅接受 image
         "source": "https://example.com/panda.jpg", // 必需：执行前替换为实际 HTTPS URL 或本地绝对路径
         "purpose": "待编辑的熊猫图片，保留熊猫外观，只修改背景" // 必需：素材用途，只在这里记录一次
       }
     ],
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录，解析外层 assets 并填充素材字段后提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用 Pro 时替换为对应 ID
       "prompt": "将图片1的背景替换为草地，保留熊猫外观和姿态。", // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
       "image": [], // 由 Python 根据外层 assets 按顺序填充；此处留空数组或省略，不手工填写素材
       "size": "1K", // 必需：1K、1.5K、2K，或符合像素及比例限制的 WxH；用户未指定时默认最小尺寸
       "output_format": "png", // 固定：PNG
       "response_format": "url", // 固定：返回 URL
       "watermark": false, // 固定：不加平台水印
       "background": "opaque", // 固定：不启用透明背景
       "layer_decomposition": false // 固定：图生图不启用图层拆分；optimize_prompt_options 固定省略
     }
   }
   ```

2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态，如果失败则提示用户，如果成功则继续交付。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终媒体交付到启动本技能时所在的当前项目目录，图层拆分同时交付位置元数据，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。

图生图核验时，检查修改区域、产品、身份、文字及保留内容；多图融合还须检查各参考图的用途、主体关系和顺序是否符合确认要求。

### 图层拆分（`operation=decompose-layers`）

#### 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 必需 | 参考模型列表中的尺寸约束；用户未指定时默认最小尺寸；已指定时按用户要求 |
| `assets` | 必需 | 待拆分图片 1 张。提供本地绝对路径或 HTTPS URL。 |

- 素材要求

支持 JPEG、PNG。图片不超过 30 MiB，总像素为 262144～3600 万，宽高比为 1/16～16。素材来源须为本地绝对路径或可访问的 HTTPS URL，按下方示例填写外层 `assets`。

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。

图层拆分提示词须结合实际参考图，明确需要拆分的对象；未指定具体对象时，在提示词中表达拆分主要元素的要求。

- 图层拆分

输出尺寸支持 `1K`、`1.5K`、`2K`、`auto`，不支持准确 WxH。

可用自然语言指定拆分对象，或在输入图上标记辅助定位；需要精确指定区域时，使用 `<bbox>x1 y1 x2 y2</bbox>`。坐标须为 0～999 的归一化整数，框从左上到右下且面积非零；先核对实际区域，不编造坐标。依据：[官方教程“图层拆分 → 提示词输入方式”](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)。

一次请求返回 1 张底图和最多 16 张带透明通道的 PNG 图层，实际数量由模型决定。

#### 生成步骤

以下步骤在用户需要图层拆分且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "decompose-layers", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "拆出图片中的人物和标题文字", // 流程记录：用户原始提示词，不提交给供应商
     "assets": [ // 必需：本方案使用的素材，由脚本解析，不直接提交给供应商
       {
         "id": "layer-source", // 必需：任务内唯一标识，供供应商引用；不是供应商素材 ID
         "kind": "image", // 必需：image、video 或 audio；本能力仅接受 image
         "source": "/absolute/path/poster.png", // 必需：执行前替换为实际 HTTPS URL 或本地绝对路径
         "purpose": "待拆分的海报，提取人物与标题文字" // 必需：素材用途，只在这里记录一次
       }
     ],
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录，解析外层 assets 并填充素材字段后提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用 Pro 时替换为对应 ID
       "prompt": "将图片1中的人物和标题文字分别拆分为独立图层。", // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
       "image": [], // 由 Python 根据外层 assets 按顺序填充；此处留空数组或省略，不手工填写素材
       "size": "1K", // 必需：1K、1.5K、2K 或 auto；用户未指定时默认最小尺寸
       "output_format": "png", // 固定：PNG
       "response_format": "url", // 固定：返回 URL
       "watermark": false, // 固定：不加平台水印
       "background": "opaque", // 固定：底图不启用透明背景，前景图层仍带透明通道
       "layer_decomposition": true // 固定：图层拆分启用；optimize_prompt_options 固定省略
     }
   }
   ```

2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态，如果失败则提示用户，如果成功则继续交付。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终媒体交付到启动本技能时所在的当前项目目录，图层拆分同时交付位置元数据，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。

### 文生视频（`operation=text-to-video`）

#### 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `ratio` | 必需 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`；默认 `16:9` |
| `duration` | 必需 | 2.5 支持整数 4～30 秒或 `-1`；2.0 系列支持整数 4～15 秒或 `-1`；默认 4 秒；`-1` 由模型选择时长 |
| `resolution` | 必需 | 参考模型列表中的分辨率约束；用户未指定时默认 `480p`；已指定时按用户要求 |
| `generate_audio` | 必需 | 是否生成音频；默认 `false` |

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前视频能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化。

文生视频提示词须明确主体、动作、场景、事件顺序、运镜及用户要求的声音，不使用参考素材。比例、分辨率、总时长和声音开关通过接口参数落实，不追加到提示词。

#### 生成步骤

以下步骤在用户需要文生视频且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "text-to-video", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "熊猫向镜头挥手", // 流程记录：用户原始提示词，不提交给供应商
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录后原样提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "doubao-seedance-2-5-260628", // 必需：准确模型 ID；使用 2.0 系列时替换为对应 ID
       "content": [ // 必需：仅填写文本项；文生视频不提供素材
         {
           "type": "text", // 固定：文本提示词
           "text": "熊猫向镜头挥手" // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
         }
       ],
       "resolution": "480p", // 必需：所选模型支持的分辨率；用户未指定时默认 480p
       "ratio": "16:9", // 必需：所选模型支持的比例；用户未指定时默认 16:9
       "duration": 4, // 必需：2.5 为整数 4～30 秒或 -1，2.0 系列为整数 4～15 秒或 -1；默认 4 秒
       "generate_audio": false, // 必需：是否生成视频，默认无声
       "tools": [{"type":"web_search"}], // 固定：开启联网搜索
       "watermark": false, // 固定：不加平台水印
       "return_last_frame": false, // 固定：不返回末帧
       "service_tier": "default", // 固定：在线普通生成
       "output_format": "mp4" // 固定：MP4；2.0 系列固定输出 MP4，省略此字段
     }
   }
   ```

2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态；`queued`、`running` 表示尚未完成，继续查询同一任务，不重新提交。如果失败则提示用户，如果成功则继续交付。提交结果未知时按脚本操作手册的失败处理规则核对原任务。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终视频交付到启动本技能时所在的当前项目目录，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。

视频核验时，检查实测分辨率、时长、音轨及画面、对白、音效、事件顺序是否符合确认要求。API 返回的整数时长可能与文件实测时长不同，以文件实测为准。

### 图生视频（`operation=image-to-video`）

#### 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `assets` | 必需 | 首帧 1 张、首尾帧按顺序 2 张。按确认顺序提供本地绝对路径或 HTTPS URL，可混用。 |
| `duration` | 必需 | 2.5 支持整数 4～30 秒或 `-1`；2.0 系列支持整数 4～15 秒或 `-1`；默认 4 秒；`-1` 由模型选择时长 |
| `resolution` | 必需 | 参考模型列表中的分辨率约束；用户未指定时默认 `480p`；已指定时按用户要求 |
| `generate_audio` | 必需 | 是否生成音频；默认 `false` |

- 素材要求

支持 JPEG、PNG、WebP、BMP、TIFF、GIF、HEIC、HEIF。每张图片小于 30 MiB，宽高均为 300～6000 px，宽高比为 0.4～2.5；含 Base64 的完整请求不超过 64 MiB。素材来源须为本地绝对路径或可访问的 HTTPS URL，按下方示例填写外层 `assets`。

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前视频能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化。

图生视频提示词须结合实际首尾帧，明确起始状态、结束状态、中间动作及运镜；不将首尾帧改为人物、产品或风格参考。比例、分辨率、总时长和声音开关通过接口参数落实，不追加到提示词。

#### 生成步骤

以下步骤在用户需要图生视频且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。以下示例为首尾帧；首帧时外层 `assets` 只保留首图。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "image-to-video", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "熊猫向镜头挥手", // 流程记录：用户原始提示词，不提交给供应商
     "assets": [ // 必需：本方案使用的素材，按首帧、尾帧顺序排列，由脚本解析，不直接提交给供应商
       {
         "id": "first", // 必需：任务内唯一标识，供供应商引用；不是供应商素材 ID
         "kind": "image", // 必需：image、video 或 audio；本能力仅接受 image
         "source": "/absolute/path/first.png", // 必需：执行前替换为实际 HTTPS URL 或本地绝对路径
         "purpose": "视频首帧" // 必需：素材用途，只在这里记录一次
       },
       {
         "id": "last", // 必需：任务内唯一标识，供供应商引用；不是供应商素材 ID
         "kind": "image", // 必需：image、video 或 audio；本能力仅接受 image
         "source": "/absolute/path/last.png", // 必需：执行前替换为实际 HTTPS URL 或本地绝对路径
         "purpose": "视频尾帧" // 必需：素材用途，只在这里记录一次
       }
     ],
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录，解析外层 assets 并填充带角色的图片项后提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "doubao-seedance-2-5-260628", // 必需：准确模型 ID；使用 2.0 系列时替换为对应 ID
       "content": [ // 必需：仅填写文本项；图片项由 Python 根据外层 assets 按顺序添加
         {
           "type": "text", // 固定：文本提示词
           "text": "熊猫向镜头挥手" // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
         }
       ],
       "resolution": "480p", // 必需：所选模型支持的分辨率；用户未指定时默认 480p
       "ratio": "adaptive", // 固定：adaptive
       "duration": 4, // 必需：2.5 为整数 4～30 秒或 -1，2.0 系列为整数 4～15 秒或 -1；默认 4 秒
       "tools": [{"type":"web_search"}], // 默认：开启联网搜索；用户明确要求关闭时设为 []
       "generate_audio": false, // 必需：默认无声；用户要求台词、旁白、音乐或音效时设为 true
       "watermark": false, // 固定：不加平台水印
       "return_last_frame": false, // 固定：不返回末帧
       "service_tier": "default", // 固定：在线普通生成
       "output_format": "mp4" // 固定：MP4；2.0 系列固定输出 MP4，省略此字段
     }
   }
   ```

2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态；`queued`、`running` 表示尚未完成，继续查询同一任务，不重新提交。如果失败则提示用户，如果成功则继续交付。提交结果未知时按脚本操作手册的失败处理规则核对原任务。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终视频交付到启动本技能时所在的当前项目目录，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。

开启联网搜索时，通过查询结果的 `usage.tool_usage.web_search` 核对实际搜索次数；配置工具不代表一定执行了搜索。

视频核验时，检查实测分辨率、时长、音轨及画面、对白、音效、首尾状态是否符合确认要求。API 返回的整数时长可能与文件实测时长不同，以文件实测为准。



## 官方来源

- [Seedream Pro/Flash 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh) — 模型能力与使用说明。
- [交互式图片编辑](https://docs.volcengine.com/docs/ark/seedream-5-0-pro-editing-guide?lang=zh) — 局部编辑与区域表达。
- [图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh) — 维护脚本时核对参数及响应。
- [模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh) — 模型 ID 与规格。
- [模型价格](https://docs.volcengine.com/docs/ark/model-pricing?lang=zh) — 计费规则与官方单价。
- [Volcengine 创建视频任务](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)
- [Volcengine Seedance 2.5](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)
