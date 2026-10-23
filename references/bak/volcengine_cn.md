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

根据主流程确定的能力和模式，检查支持模型并读取对应章节。

| 能力 | 支持模式 | 支持模型 | 脚本实现 | 详细说明 |
|---|---|---|---|---|
| 文生图 | — | Seedream 5.0 Pro、Flash | 已实现 | [文生图](#文生图operationtext-to-image) |
| 图生图 | 单图编辑、多图融合、局部编辑 | Seedream 5.0 Pro、Flash | 已实现 | [图生图](#图生图operationimage-to-image) |
| 图层拆分 | — | Seedream 5.0 Pro、Flash | 已实现 | [图层拆分](#图层拆分operationdecompose-layers) |
| 文生视频 | — | Seedance 2.5、2.0、2.0 Fast、2.0 Mini | 已实现 | [文生视频](#文生视频operationtext-to-video) |
| 图生视频 | 首帧、首尾帧 | 同上四款 Seedance | 已实现 | [图生视频](#图生视频operationimage-to-video) |
| 参考生视频 | 参考生成、视频编辑 | 同上四款 Seedance；纯音频参考仅 2.5 | 已实现 | [参考生视频](#参考生视频operationreference-to-video) |
| 视频延长 | 向前延长、向后延长 | 同上四款 Seedance | 已实现 | [视频延长](#视频延长operationextend-video) |

同一能力下，不同模式或模型的素材要求、参数和限制，见对应能力的调用要求。

## 预估成本

根据能力和用户要求构建成本参数 JSON；Python 脚本读取供应商单价描述文件，检查素材并解析计费所需的数据，最后按本节公式计算。不要让大模型填写图片数量、素材实测尺寸、素材实测时长、单价或最终金额。

### 能力与成本参数

| 能力 | JSON 必填任务参数 | 输入素材 |
|---|---|---|
| 文生图 | `size` | 无 |
| 图生图 | `size` | 单图编辑 1 张；多图融合 2～10 张；局部编辑 1～10 张图片 |
| 图层拆分 | `size`，支持 `auto` | 1 张图片 |
| 文生视频 | `resolution`、`ratio`、`duration` | 无 |
| 图生视频 | `resolution`、`ratio`、`duration` | 首帧 1 张；首尾帧按顺序提供 2 张图片 |
| 参考生视频 | `resolution`、`ratio`、`duration` | 参考生成必须有素材；编辑必须有视频；2.0 不支持纯音频参考 |
| 视频延长 | `resolution`、`ratio`、`duration` | 必须有视频；方向不改变计费公式 |

公共字段为 `provider="volcengine"`、`model`（模型别名或准确 ID）和 `operation`。`assets` 为数组，每项包含素材标识 `id`、`kind`（image/video/audio）及 `source`（本地绝对路径或可访问 HTTPS URL）；无素材时可省略或传空数组。有素材时 Python 使用 ffprobe 读取尺寸和时长，并检查素材类型、数量及音视频时长是否符合该模式。`asset://` 不能直接探测，成本计算需提供对应原始文件或 HTTPS URL。

`estimate_context` 仅在下方列出的条件需要补充信息时使用；它是计费依据，不提交给生成 API。Python 自行读取 `models/volcengine-pricing.json`，不接受单价、价格文件路径或大模型计算出的媒体元数据。

### 文生图、图生图计费

#### 计算公式

```text
额外输入图片数量 = max(输入图片数量 − 1, 0)
输出费用 = 一张输出图片对应像素档位的单价
输入费用 = 额外输入图片数量 × 模型的额外输入图片单价
预计费用 = 输出费用 + 输入费用
```

#### 返回的数据对象

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

#### 返回的数据对象

根据前两步的信息组织如下 JSON 内容，作为 estimate-cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "volcengine", // 必需：供应商；Python 自行读取 models/volcengine-pricing.json，不传单价或文件路径
  "model": "seedream-5.0-flash", // 必需：模型别名或准确 ID；Python 读取该模型的 layer 费率
  "operation": "decompose-layers", // 必需：图层拆分，不提供 mode
  "size": "auto", // 必需：auto 或模型支持的尺寸档位；不能据此确定各张未来图层的尺寸
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

#### 返回的数据对象

根据前两步的信息组织如下 JSON 内容，作为 estimate-cost 的输入；传给脚本前去除注释。

```jsonc
{
  "provider": "volcengine", // 必需：供应商；Python 自行读取 models/volcengine-pricing.json
  "model": "seedance-2.5", // 必需：模型别名或准确 ID；Python 根据模型、分辨率及有无视频输入选择单价
  "operation": "image-to-video", // 必需：text-to-video 文生视频、image-to-video 图生视频、reference-to-video 参考生视频、extend-video 视频延长
  "mode": "first-frame", // 当前视频脚本要求：图生视频 first-frame/first-last-frame；参考生视频 reference/edit；延长 before/after；文生视频不提供
  "resolution": "480p", // 必需：所选模型支持的分辨率；与模型和比例共同确定输出宽高，不直接复用输入像素
  "ratio": "adaptive", // 必需：固定比例按官方像素表查宽高；2.5 首帧/首尾帧、编辑、延长必须为 adaptive
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

## 能力操作说明

### 文生图（`operation=text-to-image`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 必需 | 参考模型列表中模型的尺寸档位约束，默认最小尺寸 |

- 提示词优化

使用 `sd25-pe` 优化提示词；用于图片任务时，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，保留原始提示词。

#### 运行步骤

以下步骤在用户需要问生图且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "text-to-image", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "生成一张正方形熊猫图片", // 流程记录：用户原始提示词，不提交给供应商
     "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交
       "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用 Pro 时替换为对应 ID
       "prompt": "一只熊猫坐在草坡上，柔和自然光，写实摄影，不添加文字。构图比例偏好：1:1。", // 必需：最终确认的提示词，脚本不再改写
       "size": "1K", // 可选：1K、1.5K、2K，或符合像素及比例限制的 WxH；本 skill 默认最小尺寸
       "output_format": "png", // 可选：png、jpeg；本 skill 默认 png
       "response_format": "url", // 可选：url、b64_json；默认 url
       "watermark": false, // 可选：是否添加平台水印；本 skill 默认 false
       "background": "opaque", // 可选：文生图使用 opaque，不启用 transparent
       "optimize_prompt_options": { // 可选：供应商服务端提示词优化，与本地 sd25-pe 优化独立
         "mode": "standard" // 对象存在时填写：Pro 支持 standard、fast；Flash 仅支持 standard
       },
       "layer_decomposition": false // 可选：文生图保持 false；true 应走图层拆分能力
     }
   }
   ```
2. **调用脚本提交生成：** 
 - 将第一步构建的 JSON 通过标准输入传给如下脚本。输入及脚本输出结果保存到 `$WORK/submit-xxx.json`，并返回该文件的绝对路径。将返回路径记为 `$SUBMISSION`，供后续下载使用。

   ```bash
   python3 "scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
   <第一步构建的完整 JSON 对象，不含注释>
   JSON
   ```

- 返回结果示例：

   ```jsonc
   {
     "submission": "/tmp/richmedia-20261022153000/submit-001.json" // 本次提交记录的绝对路径；将此字段值记为 $SUBMISSION
   }
   ```

3. **判断生成结果：** 读取本次提交记录的执行状态。图片接口同步返回结果。
 - `succeeded` 时继续下载；
 - `partial_failed` 时仅保存有效结果，并说明失败项
 - 其他失败或提交结果未知的情况，按下方“成功、失败与重试”处理，不重复提交。

4. **调用脚本下载或保存图片：** 将本次提交记录路径传给 `download`，脚本根据响应下载图片或解码保存，并返回文件清单。完成后进入主流程的结果核验与交付步骤。

   ```bash
   python3 "scripts/media.py" download --submission "$SUBMISSION"
   ```

#### 成功、失败与重试

读取 `$SUBMISSION` 指向的提交记录，按以下条件判断：

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 生成成功 | `execution.state="succeeded"`，且 `response.data` 中包含可用图片 URL 或 Base64 数据 | 调用 `download` 保存图片；文生图为同步返回，不需要轮询生成进度。 |
| 部分生成失败 | `execution.state="partial_failed"`，`response.data` 中有条目包含 `error` | 下载其余有效图片，说明失败项；不能认定任务全部成功。 |
| 请求被拒绝 | `execution.state="rejected"` | 查看 `execution.error` 和供应商返回的错误，修正参数、权限或账户问题。需要再次提交时，更新任务确认单并取得用户确认。 |
| 提交结果未知 | `execution.state` 为 `submitting` 或 `submission_unknown`，例如请求超时、中断或响应无法解析 | 保留提交记录，核对供应商控制台或请求记录，确认是否已生成或计费；不自动再次调用 `submit`。图片接口没有可供本脚本轮询的任务 ID。 |
| 下载失败 | `download` 报错，或 `execution.download_complete` 不为 `true` | 排查后对同一个 `$SUBMISSION` 再次调用 `download`，不重新生成。图片 URL 失效时，优先使用已保存文件或供应商可提供的恢复方式。 |
| 图片不符合要求 | 文件已保存，但主体、构图、文字、尺寸等不符合用户确认的要求 | 说明差异并提出修改方案；需要重新生成时，重新估算费用、更新确认单并取得用户确认。 |

只有 `execution.download_complete=true`、`result.files` 清单与实际文件一致，且图片通过已确认要求的内容核验，才算任务完成。无法核验的内容需明确说明。若后续将含人脸图片交给 Seedance，交付时同时保留上述人像来源证据，最终媒体保持原始字节。

### 图生图（`operation=image-to-image`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 确认前确定 | 默认 `1K`；支持 `1K/1.5K/2K` 或准确 `WxH`，总像素 921600～4624220、比例 1/16～16。 |

- 提示词优化

使用 `sd25-pe` 优化提示词；用于图片任务时，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，保留原始提示词。

#### 运行步骤

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

单图编辑示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "image-to-image", // 必需：能力，供脚本选择接口及结果处理方式
  "original_prompt": "把图片1的背景改为浅灰色，保留产品形状、颜色、标志和主体位置。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "prompt": "把图片1的背景改为浅灰色，保留产品形状、颜色、标志和主体位置。构图比例偏好：1:1。", // 必需：最终确认的完整提示词，比例要求直接写在提示词中
    "image": [ // 必需：输入图片 URL；单图编辑／拆分 1 张，多图融合 2～10 张，局部编辑 1～10 张
      "https://your-approved-storage.example/product.png"
    ],
    "size": "1K", // 可选：1K、1.5K、2K 或符合像素及比例限制的 WxH；本 skill 默认最小尺寸
    "output_format": "png", // 可选：png、jpeg；本 skill 默认 png，透明图层使用 PNG
    "response_format": "url", // 可选：url、b64_json；默认 url，由 download 下载或解码保存
    "watermark": false, // 可选：是否添加平台水印；本 skill 图片默认 false
    "background": "opaque", // 可选：默认 opaque；transparent 仅适用于满足 Alpha 要求的单图编辑
    "optimize_prompt_options": { // 可选：供应商服务端提示词优化，与本地提示词优化 skill 独立
      "mode": "standard" // 对象存在时填写：Pro 支持 standard、fast；Flash 仅 standard
    },
    "layer_decomposition": false // 可选：普通图片保持 false；true 应走图层拆分能力
  }
}
```

多图融合示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "image-to-image", // 必需：能力，供脚本选择接口及结果处理方式
  "original_prompt": "保留图片1的产品形状、颜色和标志，将产品自然放入图片2的室内背景，统一光线与透视。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedream-5-0-pro-260628", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "prompt": "保留图片1的产品形状、颜色和标志，将产品自然放入图片2的室内背景，统一光线与透视。构图比例偏好：1:1。", // 必需：最终确认的完整提示词，比例要求直接写在提示词中
    "image": [ // 必需：输入图片 URL；单图编辑／拆分 1 张，多图融合 2～10 张，局部编辑 1～10 张
      "https://your-approved-storage.example/product.png",
      "https://your-approved-storage.example/background.png"
    ],
    "size": "1K", // 可选：1K、1.5K、2K 或符合像素及比例限制的 WxH；本 skill 默认最小尺寸
    "output_format": "png", // 可选：png、jpeg；本 skill 默认 png，透明图层使用 PNG
    "response_format": "url", // 可选：url、b64_json；默认 url，由 download 下载或解码保存
    "watermark": false, // 可选：是否添加平台水印；本 skill 图片默认 false
    "background": "opaque", // 可选：默认 opaque；transparent 仅适用于满足 Alpha 要求的单图编辑
    "optimize_prompt_options": { // 可选：供应商服务端提示词优化，与本地提示词优化 skill 独立
      "mode": "standard" // 对象存在时填写：Pro 支持 standard、fast；Flash 仅 standard
    },
    "layer_decomposition": false // 可选：普通图片保持 false；true 应走图层拆分能力
  }
}
```

局部编辑示例：

框坐标仅演示标签语法；实际运行前必须替换为核验过的编辑区域。使用标注图时按真实顺序加入素材，并在提示词说明其用途。

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "image-to-image", // 必需：能力，供脚本选择接口及结果处理方式
  "original_prompt": "把图片1中 <bbox>100 100 400 400</bbox> 框内的背景改为浅灰色，保留框外内容和产品。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "prompt": "把图片1中 <bbox>100 100 400 400</bbox> 框内的背景改为浅灰色，保留框外内容和产品。构图比例偏好：1:1。", // 必需：最终确认的完整提示词，比例要求直接写在提示词中
    "image": [ // 必需：输入图片 URL；单图编辑／拆分 1 张，多图融合 2～10 张，局部编辑 1～10 张
      "https://your-approved-storage.example/product.png"
    ],
    "size": "1K", // 可选：1K、1.5K、2K 或符合像素及比例限制的 WxH；本 skill 默认最小尺寸
    "output_format": "png", // 可选：png、jpeg；本 skill 默认 png，透明图层使用 PNG
    "response_format": "url", // 可选：url、b64_json；默认 url，由 download 下载或解码保存
    "watermark": false, // 可选：是否添加平台水印；本 skill 图片默认 false
    "background": "opaque", // 可选：默认 opaque；transparent 仅适用于满足 Alpha 要求的单图编辑
    "optimize_prompt_options": { // 可选：供应商服务端提示词优化，与本地提示词优化 skill 独立
      "mode": "standard" // 对象存在时填写：Pro 支持 standard、fast；Flash 仅 standard
    },
    "layer_decomposition": false // 可选：普通图片保持 false；true 应走图层拆分能力
  }
}
```

2. **调用脚本提交生成：** 
 - 将第一步构建的 JSON 通过标准输入传给如下脚本。输入及脚本输出结果保存到 `$WORK/submit-xxx.json`，并返回该文件的绝对路径。将返回路径记为 `$SUBMISSION`，供后续下载使用。

  ```bash
  python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
  <本次确认的完整任务 JSON，不含注释>
  JSON
  ```

- 返回结果示例：

   ```jsonc
   {
     "submission": "/tmp/richmedia-20261022153000/submit-001.json" // 本次提交记录的绝对路径；将此字段值记为 $SUBMISSION
   }
   ```

3. **判断生成结果：** 读取本次提交记录的执行状态。图片接口同步返回结果。
 - `succeeded` 时继续下载；
 - `partial_failed` 时仅保存有效结果，并说明失败项
 - 其他失败或提交结果未知的情况，按下方“成功、失败与重试”处理，不重复提交。

4. **调用脚本下载或保存图片：** 将本次提交记录路径传给 `download`，脚本根据响应下载图片或解码保存，并返回文件清单。完成后进入主流程的结果核验与交付步骤。

   ```bash
   python3 "scripts/media.py" download --submission "$SUBMISSION"
   ```

#### 成功、失败与重试

读取 `$SUBMISSION` 指向的提交记录，按以下条件判断：

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 生成成功 | `execution.state="succeeded"`，且 `response.data` 中包含可用图片 URL 或 Base64 数据 | 调用 `download` 保存图片；文生图为同步返回，不需要轮询生成进度。 |
| 部分生成失败 | `execution.state="partial_failed"`，`response.data` 中有条目包含 `error` | 下载其余有效图片，说明失败项；不能认定任务全部成功。 |
| 请求被拒绝 | `execution.state="rejected"` | 查看 `execution.error` 和供应商返回的错误，修正参数、权限或账户问题。需要再次提交时，更新任务确认单并取得用户确认。 |
| 提交结果未知 | `execution.state` 为 `submitting` 或 `submission_unknown`，例如请求超时、中断或响应无法解析 | 保留提交记录，核对供应商控制台或请求记录，确认是否已生成或计费；不自动再次调用 `submit`。图片接口没有可供本脚本轮询的任务 ID。 |
| 下载失败 | `download` 报错，或 `execution.download_complete` 不为 `true` | 排查后对同一个 `$SUBMISSION` 再次调用 `download`，不重新生成。图片 URL 失效时，优先使用已保存文件或供应商可提供的恢复方式。 |
| 图片不符合要求 | 文件已保存，但主体、构图、文字、尺寸等不符合用户确认的要求 | 说明差异并提出修改方案；需要重新生成时，重新估算费用、更新确认单并取得用户确认。 |

只有 `execution.download_complete=true`、`result.files` 清单与实际文件一致，且图片通过已确认要求的内容核验，才算任务完成。无法核验的内容需明确说明。若后续将含人脸图片交给 Seedance，交付时同时保留上述人像来源证据，最终媒体保持原始字节。

### 图层拆分（`operation=decompose-layers`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `provider / payload.model / operation` | 必需 | `volcengine`；Seedream Pro/Flash 准确模型 ID；`decompose-layers`。不提供顶层 `mode`。 |
| `payload.image` | 必需 | 只能提供 1 张待拆分图片的 HTTPS URL，不接受 `asset://`。 |
| `payload.size` | 确认前确定 | 默认 `auto`，可选 `auto/1K/1.5K/2K`；不接受准确 `WxH`。 |
| `original_prompt / payload.prompt` | 原文保留；提示词可选 | 不提供 `prompt` 时自动识别主要元素；也可指定要拆出的主体、文字或装饰。 |
| `payload.output_format / response_format` | 可选 | 默认 `png / url`；建议保留 PNG；图层为带透明通道的 PNG，返回可选 `url/b64_json`。 |
| `payload.watermark / background` | 可选 | 默认 `false / opaque`；不要用 `background=transparent` 启用拆分，payload.layer_decomposition 必须与 operation 一致。 |
| `payload.optimize_prompt_options` | 可选 | 默认 standard；Pro 还可选 fast，Flash 仅 standard。 |

- 提示词优化

使用 `sd25-pe` 优化提示词；用于图片任务时，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，保留原始提示词。

#### 运行步骤

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "decompose-layers", // 必需：能力，供脚本选择接口及结果处理方式
  "original_prompt": "将产品、文字和背景拆成可独立编辑的图层。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedream-5-0-flash-260915", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "prompt": "将产品、文字和背景拆成可独立编辑的图层。", // 可选：指定拆分元素；省略时自动识别
    "image": [ // 必需：输入图片 URL；单图编辑／拆分 1 张，多图融合 2～10 张，局部编辑 1～10 张
      "https://your-approved-storage.example/poster.png"
    ],
    "size": "auto", // 可选：auto、1K、1.5K、2K；拆分默认 auto，不接受准确 WxH
    "output_format": "png", // 可选：png、jpeg；本 skill 默认 png，透明图层使用 PNG
    "response_format": "url", // 可选：url、b64_json；默认 url，由 download 下载或解码保存
    "watermark": false, // 可选：是否添加平台水印；本 skill 图片默认 false
    "background": "opaque", // 可选：默认 opaque；transparent 仅适用于满足 Alpha 要求的单图编辑
    "optimize_prompt_options": { // 可选：供应商服务端提示词优化，与本地提示词优化 skill 独立
      "mode": "standard" // 对象存在时填写：Pro 支持 standard、fast；Flash 仅 standard
    },
    "layer_decomposition": true // 必需：图层拆分使用 true
  }
}
```

2. **调用脚本提交生成：** 
 - 将第一步构建的 JSON 通过标准输入传给如下脚本。输入及脚本输出结果保存到 `$WORK/submit-xxx.json`，并返回该文件的绝对路径。将返回路径记为 `$SUBMISSION`，供后续下载使用。

   ```bash
   python3 "scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
   <第一步构建的完整 JSON 对象，不含注释>
   JSON
   ```

- 返回结果示例：

   ```jsonc
   {
     "submission": "/tmp/richmedia-20261022153000/submit-001.json" // 本次提交记录的绝对路径；将此字段值记为 $SUBMISSION
   }
   ```

3. **判断生成结果：** 读取本次提交记录的执行状态。图片接口同步返回结果。
 - `succeeded` 时继续下载；
 - `partial_failed` 时仅保存有效结果，并说明失败项
 - 其他失败或提交结果未知的情况，按下方“成功、失败与重试”处理，不重复提交。

4. **调用脚本下载或保存图片：** 将本次提交记录路径传给 `download`，脚本根据响应下载图片或解码保存，并返回文件清单。完成后进入主流程的结果核验与交付步骤。

   ```bash
   python3 "scripts/media.py" download --submission "$SUBMISSION"
   ```

#### 成功、失败与重试

读取 `$SUBMISSION` 指向的提交记录，按以下条件判断：

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 生成成功 | `execution.state="succeeded"`，且 `response.data` 中包含可用图片 URL 或 Base64 数据 | 调用 `download` 保存图片；文生图为同步返回，不需要轮询生成进度。 |
| 部分生成失败 | `execution.state="partial_failed"`，`response.data` 中有条目包含 `error` | 下载其余有效图片，说明失败项；不能认定任务全部成功。 |
| 请求被拒绝 | `execution.state="rejected"` | 查看 `execution.error` 和供应商返回的错误，修正参数、权限或账户问题。需要再次提交时，更新任务确认单并取得用户确认。 |
| 提交结果未知 | `execution.state` 为 `submitting` 或 `submission_unknown`，例如请求超时、中断或响应无法解析 | 保留提交记录，核对供应商控制台或请求记录，确认是否已生成或计费；不自动再次调用 `submit`。图片接口没有可供本脚本轮询的任务 ID。 |
| 下载失败 | `download` 报错，或 `execution.download_complete` 不为 `true` | 排查后对同一个 `$SUBMISSION` 再次调用 `download`，不重新生成。图片 URL 失效时，优先使用已保存文件或供应商可提供的恢复方式。 |
| 图片不符合要求 | 文件已保存，但主体、构图、文字、尺寸等不符合用户确认的要求 | 说明差异并提出修改方案；需要重新生成时，重新估算费用、更新确认单并取得用户确认。 |

只有 `execution.download_complete=true`、`result.files` 清单与实际文件一致，且图片通过已确认要求的内容核验，才算任务完成。无法核验的内容需明确说明。若后续将含人脸图片交给 Seedance，交付时同时保留上述人像来源证据，最终媒体保持原始字节。

### 文生视频（`operation=text-to-video`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `provider / payload.model / operation` | 必需 | `volcengine`；四款 Seedance 准确模型 ID；`text-to-video`。 |
| `original_prompt / payload.content[].text` | 保留原文；最终提示词必需 | 描述主体、动作、镜头、事件顺序和需要的声音；content 只包含文本项，不包含媒体项。 |
| `payload.resolution` | 本 skill 必需显式提供 | 默认 `480p`；2.5 支持 480p/720p/1080p；2.0 另支持 4k；Fast/Mini 仅 480p/720p。 |
| `payload.duration` | 本 skill 必需显式提供 | 默认 4 秒；整数 4～30（2.5）或 4～15（2.0 系列）；`-1` 为自动时长，需估算区间。 |
| `payload.ratio` | 本 skill 必需显式提供 | 默认 `16:9`；可选 16:9、4:3、1:1、3:4、9:16、21:9、adaptive；自适应尺寸无法确定时费用可能未知。 |
| `payload.generate_audio` | 本 skill 必需显式提供 | 默认 false；需要对白、音乐或音效时明确选择并写入确认单。 |
| `payload.output_format` | 可选 | 默认 mp4；2.5 可选 mp4/mov；2.0 系列固定 mp4，不发送此字段。 |
| `payload.watermark / return_last_frame` | watermark 显式提供；末帧可选 | 视频默认 true / false；请求末帧后必须检查相应响应与文件。 |
| `optimizer` | 2.5 必需 | 实际应用 sd25-pe 后记录 `{"skill":"sd25-pe","status":"applied"}`；2.0 系列不要求该记录。 |

当前脚本还允许 `payload.execution_expires_after`（3600～259200 秒，默认 172800）、`priority`（0～9，默认 0）、`callback_url`（HTTPS 或 null）、`safety_identifier`（1～64 字符 ASCII 或 null）；不需要时省略字段，账户权限仍需单独确认。这些公共技术选项同样适用于下方三类视频能力。`payload.service_tier` 仅支持 default，不提供时不额外写入请求，不接受 seed、camera_fixed、frames、draft、搜索工具等未经适配的参数。

- 提示词优化

2.5 实际应用 sd25-pe 后才能填写 optimizer；2.0 系列使用对应官方指南，按镜头顺序表达事件，不承诺 2.5 式时间戳控制。不要因为选择了 4 秒就自行编造分秒脚本，也不要添加用户未要求的字幕或音轨。

- 人像检查

纯文本没有待检查的人像图片／视频，不适用输入人像信任检查；输出仍可能触发平台审核。若成片或尾帧将作为下一阶段输入，交付时保留原始字节、所属 Ark 账户、模型、任务 ID、生成时间与响应记录；下一阶段按[人像来源](#人像来源)重新核验，不预先保证受信。

#### 运行步骤

1. **构建任务 JSON：** 采用已确认的模型、时长、分辨率、比例和音频设置，无素材上传。示例使用 2.0；切换 2.5 时补充真实优化记录并重新核对规格与报价。

调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "text-to-video", // 必需：能力，供脚本选择接口及结果处理方式
  "original_prompt": "熊猫幼崽在绿色草坡上缓慢侧滚，最后趴下。低机位中景，镜头轻微跟随。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "熊猫幼崽在绿色草坡上缓慢侧滚，最后趴下。低机位中景，镜头轻微跟随。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "16:9", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": false, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

2. **提交一次生成请求：** 移除示例注释并替换实际值后，将任务 JSON 通过标准输入传给命令。命令会读取 `$WORK/volcengine/cost.json`，校验计费参数并保存 `$WORK/submit-NNN.json`。输出对象的 `submission` 字段就是本次记录的绝对路径，将其记为 `$SUBMISSION`。 费用上界未知时，先取得用户明确接受，再在命令中附加 `--accept-uncertain-cost`；没有明确接受时停止提交。

```bash
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<本次确认的完整任务 JSON，不含注释>
JSON
```

3. **查询生成状态：** `submit` 返回任务 ID 后，记录中的 `execution.state` 为 `queued`，尚未完成。对同一个 `$SUBMISSION` 查询；`queued/running` 时有界重复查询，`succeeded` 时检查最近一次成功查询响应的 `content.video_url`。查询失败只重试查询。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

4. **下载结果：** 仅在任务成功且含主视频 URL 后运行；`return_last_frame=true` 时还需核对末帧 URL 和下载文件。下载清单和文件保存在本次提交记录及 `$WORK/outputs/submit-NNN/` 中。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

5. **核对并交付：** 检查主体、动作、事件顺序、实际分辨率、时长、文件格式及约定音频，交付完整成片。无视频输入时按无视频费率估算；固定比例由脚本查官方像素映射，见[视频计费](#文生视频图生视频参考生视频视频延长计费)。

#### 成功、失败与重试

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 任务处理中 | `execution.state` 为 `queued/running` | 对同一记录继续 `status`，不再次 `submit`。 |
| 生成成功 | `execution.state="succeeded"`，最近一次成功查询的 `queries[].response.content.video_url` 非空 | 下载并核对主体、动作、事件顺序、输出规格和约定音频；请求末帧时同时核对末帧。 |
| 任务失败 | `failed/expired/cancelled`，或提交明确 `rejected` | 保留供应商错误与任务记录，修正问题；再次付费前更新方案、必要时重新估价并取得新确认。 |
| 提交结果未知 | `submitting/submission_unknown`，可能已有任务或计费 | 核对控制台；无任务 ID 时，仅在独立核实已有任务后使用 `attach-task`，不自动重发 POST。 |
| 查询或下载失败 | `status/download` 报错，或任务成功却缺少媒体 URL／所需文件 | 重试同一任务的查询或下载，核查响应与供应商恢复途径，不通过重新生成解决下载问题。 |
| 内容不符合要求 | 已下载但未满足核对主体、动作、事件顺序、输出规格和约定音频等要求 | 明确差异，重新准备与确认后才可再次付费。 |

完成还需 `execution.download_complete=true`、`result.files` 与实际文件一致，并通过本能力内容核验；无法检查画面或音频时说明观察范围。恢复命令和 URL 过期处理见[共用判断](#成功失败与重试的共用判断)。

### 图生视频（`operation=image-to-video`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `provider / payload.model / operation` | 必需 | `volcengine`；四款 Seedance 准确模型 ID；`image-to-video`。 |
| `mode` | 必需 | `first-frame` 首帧；`first-last-frame` 首尾帧。 |
| `original_prompt / payload.content[].text` | 保留原文；最终提示词必需 | 描述从首帧开始的动作；首尾帧模式描述两帧之间的变化，不混入另一套参考角色。 |
| `payload.content` | 必需 | 首帧只能 1 张图片，role=first_frame；首尾帧只能 2 张，依次为 first_frame、last_frame。 |
| `payload.content[]` | 媒体项必需 | 提供 type、对应 image_url/video_url/audio_url.url 及 role；实测素材信息由 cost.json 读取，不放进 API 请求体。 |
| `payload.resolution / duration` | 本 skill 必需显式提供 | 默认 480p / 4 秒；支持范围同文生视频；-1 为自动时长。 |
| `payload.ratio` | 本 skill 必需显式提供 | 2.5 强制 adaptive；2.0 系列允许文生视频所列表达，带素材时默认 adaptive。 |
| `payload.generate_audio / output_format / watermark / return_last_frame` | 音频、水印显式提供；其余可选 | 默认 false / mp4 / true / false；格式、其他技术选项同文生视频。 |
| `optimizer` | 2.5 必需 | 实际应用 sd25-pe 后记录 applied；2.0 系列可省略。 |

- 素材要求

每张图片宽高 300～6000 px、比例 0.4～2.5、小于 30 MB；先检查可解码格式及首尾帧是否符合确认的内容。本示例使用 HTTPS 图片 URL；已有 `asset://` 必须核实真实供应商及账户归属，不能复用 BytePlus 素材；本节原生提交要求 URL 与成本记录来源逐项一致，示例使用可探测的 HTTPS URL。完整请求不超过 64 MB。含人脸素材按下方“人像检查”执行，不擅自压缩或裁剪可信原图。

- 提示词优化

明确主体在首尾画面间的动作和镜头变化，保持指定身份、产品和事件顺序。首尾帧之间的过渡应可理解；不要把严格首尾帧与多模态参考素材混在同一任务。2.5 需实际应用 sd25-pe。

- 人像检查

在成本计算和任务确认前，逐张检查首帧及尾帧是否含真人人脸，不能只检查主要人物。含人脸时逐项核验[人像来源](#人像来源)的可用路径；走可信原始产物路径时核对同平台、同账户、模型与操作、生成时间及原始字节。来源不明、过期或被编辑过时先解决素材来源，不直接提交。确认后到实际提交前再次检查素材未变且仍在有效期内。

#### 运行步骤

1. **构建任务 JSON：** 按所选模式填写素材顺序和 role，检查已确认分辨率、时长及自适应比例的费用依据。以下以 2.0 演示；使用 2.5 必须保持 adaptive 并补真实 optimizer 记录。

首帧调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "image-to-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "first-frame", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "从图片1开始，产品缓慢旋转，镜头保持中景，保留产品形状、颜色和标志。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "从图片1开始，产品缓慢旋转，镜头保持中景，保留产品形状、颜色和标志。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "image_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "image_url": { // 必需：图片输入对象；对应 type=image_url
          "url": "https://your-approved-storage.example/first.png" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "first_frame" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "adaptive", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": false, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

首尾帧调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "image-to-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "first-last-frame", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "从图片1平稳过渡到图片2，主体自然完成转身，保留身份与服装。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "从图片1平稳过渡到图片2，主体自然完成转身，保留身份与服装。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "image_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "image_url": { // 必需：图片输入对象；对应 type=image_url
          "url": "https://your-approved-storage.example/first.png" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "first_frame" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      },
      {
        "type": "image_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "image_url": { // 必需：图片输入对象；对应 type=image_url
          "url": "https://your-approved-storage.example/last.png" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "last_frame" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "adaptive", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": false, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

2. **提交一次生成请求：** 移除示例注释并替换实际值后，将任务 JSON 通过标准输入传给命令。命令会读取 `$WORK/volcengine/cost.json`，校验计费参数并保存 `$WORK/submit-NNN.json`。输出对象的 `submission` 字段就是本次记录的绝对路径，将其记为 `$SUBMISSION`。 费用上界未知时，先取得用户明确接受，再在命令中附加 `--accept-uncertain-cost`；没有明确接受时停止提交。

```bash
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<本次确认的完整任务 JSON，不含注释>
JSON
```

3. **查询生成状态：** `submit` 返回任务 ID 后，记录中的 `execution.state` 为 `queued`，尚未完成。对同一个 `$SUBMISSION` 查询；`queued/running` 时有界重复查询，`succeeded` 时检查最近一次成功查询响应的 `content.video_url`。查询失败只重试查询。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

4. **下载结果：** 仅在任务成功且含主视频 URL 后运行；`return_last_frame=true` 时还需核对末帧 URL 和下载文件。下载清单和文件保存在本次提交记录及 `$WORK/outputs/submit-NNN/` 中。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

5. **核对并交付：** 检查开头是否对应首帧；首尾帧模式同时检查结尾及过渡。核对身份、产品细节、实际时长、分辨率和音频。图片不计入视频输入秒数，使用无输入视频费率；adaptive 报价按对应源图比例和输出分辨率推导，不直接套用源图像素。无法可靠推导时如实显示费用未知，见[视频计费](#文生视频图生视频参考生视频视频延长计费)。

#### 成功、失败与重试

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 任务处理中 | `execution.state` 为 `queued/running` | 对同一记录继续 `status`，不再次 `submit`。 |
| 生成成功 | `execution.state="succeeded"`，最近一次成功查询的 `queries[].response.content.video_url` 非空 | 下载并核对首帧、所需尾帧、过渡动作、身份及产品细节；请求末帧时同时核对末帧。 |
| 任务失败 | `failed/expired/cancelled`，或提交明确 `rejected` | 保留供应商错误与任务记录，修正问题；再次付费前更新方案、必要时重新估价并取得新确认。 |
| 提交结果未知 | `submitting/submission_unknown`，可能已有任务或计费 | 核对控制台；无任务 ID 时，仅在独立核实已有任务后使用 `attach-task`，不自动重发 POST。 |
| 查询或下载失败 | `status/download` 报错，或任务成功却缺少媒体 URL／所需文件 | 重试同一任务的查询或下载，核查响应与供应商恢复途径，不通过重新生成解决下载问题。 |
| 内容不符合要求 | 已下载但未满足核对首帧、所需尾帧、过渡动作、身份及产品细节等要求 | 明确差异，重新准备与确认后才可再次付费。 |

完成还需 `execution.download_complete=true`、`result.files` 与实际文件一致，并通过本能力内容核验；无法检查画面或音频时说明观察范围。恢复命令和 URL 过期处理见[共用判断](#成功失败与重试的共用判断)。

### 参考生视频（`operation=reference-to-video`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `provider / payload.model / operation` | 必需 | `volcengine`；四款 Seedance 准确模型 ID；`reference-to-video`。 |
| `mode` | 必需 | reference=借鉴素材生成新视频；edit=修改已有视频内容。 |
| `original_prompt / payload.content[].text` | 保留原文；最终提示词必需 | 参考生成逐项说明借鉴维度；编辑明确目标视频和替换、增加、删除等动作及保留项。 |
| `payload.content` | 必需 | reference 至少一份素材；edit 至少一个 reference_video；全部使用 reference_image/reference_video/reference_audio 角色。 |
| `payload.content[]` | 媒体项必需 | 提供 type、对应 image_url/video_url/audio_url.url 及 role；实测素材信息由 cost.json 读取，不放进 API 请求体。 |
| `payload.resolution` | 本 skill 必需显式提供 | 默认 480p，按模型列表选择。 |
| `payload.duration` | 本 skill 必需显式提供 | reference 默认 4 秒，可选 -1 或 4～模型上限；2.5 edit 只能 -1；2.0 系列 edit 不采用 2.5 的时长锁定规则。 |
| `payload.ratio` | 本 skill 必需显式提供 | 带素材默认 adaptive；2.5 edit 强制 adaptive；reference 和 2.0 系列 edit 也可使用支持的固定比例。 |
| `payload.generate_audio / output_format / watermark / return_last_frame` | 音频、水印显式提供；其余可选 | 默认 false / mp4 / true / false；需要保留、修改或生成音频时明确选择。其他技术选项同文生视频。 |
| `optimizer` | 2.5 必需 | 实际应用 sd25-pe 后记录 applied；2.0 系列可省略。 |

- 素材要求

| 素材 | Seedance 2.5 | Seedance 2.0 / Fast / Mini | 传输和其他限制 |
|---|---|---|---|
| 图片 | 最多 30 张 | 最多 9 张 | 宽高 300～6000、比例 0.4～2.5、小于 30 MB；供应商支持 Base64、HTTPS 或对应 asset://；本文原生请求示例使用可探测的 HTTPS URL。 |
| 视频 | 最多 10 段，通常每段 2～30 秒，视频合计不超过 30 秒；edit 每段待编辑视频 4～30 秒 | 最多 3 段，每段 2～15 秒，视频合计不超过 15 秒 | 宽高 300～6000、比例 0.4～2.5、总像素 407696～8295044、24～60 FPS、每段不超过 200 MB；仅 HTTPS 或对应 asset://。 |
| 音频 | 最多 10 段，每段 2～30 秒，音频合计不超过 30 秒；支持纯音频参考 | 最多 3 段，每段 2～15 秒，音频合计不超过 15 秒；不能只有音频 | WAV/MP3、每段不超过 15 MB；供应商支持 Base64、HTTPS 或对应 asset://；本文原生请求示例使用可探测的 HTTPS URL。 |

音频和视频分别统计总时长；须实际检查格式、尺寸、帧率、字节数和时长，脚本的字段校验不等于全部媒体条件已经核验。已有 asset:// 需要匹配 `provenance.provider` 及账户来源。成本脚本无法直接探测 asset://，应使用对应原始文件或 HTTPS URL 做报价检查；提交时的素材必须与该实测依据一致。不能仅凭 ID 通过而声称素材上传或信任资格已处理。

- 提示词优化

同类型素材按数组中的相对顺序称为图片1、视频1、音频1等，每份素材说明参考维度。多视频编辑须明确目标，2.5 由模型依据提示词选择源视频；`estimate_context.target_asset_index` 只控制估价目标，不是供应商编辑目标参数。2.0 编辑直接指明“视频N”，不承诺 2.5 的锁定时长行为。2.5 实际应用 sd25-pe 后，在 payload 中明确设置 `omni_reference_task_type=reference/edit`；2.0 系列不发送该字段。

- 人像检查

在成本计算和任务确认前，检查全部参考图片、参考视频及待编辑视频中的真人人脸；即使素材仅用于参考动作、背景或运镜，也不能跳过。按[人像来源](#人像来源)逐份核验，存在未解决的人脸来源问题时停止该素材的提交；提交前再次检查有效期和原始文件。纯音频参考不触发本节的人脸图片／视频检查，不据此推导声音授权规则。

#### 运行步骤

1. **构建任务 JSON：** 将文本、图片、视频和音频按原生 content 格式填写，使用已核验的 HTTPS 素材 URL，与本次 cost.json 的素材顺序及来源保持一致。脚本从成本记录读取实测信息，不把 metadata、purpose 或成本专用 id 发送给供应商。当前不提供上传或创建素材 ID 的命令。

参考生成调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "reference-to-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "reference", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "参考图片1的产品外观和视频1的运镜，生成新的室内产品展示视频，保留产品形状和标志。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "参考图片1的产品外观和视频1的运镜，生成新的室内产品展示视频，保留产品形状和标志。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "image_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "image_url": { // 必需：图片输入对象；对应 type=image_url
          "url": "https://your-approved-storage.example/product.png" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "reference_image" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      },
      {
        "type": "video_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "video_url": { // 必需：视频输入对象；对应 type=video_url
          "url": "https://your-approved-storage.example/motion.mp4" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "reference_video" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "16:9", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": false, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

视频编辑调用示例：

本示例的 optimizer 仅说明所需字段；只有实际读取并应用 sd25-pe 后，才可使用 applied 状态。

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "reference-to-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "edit", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "编辑视频1，将背景改为傍晚海边，保留原主体身份、动作顺序与镜头运动，不生成声音。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-5-260628", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "编辑视频1，将背景改为傍晚海边，保留原主体身份、动作顺序与镜头运动，不生成声音。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "video_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "video_url": { // 必需：视频输入对象；对应 type=video_url
          "url": "https://your-approved-storage.example/source.mp4" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "reference_video" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "adaptive", // 本模式固定 adaptive
    "duration": -1, // 2.5 视频编辑固定 -1，输出时长自动与目标视频基本对齐
    "generate_audio": false, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "output_format": "mp4", // 可选：mp4、mov；仅 2.5 支持该字段，2.0 系列不发送
    "return_last_frame": false, // 可选：默认 false；true 时请求末帧，成功后同时下载核对
    "omni_reference_task_type": "edit" // 2.5 参考／编辑／延长必需：reference、edit、extend，须与 operation 和 mode 一致
  },
  "optimizer": { // 2.5 流程记录：仅在实际读取并应用 sd25-pe 后填写，不提交给供应商
    "skill": "sd25-pe", // 2.5 必需：实际应用的优化 skill，固定 sd25-pe
    "status": "applied" // 2.5 必需：实际应用后记录 applied，不得伪造
  }
}
```

纯音频参考使用 2.5、mode=reference，在 content 中提供 `type=audio_url`、`role=reference_audio` 的音频项；根据需求设置 `generate_audio`，不要把参考输入音频与输出音频开关混为一谈。

2. **提交一次生成请求：** 移除示例注释并替换实际值后，将任务 JSON 通过标准输入传给命令。命令会读取 `$WORK/volcengine/cost.json`，校验计费参数并保存 `$WORK/submit-NNN.json`。输出对象的 `submission` 字段就是本次记录的绝对路径，将其记为 `$SUBMISSION`。 含视频输入时若缺少已核实最低计费门槛，报价通常仅有下界；必须先取得用户明确接受未知上界，才可附加 `--accept-uncertain-cost`，不能因下界低而默认接受。 费用上界未知时，先取得用户明确接受，再在命令中附加 `--accept-uncertain-cost`；没有明确接受时停止提交。

```bash
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<本次确认的完整任务 JSON，不含注释>
JSON
```

3. **查询生成状态：** `submit` 返回任务 ID 后，记录中的 `execution.state` 为 `queued`，尚未完成。对同一个 `$SUBMISSION` 查询；`queued/running` 时有界重复查询，`succeeded` 时检查最近一次成功查询响应的 `content.video_url`。查询失败只重试查询。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

4. **下载结果：** 仅在任务成功且含主视频 URL 后运行；`return_last_frame=true` 时还需核对末帧 URL 和下载文件。下载清单和文件保存在本次提交记录及 `$WORK/outputs/submit-NNN/` 中。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

5. **核对并交付：** reference 检查各素材的借鉴维度是否正确；edit 检查指定视频的修改、保留项及时间顺序，2.5 自动时长核对与目标视频基本一致。根据确认内容检查音轨，不能把 generate_audio=true 当作保留原音频的保证。计费包含全部输入视频时长和输出时长，并核验最低计费门槛；没有视频输入时按无视频费率，音频时长不计入输入视频秒数，见[视频计费](#文生视频图生视频参考生视频视频延长计费)。

#### 成功、失败与重试

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 任务处理中 | `execution.state` 为 `queued/running` | 对同一记录继续 `status`，不再次 `submit`。 |
| 生成成功 | `execution.state="succeeded"`，最近一次成功查询的 `queries[].response.content.video_url` 非空 | 下载并核对参考职责，或目标视频的指定修改、保留项与音频要求；请求末帧时同时核对末帧。 |
| 任务失败 | `failed/expired/cancelled`，或提交明确 `rejected` | 保留供应商错误与任务记录，修正问题；再次付费前更新方案、必要时重新估价并取得新确认。 |
| 提交结果未知 | `submitting/submission_unknown`，可能已有任务或计费 | 核对控制台；无任务 ID 时，仅在独立核实已有任务后使用 `attach-task`，不自动重发 POST。 |
| 查询或下载失败 | `status/download` 报错，或任务成功却缺少媒体 URL／所需文件 | 重试同一任务的查询或下载，核查响应与供应商恢复途径，不通过重新生成解决下载问题。 |
| 内容不符合要求 | 已下载但未满足核对参考职责，或目标视频的指定修改、保留项与音频要求等要求 | 明确差异，重新准备与确认后才可再次付费。 |

完成还需 `execution.download_complete=true`、`result.files` 与实际文件一致，并通过本能力内容核验；无法检查画面或音频时说明观察范围。恢复命令和 URL 过期处理见[共用判断](#成功失败与重试的共用判断)。

### 视频延长（`operation=extend-video`）

#### 运行要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `provider / payload.model / operation` | 必需 | `volcengine`；四款 Seedance 准确模型 ID；extend-video。 |
| `mode` | 必需 | before=向前延长；after=向后延长；必须与提示词方向一致。 |
| `original_prompt / payload.content[].text` | 保留原文；最终提示词必需 | 明确延长视频N、方向、延续的动作、镜头及画面／音频衔接要求。 |
| `payload.content` | 必需 | 至少一个 type=video_url、role=reference_video 的源视频；可按需求添加参考图片或音频，数量与限制同参考生视频。 |
| `payload.content[]` | 媒体项必需 | 提供 type、对应 image_url/video_url/audio_url.url 及 role；实测素材信息由 cost.json 读取，不放进 API 请求体。 |
| `payload.resolution` | 脚本必需显式提供 | 按用户需求和模型能力选择，不自动套用普通生成的低分辨率默认值。 |
| `payload.duration` | 脚本必需显式提供 | 指定输出时长，-1 或整数 4～模型上限；2.5 上限 30 秒，2.0 系列 15 秒，不可把该字段当作拼接后总时长。 |
| `payload.ratio` | 本 skill 必需显式提供 | 2.5 必须 adaptive；2.0 系列默认 adaptive，也支持固定比例。 |
| `payload.generate_audio` | 本 skill 必需显式提供，按需求确定 | 延长默认 true，区别于普通视频默认 false；根据确认的音频连续性要求显式设置，不保证原始音轨字节不变。 |
| `payload.output_format / watermark / return_last_frame` | 水印显式提供；其余可选 | 默认 mp4 / true / false；其他技术选项同文生视频。 |
| `optimizer` | 2.5 必需 | 实际应用 sd25-pe 后记录 applied；2.0 系列按对应指南。 |

- 素材与提示词要求

图片、视频、音频的数量、时长、尺寸、传输及人像来源要求同[参考生视频](#参考生视频operationreference-to-video)。多个源视频时需在确认前明确目标及顺序；计费仍包含全部输入视频，不只目标视频。2.5 在 payload 中明确设置 `omni_reference_task_type=extend`；mode 的前／后方向不单独成为供应商 API 字段，因此必须在最终提示词中明确，2.0 系列同样依靠提示词表达延长意图。

- 人像检查

在成本计算和任务确认前，检查所有源视频以及额外参考图片／视频中的真人人脸，按[人像来源](#人像来源)核验来源、有效期和原始性。原视频曾生成成功、编辑成功或下载成功，都不自动证明它在当前账户及当前时间仍是可信输入。实际提交前再次检查；不通过裁剪、压缩或换存储地址来假定绕过人脸审核。

#### 运行步骤

1. **构建任务 JSON：** 明确源视频、方向、输出分辨率、输出时长及音频要求；使用已有可访问视频地址。使用与本次成本计算一致的 HTTPS 素材 URL；实测信息留在 cost.json，不放入 payload。需要上传时使用已获授权的外部路径，本技能不创建素材 ID。

向后延长调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "extend-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "after", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "向后延长视频1，接着展示人物继续沿原方向行走，保持原场景、服装和镜头运动，画面与声音自然衔接。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "向后延长视频1，接着展示人物继续沿原方向行走，保持原场景、服装和镜头运动，画面与声音自然衔接。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "video_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "video_url": { // 必需：视频输入对象；对应 type=video_url
          "url": "https://your-approved-storage.example/source.mp4" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "reference_video" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "adaptive", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": true, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

向前延长调用示例：

```jsonc
{
  "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
  "operation": "extend-video", // 必需：能力，供脚本选择接口及结果处理方式
  "mode": "before", // 必需：首帧 first-frame／首尾帧 first-last-frame，参考 reference／编辑 edit，延长 before／after；不提交给供应商
  "original_prompt": "向前延长视频1，补充人物走入当前场景的前置动作，使新片段结尾与视频1开头的姿态、镜头和声音自然衔接。", // 流程记录：用户原始提示词，不提交给供应商
  "payload": { // 必需：火山引擎原生请求体，脚本校验后直接提交，不改写提示词
    "model": "doubao-seedance-2-0-260128", // 必需：准确模型 ID；使用其他模型时替换为对应 ID
    "content": [ // 必需：文本与素材数组；按各类素材顺序引用图片1／视频1／音频1
      {
        "type": "text", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "text": "向前延长视频1，补充人物走入当前场景的前置动作，使新片段结尾与视频1开头的姿态、镜头和声音自然衔接。" // 必需：最终确认的完整提示词；编辑目标与延长方向须明确
      },
      {
        "type": "video_url", // 必需：本项类型，text 或 image_url／video_url／audio_url
        "video_url": { // 必需：视频输入对象；对应 type=video_url
          "url": "https://your-approved-storage.example/source.mp4" // 必需：实际可用素材 URL；示例使用 HTTPS，须与成本检查中的素材一致
        },
        "role": "reference_video" // 必需：首帧 first_frame、尾帧 last_frame；参考素材 reference_image／reference_video／reference_audio
      }
    ],
    "resolution": "480p", // 本 skill 显式提供：默认 480p；可选档位须符合所选模型
    "ratio": "adaptive", // 本 skill 显式提供：可选支持的固定比例或 adaptive；取值见运行要求
    "duration": 4, // 本 skill 显式提供：-1 自动或 4～模型上限的整数秒；普通生成默认 4 秒，延长须明确
    "generate_audio": true, // 本 skill 显式提供：输出音频开关，普通生成默认 false，延长默认 true
    "watermark": true, // 可选：是否添加平台水印；本 skill 视频默认 true
    "return_last_frame": false // 可选：默认 false；true 时请求末帧，成功后同时下载核对
  }
}
```

切换 2.5 时保持 ratio=adaptive，核对所需时长并补真实 optimizer 记录；不能为了减少费用截断输入视频。

2. **提交一次生成请求：** 移除示例注释并替换实际值后，将任务 JSON 通过标准输入传给命令。命令会读取 `$WORK/volcengine/cost.json`，校验计费参数并保存 `$WORK/submit-NNN.json`。输出对象的 `submission` 字段就是本次记录的绝对路径，将其记为 `$SUBMISSION`。 如视频报价上界未知，须先取得用户明确接受，再附加 `--accept-uncertain-cost`；未接受时停止提交。 费用上界未知时，先取得用户明确接受，再在命令中附加 `--accept-uncertain-cost`；没有明确接受时停止提交。

```bash
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<本次确认的完整任务 JSON，不含注释>
JSON
```

3. **查询生成状态：** `submit` 返回任务 ID 后，记录中的 `execution.state` 为 `queued`，尚未完成。对同一个 `$SUBMISSION` 查询；`queued/running` 时有界重复查询，`succeeded` 时检查最近一次成功查询响应的 `content.video_url`。查询失败只重试查询。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

4. **下载结果：** 仅在任务成功且含主视频 URL 后运行；`return_last_frame=true` 时还需核对末帧 URL 和下载文件。下载清单和文件保存在本次提交记录及 `$WORK/outputs/submit-NNN/` 中。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

5. **核对并交付：** 检查延长方向、源视频目标、衔接处动作和镜头、身份、场景及音频连续性，并检查实际时长与输出规格。交付供应商实际返回的视频；若需要与源视频拼接，按单独明确的后期需求处理，本技能没有内置拼接命令，也不默认把返回结果称为完整拼接长片。计费规则与含视频输入的参考生成相同，见[视频计费](#文生视频图生视频参考生视频视频延长计费)。

#### 成功、失败与重试

| 情况 | 判断依据 | 后续处理 |
|---|---|---|
| 任务处理中 | `execution.state` 为 `queued/running` | 对同一记录继续 `status`，不再次 `submit`。 |
| 生成成功 | `execution.state="succeeded"`，最近一次成功查询的 `queries[].response.content.video_url` 非空 | 下载并核对延长方向、衔接处画面与音频连续性、实际时长及输出规格；请求末帧时同时核对末帧。 |
| 任务失败 | `failed/expired/cancelled`，或提交明确 `rejected` | 保留供应商错误与任务记录，修正问题；再次付费前更新方案、必要时重新估价并取得新确认。 |
| 提交结果未知 | `submitting/submission_unknown`，可能已有任务或计费 | 核对控制台；无任务 ID 时，仅在独立核实已有任务后使用 `attach-task`，不自动重发 POST。 |
| 查询或下载失败 | `status/download` 报错，或任务成功却缺少媒体 URL／所需文件 | 重试同一任务的查询或下载，核查响应与供应商恢复途径，不通过重新生成解决下载问题。 |
| 内容不符合要求 | 已下载但未满足核对延长方向、衔接处画面与音频连续性、实际时长及输出规格等要求 | 明确差异，重新准备与确认后才可再次付费。 |

完成还需 `execution.download_complete=true`、`result.files` 与实际文件一致，并通过本能力内容核验；无法检查画面或音频时说明观察范围。恢复命令和 URL 过期处理见[共用判断](#成功失败与重试的共用判断)。


# 参考

本说明于 2026-10-21 对照下列官方来源核验。机器可读的模型能力位于 `models/volcengine.json`；ID、格式、限制和操作均以该文件为唯一数据来源。网络传输直接使用 Python 标准库 HTTPS，无需 SDK 包。API Key 只从项目 `.env` 的 `VOLCENGINE_API_KEY` 读取。固定北京端点为 `https://ark.cn-beijing.volces.com/api/v3`。不得将凭证重定向至自定义端点。

## API 契约

- 图片：`POST /images/generations`。处理所有 `data` 项，包括错误项和拆分图层。`response_format=url|b64_json`。保留 `usage`，以及每层的 `z_index`、`bounding_box`、`name`、`description`。支持 PNG/JPEG 输出，图层始终使用 PNG。
- 视频：`POST /contents/generations/tasks` 返回 `id`。通过 `GET /contents/generations/tasks/{id}` 查询；queued/running 为非终态，succeeded/failed/expired/cancelled 为终态。成功媒体位于 `content.video_url` 及可选的 `content.last_frame_url`。不能将 API 接受请求等同于媒体生成成功。按原始返回报告 `usage.completion_tokens` / `total_tokens`。
- 视频输入：文本加 `image_url` / `video_url` / `audio_url`，并明确指定角色。首帧、首尾帧模式与多模态参考模式互斥。图片和音频接受 HTTPS、Base64 或 asset://；视频只接受 HTTPS 或 asset://。Seedream 图片 API 接受 URL/Base64，不接受 asset://。
- 本地图片和音频在提交时于内存中转为 Base64；具体端点允许时也可使用 HTTPS URL 与已有 Volcengine `asset://` ID。本技能不调用 Volcengine 上传 API，也不创建素材 ID。用户必须另行通过供应商或获准存储上传，再提供素材 ID 或 URL。视频输入不能使用 Base64。
- 结果 URL 通常保留 24 小时，应及时下载并保留原始字节。不断重新查询无法修复过期媒体；提出新付费生成前先检查已有存储或供应商恢复能力。沙箱环境阻断出站 DNS 或网络时，使用提升权限的 API 网络命令；否则 Python `urllib` 可能在收到 HTTP 响应前就于本地抛出 `URLError`。传输诊断应保留脱敏的底层原因，例如 `gaierror`，不得包含秘密信息。

## 各模型限制

- 2.5：视频编辑、延长及首帧/首尾帧比例必须为 adaptive。编辑时长必须为 -1；编辑输入视频为 4..30 秒。其他输入视频或音频为 2..30 秒；每类合计时长不超过 30 秒。2.0 系列输入视频或音频为 2..15 秒，每类合计不超过 15 秒。数量限制见模型目录。2.0 不支持纯音频参考。
- 视频任务的输入图片：宽高 300..6000，比例 0.4..2.5，小于 30 MB。输入视频总像素 407696..8295044，宽高 300..6000，比例 0.4..2.5，帧率 24..60 FPS，每段不超过 200 MB。音频支持 WAV/MP3，不超过 15 MB。请求体不超过 64 MB。确认前检查远程素材格式与尺寸；成本计算或本地编译不代表完成生成接口的联网预检。
- Pro/Flash：参考图不超过 10 张，每张不超过 30 MB；宽高均大于 14，比例 1/16..16，总像素不超过 3600 万。图层拆分输入为单张 PNG/JPEG，总像素至少 262144。标准生成支持 1K/1.5K/2K 或准确像素，总像素 921600..4624220，比例 1/16..16。拆分只支持尺寸档位或 auto。
- Pro/Flash 标准生成优先使用文档中的分辨率档位（`1K`、`1.5K` 或 `2K`），并在 `prompt` 中自然描述宽高比；不要同时发送 `ratio` 字段。常见 1K 映射包括 4:3 = 1152x864。准确像素模式最低为 921600 像素：1024x768 只有 786432 像素，无效；1152x864 有效。不要根据传统 1024x768 画布缩放推导尺寸。
- Pro/Flash 每个请求生成一张图片，不支持 `sequential_image_generation` / `sequential_image_generation_options.max_images`。`image` 的输入数量（最多 10 张参考）与输出数量不同。不要为一个 Pro/Flash 请求宣传多张输出选项，不要发送 `n` 或顺序组图输出字段。这些模型也不支持 stream 或 web_search。
- Seedream 5.0 Pro/Flash 图片请求必须包含 `model`（Pro：`doubao-seedream-5-0-pro-260628`；Flash：`doubao-seedream-5-0-flash-260915`）和 `prompt`；可选字段为 `image`（URL 或 data URI/Base64，最多 10 张参考）、`size`、`output_format`、`response_format`、`watermark`、`background`、`optimize_prompt_options`、`layer_decomposition`。
- `size`：`1K` / `1.5K` / `2K`（API 默认 2K），或满足总像素 921600..4624220、宽高比 1/16..16 的准确 `WxH`。优先使用档位并在提示词描述比例，不单独发送 ratio 字段。常见映射：1K、4:3 = 1152x864。
- `output_format`：`png` 或 `jpeg`（官方 API 默认 `jpeg`，本技能明确默认 `png`）。`response_format`：`url` 或 `b64_json`（默认 `url`；URL 在 24 小时后过期）。
- `watermark`：布尔值。官方 API 默认 `true`，本技能按用户偏好明确默认发送 `false`。用户明确选择时应遵从。
- `background`：`opaque` 或 `transparent`（默认 `opaque`）。透明输出仅限编辑单张带 Alpha 通道的输入图，并使用 PNG 输出。
- `optimize_prompt_options.mode`：Pro 和 Flash 均支持 `standard`，只有 Pro 支持 `fast`。服务端提示词优化与必需的 sd25-pe 工作流程不同。
- `layer_decomposition`：布尔值，默认 `false`；设为 `true` 启用图层拆分，且必须只有一张输入图片。普通生成保持 false。Pro/Flash 每次请求只生成一份输出，不发送 `n` 或顺序组图字段。
- 文生图请求示例（Flash；使用 Pro 时只修改模型 ID）：
  ```json
  {
    "model": "doubao-seedream-5-0-flash-260915",
    "prompt": "一只小猫趴在草地上，柔和自然光，摄影质感。画面比例为4:3。",
    "size": "1K",
    "output_format": "png",
    "response_format": "url",
    "watermark": false,
    "background": "opaque",
    "optimize_prompt_options": {"mode": "standard"},
    "layer_decomposition": false
  }
  ```
- 适配器不暴露 seed/camera_fixed/frames（所选 Seedance API 不支持）、flex 推理、草稿流程或视频 web_search。用户设置在任务确认单展示，技术请求细节保留在任务配置及提交记录中。不支持的选项会被拒绝，不会被静默忽略。

## 人像来源

本节约束 Seedance 2.5、2.0 系列接收的含真人人脸图片／视频，不是所有 Seedream 图片任务的统一前置限制。这些模型不支持任意含真人人脸的参考图／视频直接上传。官方提供可信模型原始产物、预置虚拟人像、已授权真人素材三类路径；普通上传或仅声明“已有授权”，不代表已完成供应商要求的开通、认证或素材接入。

| 所选路径 | 确认前检查 |
|---|---|
| 可信模型原始产物 | 同一火山方舟平台、同一实际调用账户、生成后 30 天内且保持原始字节。限指南列出的 Seedance 2.5／2.0 系列含人脸视频及对应尾帧，或 Seedream 5.0 Lite／Pro／Flash **文生图**人脸图片；图生图及拆分图层不自动在此范围内。 |
| 预置虚拟人像 | 使用供应商提供且当前账户可用的素材及 ID，遵循该素材支持的输入角色；不要把任意 AI 图片称为预置虚拟人像。 |
| 已授权真人素材 | 按官方指南检查当前账户开通条件、授权／认证材料与可用素材接入方式；本技能不负责代办认证、上传或创建素材 ID。 |

在各能力的“人像检查”节点完成上述核验后，再报价和展示确认单；提交前再次确认文件、账户与有效期没有变化。可信原始产物的来源记录应能关联实际模型、生成操作、生成时间、账户、原始响应／任务 ID 和原文件哈希。`provenance` 只记录事实，当前脚本不自动认证人像、校验 30 天信任或验证授权，不得仅凭字段存在判定通过。

不要编辑、压缩或转发后继续沿用原产物的可信结论。30 天信任窗口与结果 URL 的 24 小时保留期不同：下载、原字节转存或更换 URL 不会重新开始 30 天；TOS 转存也不改变素材来源。本技能不会自动转存。对于不含人脸的素材，不套用此人脸信任限制。

人脸输入受信不保证输出通过平台审核。若返回人脸／肖像相关审核错误，保留提交记录和错误码，回到对应能力的人像检查节点修正；不直接重发付费请求。官方入口及完整细则见文末“人像素材”。

## 能力执行的共用约定

### 成功、失败与重试的共用判断

| 现象 / 状态 | 判断依据与下一步 |
|---|---|
| 成本计算／本地编译成功 | 只证明取得估价或请求可编译；不能证明已生成、已验证远程素材或账户权限 |
| 图片 succeeded | 响应有非空 data，当前脚本未发现项级 error；还须检查可用图片并完成下载 |
| 图片 partial_failed | 至少一项含 error；可下载其他有效项，记录遗漏；不能认定全部成功 |
| 视频返回 id、queued / running | 只代表任务创建或处理中；继续 status，不创建第二个任务 |
| 视频 succeeded | 还须存在 content.video_url、下载完整并核对产物；请求了末帧时也核对 last_frame_url |
| failed / expired / cancelled / rejected | 保存错误与任务状态；分析原因。修改后重新准备、报价、确认，不对同一计划重复 POST |
| submitting / submission_unknown、POST 超时或中断 | 不确定是否已受理或计费；保留状态，在供应商控制台核对。核实已有视频任务后可用 attach-task 关联，再查询或下载 |
| 下载失败 | 保留任务与已下载文件，重复 download；媒体 GET 已有最多3次尝试及2/4秒退避，不是付费 POST 重试 |
| URL 过期 | 优先已有本地文件或供应商恢复途径；不因下载失败自动重新付费生成 |

`attach-task --submission "$SUBMISSION" --task-id '<独立核实的已有视频任务ID>'` 只用于没有任务 ID 的未知视频提交；还须核对创建时间、素材及提示词，它不能替图片请求恢复，也不会证明内容一致。不要删除提交记录绕过重复提交保护。

下载完成依据为对应提交记录的 execution.download_complete、result 文件清单与实际文件一致；头部格式及哈希校验不证明视觉或音频质量。还需检查能力章节列出的内容要求，无法观察的部分明确说明。把完整媒体复制到用户输出目录，保留原始字节，返回绝对本地链接；图层位置元数据同样交付，其他过程文件留在临时目录。

## 官方来源

按当前任务读取相关来源，分别核对能力、提示词、接口、模型差异和人像输入规则；不得将其他模型的示例字段直接视为当前脚本支持。

- [Seedance 2.5 教程](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh) — 核对 2.5 各模式能力、参数特殊限制及报错机制。
- [Seedance 2.5 提示词指南](https://docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide?lang=zh) — 优化 2.5 参考生成、编辑、延长及多素材提示词。
- [Seedance 2.0 系列教程](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=zh) — 核对 2.0／Fast／Mini 能力与版本差异。
- [Seedance 2.0 提示词指南](https://docs.volcengine.com/docs/ark/seedance-2-0-prompt-guide?lang=zh) — 按 2.0 系列规则组织镜头与素材引用，避免套用 2.5 控制方式。
- [视频生成教程与像素映射](https://docs.volcengine.com/docs/ark/video-generation-tutorial?lang=zh) — 核对通用生成流程、输出规格和像素映射。
- [创建视频任务 API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh) — 核对提交请求字段、素材角色、参数范围和接口限制。
- [查询视频任务 API](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh) — 核对任务状态、错误及视频／尾帧响应字段。
- [人像素材](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh) — 核对人脸输入适用范围、可信原始产物、虚拟人像和已授权真人素材路径。
- [Seedream Pro/Flash 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh) — 核对 Pro／Flash 的图片编辑与图层拆分用法。
- [交互式图片编辑](https://docs.volcengine.com/docs/ark/seedream-5-0-pro-editing-guide?lang=zh) — 核对局部编辑点选／框选坐标及标签格式。
- [通用图片生成与模型特例](https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh) — 核对通用图片能力与 Pro／Flash 例外，避免误用其他 Seedream 版本的组图、搜索等能力。
- [图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh) — 核对图片请求字段、尺寸、格式、图层响应及错误规则。
- [模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh) — 核对官方模型 ID、版本及可用能力；本地目录需随已核验来源维护。