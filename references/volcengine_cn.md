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
| 文生图 | — | Seedream 5.0 Pro、Flash | 已实现 | [文生图](#文生图) |
| 图生图 | 单图编辑、多图融合、局部编辑 | Seedream 5.0 Pro、Flash | 已实现 | [图生图](#图生图) |
| 图层拆分 | — | Seedream 5.0 Pro、Flash | 已实现 | [图层拆分](#图层拆分) |
| 文生视频 | — | Seedance 2.5、2.0、2.0 Fast、2.0 Mini | 已实现 | [文生视频](#文生视频) |
| 图生视频 | 首帧、首尾帧 | 同上四款 Seedance | 已实现 | [图生视频](#图生视频) |
| 参考生视频 | 参考生成、视频编辑 | 同上四款 Seedance；纯音频参考仅 2.5 | 已实现 | [参考生视频](#参考生视频) |
| 视频延长 | 向前延长、向后延长 | 同上四款 Seedance | 已实现 | [视频延长](#视频延长) |

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

只有 `execution.download_complete=true`、`result.files` 清单与实际文件一致，且图片通过已确认要求的内容核验，才算任务完成。无法核验的内容需明确说明。

### 图生图

本能力统一使用 `operation="image-to-image"`，不提供顶层 `mode`；单图编辑、多图融合、局部修改均通过输入图片及提示词表达。

#### 单图编辑

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedream-5.0-pro`、`seedream-5.0-flash`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `image-to-image` | 本能力固定值；更换操作需要重新准备计划。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 明确改什么、保留什么；一张输入图。 |
| `parameters` | 普通图片必需 | 对象；仅接受下列parameters子字段 | 普通图片必须通过此对象提供ratio。 |
| `parameters.size` | 可选 | `1K`、`1.5K`、`2K`、准确`WxH`；默认`1K` | Pro/Flash相同；准确总像素921600..4624220、宽高比1/16..16，准确像素优先。 |
| `parameters.ratio` | 必需 | `21:9`、`16:9`、`3:2`、`4:3`、`1:1`、`3:4`、`2:3`、`9:16` | 作为构图提示追加到prompt，不作为图片API独立ratio参数，不保证准确输出比例。 |
| `parameters.output_format` | 可选 | `png`、`jpeg`；默认`png` | 透明输出必须PNG；Pro/Flash相同。 |
| `parameters.response_format` | 可选 | `url`、`b64_json`；默认`url` | 临时URL通常保留24小时；download负责获取URL或解码Base64。 |
| `parameters.watermark` | 可选 | `true`、`false`；本skill默认`false` | 控制平台水印；区别于官方API默认值。 |
| `parameters.background` | 可选 | `opaque`、`transparent`；默认`opaque` | transparent要求单张实测带Alpha输入、PNG输出；不满足时拒绝。 |
| `parameters.optimize_prompt_options` | 可选 | 对象；默认`{"mode":"standard"}` | 供应商服务端优化，不等于外部优化skill调用。 |
| `parameters.optimize_prompt_options.mode` | 对象存在时提供 | Pro：`standard`或`fast`；Flash：仅`standard` | Pro/Flash默认standard；CLI只接受列出的完整对象形式。 |
| `assets` | 必需 | 恰好1张图片 | 普通图片每请求只生成一张，输入张数与输出张数不同；拆分除外。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL | Seedream不接受asset://；本地图片提交时内存编码Base64，无独立上传步骤。 |
| `assets[].role` | 可选 | `reference_image`；图片接口不按role控制素材 | 图片接口不使用此字段编译角色，可省略；建议沿用示例标记。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 单张透明编辑时必需；其他可选 | 布尔`true`、`false`，需实际检测 | 仅图生图单张带Alpha输入、PNG输出允许transparent。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | 可信人像相关用途需要实际来源证据；Seedream输入不接受asset://。 |
| `assets[].provenance.provider` | 可选 | `volcengine`，需符合实际来源 | 仅记录实际来源，不表示图片由火山生成；外部素材不要虚构供应商来源。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |

##### 生成步骤

1. 检查唯一输入图，确认修改范围与产品保留项；需要透明背景时验证Alpha。
2. 本地图片随请求Base64发送或直接使用HTTPS；读取任务配置与cost.json并展示确认单（见调用示例）并确认。
3. 确认后submit、download；将结果与原图对照再交付。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // optimizer不用于本图片示例；图片费用按张数/像素计算，没有可靠的调用前Token公式。
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedream-5.0-flash", // 必需：seedream-5.0-pro、seedream-5.0-flash，或对应准确ID；用户指定模型不得静默更换
  "operation": "image-to-image",
  "original_prompt": "把图片1的背景改为浅灰色，保留产品形状、颜色、标志和主体位置。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "把图片1的背景改为浅灰色，保留产品形状、颜色、标志和主体位置。", // 必需：优化后的完整提示词；局部编辑需实际核验区域或标注
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "size": "1K", // 可选：默认1K；1K、1.5K、2K或准确WxH；准确总像素921600..4624220、比例1/16..16
    "ratio": "1:1", // 必需：确认前选定21:9、16:9、3:2、4:3、1:1、3:4、2:3、9:16；仅追加构图提示，准确像素优先
    "output_format": "png", // 可选：png或jpeg；本skill默认png；透明输出必须png；拆分图层保存PNG
    "response_format": "url", // 可选：url或b64_json，默认url；临时URL通常保留24小时，b64_json由download解码
    "watermark": false, // 可选布尔：本skill默认false，控制平台水印
    "background": "opaque", // 可选：默认opaque；transparent仅限单张实测has_alpha=true的输入且输出png
    "optimize_prompt_options": { // 可选：服务端提示词优化对象，默认mode=standard；不是外部优化skill调用
      "mode": "standard" // 可选：默认standard；Pro还可用fast，Flash仅standard；不同于sd25-pe
    }
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/product.png", // 必需：本地绝对路径或HTTPS；Seedream不接受asset://；本地文件提交时内存编码Base64
      "purpose": "编辑对象，保留产品外观", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，图片接口不以role控制输入
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`layer_decomposition`由operation自动确定，不能手工加入parameters；普通输出每请求一张，拆分除外。`n`、sequential_image_generation、stream和tools不受支持。输入请求体不得超过64MB，Base64会放大体积。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：图片为同步响应，无需远程轮询；succeeded时下载全部结果，partial_failed时可下载有效项但须说明缺失。URL由脚本获取，b64_json由脚本解码；下载失败只重试download。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第七步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

除共用图片成功条件外，核对指定修改已生效且保留项未改变；接口成功不等于编辑准确。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

#### 多图融合

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedream-5.0-pro`、`seedream-5.0-flash`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `image-to-image` | 本能力固定值；更换操作需要重新准备计划。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 明确每张图提供的主体、背景、配色等职责及最终画面。 |
| `parameters` | 普通图片必需 | 对象；仅接受下列parameters子字段 | 普通图片必须通过此对象提供ratio。 |
| `parameters.size` | 可选 | `1K`、`1.5K`、`2K`、准确`WxH`；默认`1K` | Pro/Flash相同；准确总像素921600..4624220、宽高比1/16..16，准确像素优先。 |
| `parameters.ratio` | 必需 | `21:9`、`16:9`、`3:2`、`4:3`、`1:1`、`3:4`、`2:3`、`9:16` | 作为构图提示追加到prompt，不作为图片API独立ratio参数，不保证准确输出比例。 |
| `parameters.output_format` | 可选 | `png`、`jpeg`；默认`png` | Pro/Flash均支持这两种格式。 |
| `parameters.response_format` | 可选 | `url`、`b64_json`；默认`url` | 临时URL通常保留24小时；download负责获取URL或解码Base64。 |
| `parameters.watermark` | 可选 | `true`、`false`；本skill默认`false` | 控制平台水印；区别于官方API默认值。 |
| `parameters.background` | 可选 | 仅`opaque`；默认`opaque` | 本操作不支持transparent，不能因字段存在而启用透明背景。 |
| `parameters.optimize_prompt_options` | 可选 | 对象；默认`{"mode":"standard"}` | 供应商服务端优化，不等于外部优化skill调用。 |
| `parameters.optimize_prompt_options.mode` | 对象存在时提供 | Pro：`standard`或`fast`；Flash：仅`standard` | Pro/Flash默认standard；CLI只接受列出的完整对象形式。 |
| `assets` | 必需 | 2..10张图片 | 普通图片每请求只生成一张，输入张数与输出张数不同；拆分除外。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL | Seedream不接受asset://；本地图片提交时内存编码Base64，无独立上传步骤。 |
| `assets[].role` | 可选 | `reference_image`；图片接口不按role控制素材 | 图片接口不使用此字段编译角色，可省略；建议沿用示例标记。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 可选 | 布尔`true`、`false`，需实际检测 | 仅图生图单张带Alpha输入、PNG输出允许transparent。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | 可信人像相关用途需要实际来源证据；Seedream输入不接受asset://。 |
| `assets[].provenance.provider` | 可选 | `volcengine`，需符合实际来源 | 仅记录实际来源，不表示图片由火山生成；外部素材不要虚构供应商来源。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |

##### 生成步骤

1. 逐张检查素材并固定顺序、职责，明确最终画面只需一张图片。
2. 读取任务配置与cost.json并展示确认单（见调用示例）；报价计入模型适用的额外输入图费用，展示确认单。
3. 确认后submit一次、download；核对所有指定参考作用再交付。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // optimizer不用于本图片示例；图片费用按张数/像素计算，没有可靠的调用前Token公式。
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedream-5.0-flash", // 必需：seedream-5.0-pro、seedream-5.0-flash，或对应准确ID；用户指定模型不得静默更换
  "operation": "image-to-image",
  "original_prompt": "将图片1的产品自然放入图片2的室内场景，保留产品标志与比例，匹配场景光照，不增加其他产品。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "将图片1的产品自然放入图片2的室内场景，保留产品标志与比例，匹配场景光照，不增加其他产品。", // 必需：优化后的完整提示词；局部编辑需实际核验区域或标注
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "size": "1K", // 可选：默认1K；1K、1.5K、2K或准确WxH；准确总像素921600..4624220、比例1/16..16
    "ratio": "4:3", // 必需：确认前选定21:9、16:9、3:2、4:3、1:1、3:4、2:3、9:16；仅追加构图提示，准确像素优先
    "output_format": "png", // 可选：png或jpeg；本skill默认png；透明输出必须png；拆分图层保存PNG
    "response_format": "url", // 可选：url或b64_json，默认url；临时URL通常保留24小时，b64_json由download解码
    "watermark": false, // 可选布尔：本skill默认false，控制平台水印
    "background": "opaque", // 可选但本操作仅opaque；默认opaque，透明输出不适用于本能力
    "optimize_prompt_options": { // 可选：服务端提示词优化对象，默认mode=standard；不是外部优化skill调用
      "mode": "standard" // 可选：默认standard；Pro还可用fast，Flash仅standard；不同于sd25-pe
    }
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/product.png", // 必需：本地绝对路径或HTTPS；Seedream不接受asset://；本地文件提交时内存编码Base64
      "purpose": "提供产品主体", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，图片接口不以role控制输入
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    },
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/room.png", // 必需：本地绝对路径或HTTPS；Seedream不接受asset://；本地文件提交时内存编码Base64
      "purpose": "提供室内场景与光线", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，图片接口不以role控制输入
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`layer_decomposition`由operation自动确定，不能手工加入parameters；普通输出每请求一张，拆分除外。`n`、sequential_image_generation、stream和tools不受支持。输入请求体不得超过64MB，Base64会放大体积。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：图片为同步响应，无需远程轮询；succeeded时下载全部结果，partial_failed时可下载有效项但须说明缺失。URL由脚本获取，b64_json由脚本解码；下载失败只重试download。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第七步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

普通输出仍为一张；检查产品是否来自正确参考、场景是否正确、主体数量与标志是否保留。输入多张不代表应返回多张。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

#### 局部编辑

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedream-5.0-pro`、`seedream-5.0-flash`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `image-to-image` | 本能力固定值；更换操作需要重新准备计划。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 含经核验的`<point>`或`<bbox>`标签，或提供purpose为annotated edit region的标注图；坐标0..999，bbox左上到右下且面积非零。 |
| `parameters` | 普通图片必需 | 对象；仅接受下列parameters子字段 | 普通图片必须通过此对象提供ratio。 |
| `parameters.size` | 可选 | `1K`、`1.5K`、`2K`、准确`WxH`；默认`1K` | Pro/Flash相同；准确总像素921600..4624220、宽高比1/16..16，准确像素优先。 |
| `parameters.ratio` | 必需 | `21:9`、`16:9`、`3:2`、`4:3`、`1:1`、`3:4`、`2:3`、`9:16` | 作为构图提示追加到prompt，不作为图片API独立ratio参数，不保证准确输出比例。 |
| `parameters.output_format` | 可选 | `png`、`jpeg`；默认`png` | 透明输出必须PNG；Pro/Flash相同。 |
| `parameters.response_format` | 可选 | `url`、`b64_json`；默认`url` | 临时URL通常保留24小时；download负责获取URL或解码Base64。 |
| `parameters.watermark` | 可选 | `true`、`false`；本skill默认`false` | 控制平台水印；区别于官方API默认值。 |
| `parameters.background` | 可选 | `opaque`、`transparent`；默认`opaque` | transparent要求单张实测带Alpha输入、PNG输出；不满足时拒绝。 |
| `parameters.optimize_prompt_options` | 可选 | 对象；默认`{"mode":"standard"}` | 供应商服务端优化，不等于外部优化skill调用。 |
| `parameters.optimize_prompt_options.mode` | 对象存在时提供 | Pro：`standard`或`fast`；Flash：仅`standard` | Pro/Flash默认standard；CLI只接受列出的完整对象形式。 |
| `assets` | 必需 | 1..10张图片 | 普通图片每请求只生成一张，输入张数与输出张数不同；拆分除外。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL | Seedream不接受asset://；本地图片提交时内存编码Base64，无独立上传步骤。 |
| `assets[].role` | 可选 | `reference_image`；图片接口不按role控制素材 | 图片接口不使用此字段编译角色，可省略；建议沿用示例标记。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 描述每份素材的职责；局部编辑没有坐标标签时，至少一项purpose必须精确为annotated edit region。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 单张透明编辑时必需；其他可选 | 布尔`true`、`false`，需实际检测 | 仅图生图单张带Alpha输入、PNG输出允许transparent。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | 可信人像相关用途需要实际来源证据；Seedream输入不接受asset://。 |
| `assets[].provenance.provider` | 可选 | `volcengine`，需符合实际来源 | 仅记录实际来源，不表示图片由火山生成；外部素材不要虚构供应商来源。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |

##### 生成步骤

1. 从实际图片核验区域，按round(pixel / displayed_image_dimension * 1000)归一化并限制0..999；示例坐标不可盲用。
2. 固定目标图、区域和保留要求后，读取任务配置与cost.json并展示确认单（见调用示例）并展示确认单。
3. 确认后submit、download；对照区域内修改与区域外保留情况再交付。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // optimizer不用于本图片示例；图片费用按张数/像素计算，没有可靠的调用前Token公式。
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedream-5.0-flash", // 必需：seedream-5.0-pro、seedream-5.0-flash，或对应准确ID；用户指定模型不得静默更换
  "operation": "image-to-image",
  "original_prompt": "仅将图片1中<bbox>200 200 600 600</bbox>区域的杯子改为蓝色，保留其他区域。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "仅将图片1中<bbox>200 200 600 600</bbox>区域的杯子改为蓝色，保留其他区域。", // 必需：优化后的完整提示词；局部编辑需实际核验区域或标注
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "size": "1K", // 可选：默认1K；1K、1.5K、2K或准确WxH；准确总像素921600..4624220、比例1/16..16
    "ratio": "1:1", // 必需：确认前选定21:9、16:9、3:2、4:3、1:1、3:4、2:3、9:16；仅追加构图提示，准确像素优先
    "output_format": "png", // 可选：png或jpeg；本skill默认png；透明输出必须png；拆分图层保存PNG
    "response_format": "url", // 可选：url或b64_json，默认url；临时URL通常保留24小时，b64_json由download解码
    "watermark": false, // 可选布尔：本skill默认false，控制平台水印
    "background": "opaque", // 可选：默认opaque；transparent仅限单张实测has_alpha=true的输入且输出png
    "optimize_prompt_options": { // 可选：服务端提示词优化对象，默认mode=standard；不是外部优化skill调用
      "mode": "standard" // 可选：默认standard；Pro还可用fast，Flash仅standard；不同于sd25-pe
    }
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/cup.png", // 必需：本地绝对路径或HTTPS；Seedream不接受asset://；本地文件提交时内存编码Base64
      "purpose": "局部编辑对象，坐标需根据实际图片核验", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，图片接口不以role控制输入
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`layer_decomposition`由operation自动确定，不能手工加入parameters；普通输出每请求一张，拆分除外。`n`、sequential_image_generation、stream和tools不受支持。输入请求体不得超过64MB，Base64会放大体积。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：图片为同步响应，无需远程轮询；succeeded时下载全部结果，partial_failed时可下载有效项但须说明缺失。URL由脚本获取，b64_json由脚本解码；下载失败只重试download。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第七步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

下载成功后还要核对编辑位置正确、区域外没有不期望的变化；标注图可编译不证明区域已自动识别正确。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

### 图层拆分

本能力对应 `operation=decompose-layers`。

#### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedream-5.0-pro`、`seedream-5.0-flash`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `decompose-layers` | 本能力固定值；更换操作需要重新准备计划。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 可选；默认空字符串 | 拆分要求字符串或空字符串 | 可说明拆分目标，不保证指定层数。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 拆分默认size=auto、ratio=auto。 |
| `parameters.size` | 可选 | `1K`、`1.5K`、`2K`、`auto`；默认`auto` | Pro/Flash相同；拆分禁止准确WxH。 |
| `parameters.ratio` | 可选；默认auto | 仅`auto` | 拆分跟随输入。 |
| `parameters.output_format` | 可选 | `png`、`jpeg`；默认`png` | 拆分透明图层保存为PNG。 |
| `parameters.response_format` | 可选 | `url`、`b64_json`；默认`url` | 临时URL通常保留24小时；download负责获取URL或解码Base64。 |
| `parameters.watermark` | 可选 | `true`、`false`；本skill默认`false` | 控制平台水印；区别于官方API默认值。 |
| `parameters.background` | 可选 | 仅`opaque`；默认`opaque` | 本操作不支持transparent，不能因字段存在而启用透明背景。 |
| `parameters.optimize_prompt_options` | 可选 | 对象；默认`{"mode":"standard"}` | 供应商服务端优化，不等于外部优化skill调用。 |
| `parameters.optimize_prompt_options.mode` | 对象存在时提供 | Pro：`standard`或`fast`；Flash：仅`standard` | Pro/Flash默认standard；CLI只接受列出的完整对象形式。 |
| `assets` | 必需 | 恰好1张图片 | 普通图片每请求只生成一张，输入张数与输出张数不同；拆分除外。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL | Seedream不接受asset://；本地图片提交时内存编码Base64，无独立上传步骤。 |
| `assets[].role` | 可选 | `reference_image`；图片接口不按role控制素材 | 图片接口不使用此字段编译角色，可省略；建议沿用示例标记。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。拆分总像素还须至少262144。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 宽高均大于14、比例1/16..16、总像素不超过3600万。拆分总像素还须至少262144。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 可选 | 布尔`true`、`false`，需实际检测 | 仅图生图单张带Alpha输入、PNG输出允许transparent。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | 可信人像相关用途需要实际来源证据；Seedream输入不接受asset://。 |
| `assets[].provenance.provider` | 可选 | `volcengine`，需符合实际来源 | 仅记录实际来源，不表示图片由火山生成；外部素材不要虚构供应商来源。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |

#### 生成步骤

1. 检查单张输入图的格式与像素，明确交付包括图层和位置元数据。
2. 读取任务配置与cost.json并展示确认单（见调用示例），用拆分费用范围报价，不能按一张普通图片报价。
3. 确认后submit、download全部有效data项；整理图层位置元数据至最终输出目录。

#### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // optimizer不用于本图片示例；图片费用按张数/像素计算，没有可靠的调用前Token公式。
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedream-5.0-flash", // 必需：seedream-5.0-pro、seedream-5.0-flash，或对应准确ID；用户指定模型不得静默更换
  "operation": "decompose-layers", // 必需：本能力固定decompose-layers；切换操作须重新准备和确认
  "original_prompt": "", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "", // 可省略或空字符串：拆分要求；此处无需编造提示词
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "size": "auto", // 可选：默认auto；1K、1.5K、2K、auto；禁止准确WxH
    "ratio": "auto", // 可选且仅auto：拆分跟随输入；默认auto
    "output_format": "png", // 可选：png或jpeg；本skill默认png；透明输出必须png；拆分图层保存PNG
    "response_format": "url", // 可选：url或b64_json，默认url；临时URL通常保留24小时，b64_json由download解码
    "watermark": false, // 可选布尔：本skill默认false，控制平台水印
    "background": "opaque", // 可选但本操作仅opaque；默认opaque，透明输出不适用于本能力
    "optimize_prompt_options": { // 可选：服务端提示词优化对象，默认mode=standard；不是外部优化skill调用
      "mode": "standard" // 可选：默认standard；Pro还可用fast，Flash仅standard；不同于sd25-pe
    }
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/scene.png", // 必需：本地绝对路径或HTTPS；Seedream不接受asset://；本地文件提交时内存编码Base64
      "purpose": "拆分底图和前景主体", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，图片接口不以role控制输入
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`layer_decomposition`由operation自动确定，不能手工加入parameters；普通输出每请求一张，拆分除外。`n`、sequential_image_generation、stream和tools不受支持。输入请求体不得超过64MB，Base64会放大体积。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：图片为同步响应，无需远程轮询；succeeded时下载全部结果，partial_failed时可下载有效项但须说明缺失。URL由脚本获取，b64_json由脚本解码；下载失败只重试download。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第七步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。同时交付全部有效图层的bounding_box、z_index、name、description等位置层级元数据，不能只交付第一张图。

#### 成功、失败与重试

逐项检查底图和返回图层，保留name、description、bounding_box、z_index；不强求17张。存在项级错误时为部分失败，不能只检查data[0]或宣称完整成功。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

### 文生视频

本能力对应 `operation=text-to-video`。

#### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `text-to-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 描述主体、动作、场景、镜头、必要对白和事件顺序。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 省略对象时按当前模型及操作的字段默认值编译。 |
| `parameters.resolution` | 可选 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。 |
| `parameters.duration` | 可选 | `-1`自动，或`4..模型上限`的整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认16:9；各视频模型允许列出的比例；adaptive缺少像素依据时费用未知。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`false` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 可选；省略为空数组 | 只能空数组`[]` | 文生视频禁止携带任何素材。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

#### 生成步骤

1. 选择支持的模型与输出规格；2.5先实际应用sd25-pe，其他模型按对应指南优化。
2. 无素材上传；读取任务配置与cost.json并展示确认单（见调用示例），按无输入视频费率报价并确认。
3. 确认后submit一次，status至succeeded，再download和核对成片。

#### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：不上传素材。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "text-to-video", // 必需：本能力固定text-to-video；切换操作须重新准备和确认
  "original_prompt": "一只熊猫在绿色草坡上缓慢打滚，低机位中景，镜头轻微跟随，不添加字幕。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "一只熊猫在绿色草坡上缓慢打滚，低机位中景，镜头轻微跟随，不添加字幕。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 4, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": false, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [] // 不需要素材，省略或空数组；本操作禁止输入素材
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

#### 成功、失败与重试

按共用视频条件下载主视频；核对主体、动作、顺序、时长和约定音频，不因收到id就报告完成。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

### 图生视频

本能力统一使用 `operation="image-to-video"`。

| 模式 | mode |
|---|---|
| 首帧 | `first-frame` |
| 首尾帧 | `first-last-frame` |

#### 首帧生成

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `image-to-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `mode` | 必需 | `first-frame` | 当前模式；其他模式见所属能力的要求。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 以输入图作为严格首帧，描述后续运动与保留要求。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 省略对象时按当前模型及操作的字段默认值编译。 |
| `parameters.resolution` | 可选 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。 |
| `parameters.duration` | 可选 | `-1`自动，或`4..模型上限`的整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认adaptive；2.5本操作仅adaptive；2.0系列允许列出的比例。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`false` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 必需 | 恰好1张图片 | 唯一输入必须为first_frame，不混入多模态参考。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL、已有火山`asset://`ID | 视频仅HTTPS/已有素材ID，禁止本地路径及Base64；本地图片/音频提交时内存编码；当前无上传命令。 |
| `assets[].role` | 每项必需且顺序固定 | `first_frame` | 视频省略时默认reference_加kind；首帧/首尾帧不能使用该默认值。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 可选，仅记录图片信息 | 布尔`true`、`false`，需实际检测 | 仅作图片原始信息记录；不作为视频透明输出开关。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | asset://要求匹配provider；可信人像还要实际账户、时间和原始性证据；声明不能代替授权或信任资格。 |
| `assets[].provenance.provider` | 使用asset://时必需；其他可选 | `volcengine`，需符合实际来源 | 不得借用其他供应商或账户素材ID；字段匹配不证明账户归属。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

##### 生成步骤

1. 检查一张首帧图，明确它是首帧约束而非仅外观参考。
2. 本地图随请求发送或使用HTTPS/允许的已有火山素材ID；读取任务配置与cost.json并展示确认单（见调用示例）并确认。
3. 确认后submit、status、download；核对开头与首帧的对应及后续运动。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "image-to-video",
  "mode": "first-frame", // 必需：本能力固定image-to-video，模式为first-frame；切换操作须重新准备和确认
  "original_prompt": "以提供图片为首帧，产品保持原样，镜头缓慢向前推进，背景自然产生轻微景深变化。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "以提供图片为首帧，产品保持原样，镜头缓慢向前推进，背景自然产生轻微景深变化。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 4, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": false, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/first.png", // 必需：本地绝对路径或HTTPS；视频任务还允许已有火山asset://；本地文件提交时内存编码Base64
      "purpose": "严格首帧", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "first_frame", // 必需且按顺序：first_frame；首帧模式不可混用参考模式
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

除共用视频条件外，实际检查开头是否符合首帧需求。人物信任资格另行检查，不能通过裁剪或转码自行修复。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

#### 首尾帧生成

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `image-to-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `mode` | 必需 | `first-last-frame` | 当前模式；其他模式见所属能力的要求。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 明确首帧到尾帧的动作与过渡，保留输入顺序。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 省略对象时按当前模型及操作的字段默认值编译。 |
| `parameters.resolution` | 可选 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。 |
| `parameters.duration` | 可选 | `-1`自动，或`4..模型上限`的整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认adaptive；2.5本操作仅adaptive；2.0系列允许列出的比例。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`false` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 必需 | 恰好2张图片 | 按first_frame、last_frame顺序，只允许这两张图片。 |
| `assets[].kind` | 每项必需 | `image` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL、已有火山`asset://`ID | 视频仅HTTPS/已有素材ID，禁止本地路径及Base64；本地图片/音频提交时内存编码；当前无上传命令。 |
| `assets[].role` | 每项必需且顺序固定 | 依次`first_frame`、`last_frame` | 视频省略时默认reference_加kind；首帧/首尾帧不能使用该默认值。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.has_alpha` | 可选，仅记录图片信息 | 布尔`true`、`false`，需实际检测 | 仅作图片原始信息记录；不作为视频透明输出开关。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | asset://要求匹配provider；可信人像还要实际账户、时间和原始性证据；声明不能代替授权或信任资格。 |
| `assets[].provenance.provider` | 使用asset://时必需；其他可选 | `volcengine`，需符合实际来源 | 不得借用其他供应商或账户素材ID；字段匹配不证明账户归属。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

##### 生成步骤

1. 检查首尾图及先后顺序，确认它们需要严格作为端点，不与多模态参考混合。
2. 读取任务配置与cost.json并展示确认单（见调用示例），核对两张图职责、输出规格和费用后确认。
3. 确认后submit、status、download；检查开头、结尾及中间过渡。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：先检查图片和用途；本地图片随提交编码Base64，无需独立上传。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "image-to-video",
  "mode": "first-last-frame", // 必需：本能力固定image-to-video，模式为first-last-frame；切换操作须重新准备和确认
  "original_prompt": "从首帧的关闭包装平滑过渡到尾帧的打开包装，保持产品结构一致，镜头固定，不添加额外部件。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "从首帧的关闭包装平滑过渡到尾帧的打开包装，保持产品结构一致，镜头固定，不添加额外部件。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 4, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": false, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/closed.png", // 必需：本地绝对路径或HTTPS；视频任务还允许已有火山asset://；本地文件提交时内存编码Base64
      "purpose": "严格首帧", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "first_frame", // 必需且按顺序：first_frame；首帧模式不可混用参考模式
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    },
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/open.png", // 必需：本地绝对路径或HTTPS；视频任务还允许已有火山asset://；本地文件提交时内存编码Base64
      "purpose": "严格尾帧", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "last_frame", // 必需且按顺序：last_frame；首帧模式不可混用参考模式
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

核对两端图像与要求对应，并检查过渡中主体结构和身份；只满足其中一端不能称为符合全部需求。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

### 参考生视频

本能力统一使用 `operation="reference-to-video"`。

| 模式 | mode |
|---|---|
| 参考生成 | `reference` |
| 视频编辑 | `edit` |

#### 参考生成

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `reference-to-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `mode` | 必需 | `reference` | 当前模式；其他模式见所属能力的要求。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 逐项说明外观、动作、运镜或声音参考，不误写为严格编辑。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 省略对象时按当前模型及操作的字段默认值编译。 |
| `parameters.resolution` | 可选 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。 |
| `parameters.duration` | 可选 | `-1`自动，或`4..模型上限`的整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认adaptive；各视频模型允许列出的比例；adaptive缺少像素依据时费用未知。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`false` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 必需 | 至少1份参考素材 | 2.5最多图片30/视频10/音频10，2.0系列最多图片9/视频3/音频3；2.0系列不能纯音频参考。 |
| `assets[].kind` | 每项必需 | `image`、`video`、`audio` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL、已有火山`asset://`ID | 视频仅HTTPS/已有素材ID，禁止本地路径及Base64；本地图片/音频提交时内存编码；当前无上传命令。 |
| `assets[].role` | 可选 | `reference_image`、`reference_video`、`reference_audio`，按实际素材类型 | 视频省略时默认reference_加kind；首帧/首尾帧不能使用该默认值。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.duration` | 视频/音频每项必需 | 实测秒数，有限正数 | 2.5每段2..30秒，2.5编辑的视频每段4..30秒；2.0系列每段2..15秒；视频、音频各自合计不超过2.5的30秒或2.0系列15秒。 |
| `assets[].metadata.fps` | 输入视频确认前需核验 | 实际视频帧率`24..60` | CLI保留该元数据，不能据此声称脚本已自动检查帧率；仅视频适用。 |
| `assets[].metadata.has_alpha` | 可选，仅记录图片信息 | 布尔`true`、`false`，需实际检测 | 仅作图片原始信息记录；不作为视频透明输出开关。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | asset://要求匹配provider；可信人像还要实际账户、时间和原始性证据；声明不能代替授权或信任资格。 |
| `assets[].provenance.provider` | 使用asset://时必需；其他可选 | `volcengine`，需符合实际来源 | 不得借用其他供应商或账户素材ID；字段匹配不证明账户归属。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

##### 生成步骤

1. 检查各类素材，按各类型输入顺序编号并确定职责；2.5编译器按操作映射reference模式。
2. 视频先取得可用URL或已有素材ID；读取任务配置与cost.json并展示确认单（见调用示例），核验有视频费率和最低门槛，展示确认单。
3. 确认后submit、status、download；分别检查每种参考职责是否得到体现。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：先检查各素材并替换URL、元数据；视频不能本地Base64提交，当前无上传脚本，缺少可用视频来源时先停止补齐。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "reference-to-video",
  "mode": "reference", // 必需：本能力固定reference-to-video，模式为reference；切换操作须重新准备和确认
  "original_prompt": "参考图片1的产品外观与视频1的运镜，在明亮室内展示产品，主体保持图片1外观，不沿用视频1人物。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "参考图片1的产品外观与视频1的运镜，在明亮室内展示产品，主体保持图片1外观，不沿用视频1人物。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 4, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": false, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "image", // 必需：素材类型；本项为image；本能力允许的种类见运行要求
      "source": "https://media.example/product.png", // 必需：本地绝对路径或HTTPS；视频任务还允许已有火山asset://；本地文件提交时内存编码Base64
      "purpose": "参考产品外观", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "width": 1024, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 1024, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "has_alpha": false, // 透明编辑条件必需：依据实际Alpha检测填写true/false；不能根据扩展名推断
        "mime": "image/png" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "role": "reference_image", // 可选：默认reference_image；本项角色为reference_image，编辑/延长/参考只允许reference_*
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    },
    {
      "kind": "video", // 必需：素材类型；本项为video；本能力允许的种类见运行要求
      "source": "https://media.example/source.mp4", // 必需：HTTPS或已有火山asset://；拒绝本地视频/Base64；CLI没有上传/创建素材命令
      "role": "reference_video", // 可选：默认reference_video；本项角色为reference_video，编辑/延长/参考只允许reference_*
      "purpose": "只参考运镜，不采用原人物", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "duration": 8, // 视频/音频必需：每段实测秒数；2.5为2..30秒、编辑视频4..30秒，2.0系列2..15秒；每类合计不超过模型上限
        "width": 1280, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 720, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "fps": 30, // 确认前核验视频帧率24..60；CLI保留元数据但不自动证明满足帧率限制
        "bytes": 12000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "mime": "video/mp4" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    },
    {
      "kind": "audio", // 必需：素材类型；本项为audio；本能力允许的种类见运行要求
      "source": "https://media.example/ambience.mp3", // 必需：本地绝对路径或HTTPS；视频任务还允许已有火山asset://；本地文件提交时内存编码Base64
      "role": "reference_audio", // 可选：默认reference_audio；本项角色为reference_audio，编辑/延长/参考只允许reference_*
      "purpose": "参考环境音氛围，不复制对白", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "duration": 4, // 视频/音频必需：每段实测秒数；2.5为2..30秒、编辑视频4..30秒，2.0系列2..15秒；每类合计不超过模型上限
        "bytes": 1000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "mime": "audio/mpeg" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

不是原视频逐帧编辑承诺；检查新成片是否遵循约定参考维度。费用上界未知须明确接受，不能把公式下界当成总价。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

#### 视频编辑

##### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `reference-to-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `mode` | 必需 | `edit` | 当前模式；其他模式见所属能力的要求。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 明确修改/替换/删除/增加及保留项；2.0系列直接指明视频N；2.5多个候选源视频有歧义时先澄清。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 可选；省略按字段默认 | 对象；仅接受下列parameters子字段 | 省略对象时按当前模型及操作的字段默认值编译。 |
| `parameters.resolution` | 可选 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。 |
| `parameters.duration` | 可选 | 2.5仅`-1`；2.0系列为`-1`或`4..15`整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。2.5编辑只能-1且默认-1；2.0系列不套用此锁定。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认adaptive；2.5本操作仅adaptive；2.0系列允许列出的比例。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`false` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 必需 | 至少1份视频，可加图片/音频参考 | 同类型数量上限：2.5图30/视频10/音频10，2.0系列图9/视频3/音频3；必须明确目标视频。 |
| `assets[].kind` | 每项必需 | `image`、`video`、`audio` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL、已有火山`asset://`ID | 视频仅HTTPS/已有素材ID，禁止本地路径及Base64；本地图片/音频提交时内存编码；当前无上传命令。 |
| `assets[].role` | 可选 | `reference_image`、`reference_video`、`reference_audio`，按实际素材类型 | 视频省略时默认reference_加kind；首帧/首尾帧不能使用该默认值。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.duration` | 视频/音频每项必需 | 实测秒数，有限正数 | 2.5每段2..30秒，2.5编辑的视频每段4..30秒；2.0系列每段2..15秒；视频、音频各自合计不超过2.5的30秒或2.0系列15秒。 |
| `assets[].metadata.fps` | 输入视频确认前需核验 | 实际视频帧率`24..60` | CLI保留该元数据，不能据此声称脚本已自动检查帧率；仅视频适用。 |
| `assets[].metadata.has_alpha` | 可选，仅记录图片信息 | 布尔`true`、`false`，需实际检测 | 仅作图片原始信息记录；不作为视频透明输出开关。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | asset://要求匹配provider；可信人像还要实际账户、时间和原始性证据；声明不能代替授权或信任资格。 |
| `assets[].provenance.provider` | 使用asset://时必需；其他可选 | `volcengine`，需符合实际来源 | 不得借用其他供应商或账户素材ID；字段匹配不证明账户归属。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

##### 生成步骤

1. 检查目标视频和保留要求；2.5多视频输入由模型选择源视频，目标有歧义时确认前澄清。
2. 按所选模型解析编辑参数；视频不走Base64，取得可用来源后读取任务配置与cost.json并确认报价及编辑范围。
3. 确认后submit、status、download；对照原视频检查修改项及保留项。

##### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：先检查各素材并替换URL、元数据；视频不能本地Base64提交，当前无上传脚本，缺少可用视频来源时先停止补齐。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "reference-to-video",
  "mode": "edit", // 必需：本能力固定reference-to-video，模式为edit；切换操作须重新准备和确认
  "original_prompt": "编辑视频1：将背景墙改为浅蓝色，保留人物身份、动作、产品、镜头顺序和其他场景元素。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "编辑视频1：将背景墙改为浅蓝色，保留人物身份、动作、产品、镜头顺序和其他场景元素。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 8, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": false, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "video", // 必需：素材类型；本项为video；本能力允许的种类见运行要求
      "source": "https://media.example/source.mp4", // 必需：HTTPS或已有火山asset://；拒绝本地视频/Base64；CLI没有上传/创建素材命令
      "role": "reference_video", // 可选：默认reference_video；本项角色为reference_video，编辑/延长/参考只允许reference_*
      "purpose": "目标视频，保留场景与镜头顺序", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "duration": 8, // 视频/音频必需：每段实测秒数；2.5为2..30秒、编辑视频4..30秒，2.0系列2..15秒；每类合计不超过模型上限
        "width": 1280, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 720, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "fps": 30, // 确认前核验视频帧率24..60；CLI保留元数据但不自动证明满足帧率限制
        "bytes": 12000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "mime": "video/mp4" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

##### 成功、失败与重试

除共用视频成功条件外，检查目标正确、修改已生效、身份与事件顺序等保留项符合要求。2.5自动时长应检查实际成片，不能承诺逐帧完全相等。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。

### 视频延长

本能力对应 `operation=extend-video`。使用 `mode="before"` 向前延长或 `mode="after"` 向后延长，在提示词中明确相同方向。

#### 运行要求

本表覆盖下方JSON示例中的字段，包括整行注释的可选配置。`assets[]`表示数组中的每一项；“必需”区分CLI校验、流程保留与条件要求，不适用的可选字段应省略。所有模型均遵循64MB请求体上限，Base64会放大体积。

| 参数 | 必须性 | 可选项 / 默认值 | 模型差异与说明 |
|---|---|---|---|
| `provider` | 本文任务必须明确 | `volcengine` | CLI在部分配置下可推断，但火山独立计划应固定供应商。 |
| `model` | 必需 | `seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`，或对应准确ID | 准确ID见支持的模型表；不得静默更换用户指定模型。 |
| `operation` | 必需 | `extend-video` | 本能力固定值；更换操作需要重新准备计划。 |
| `mode` | 必需 | `after` | 当前模式；其他模式见所属能力的要求。 |
| `original_prompt` | 流程要求保留；CLI可省略 | 用户原始需求字符串 | 不作为最终提示词发送，不覆盖为优化后的文字。 |
| `prompt` | 必需 | 非空字符串 | 明确向前/向后延长、衔接内容、源视频和音轨要求；不把API时长设置与新增秒数混为一谈。 Seedance 2.5必须先实际应用sd25-pe。 |
| `parameters` | 必需 | 对象；仅接受下列parameters子字段 | 延长必须显式提供resolution和duration。 |
| `parameters.resolution` | 必需 | `480p`、`720p`、`1080p`、`4k`，按模型限制；默认`480p` | 2.5：480p/720p/1080p；2.0：四档；Fast/Mini：480p/720p。延长必须显式提供。 |
| `parameters.duration` | 必需 | `-1`自动，或`4..模型上限`的整数秒 | 2.5上限30秒、2.0系列15秒；普通默认4秒。延长必须显式提供，先核对时长语义。 |
| `parameters.ratio` | 可选 | `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive` | 本操作默认adaptive；2.5本操作仅adaptive；2.0系列允许列出的比例。 |
| `parameters.generate_audio` | 可选 | `true`、`false`；默认`true` | 根据对白、音轨和连续性要求选择；启用不证明音频质量或原音轨保留。 |
| `parameters.watermark` | 可选 | `true`、`false`；默认`true` | 控制视频平台水印；与图片默认值不同。 |
| `parameters.output_format` | 可选 | 2.5：`mp4`或`mov`；2.0系列：仅`mp4`；默认`mp4` | 2.0系列编译时不发送output_format字段，输出固定MP4。 |
| `parameters.return_last_frame` | 可选 | `true`、`false`；默认`false` | 启用时检查并下载响应中的last_frame_url。 |
| `parameters.execution_expires_after` | 可选 | 整数`3600..259200`秒；默认`172800` | 任务有效期；到期状态按失败恢复规则处理。 |
| `parameters.priority` | 可选 | 整数`0..9`；默认`0` | CLI接受取值不代表账户具有对应调度权益。 |
| `parameters.callback_url` | 可选 | HTTPS URL字符串或`null`；默认`null` | null不发送；仅填写受控地址，回调不等于媒体已下载交付。 |
| `parameters.safety_identifier` | 可选 | 1..64字符ASCII字符串或`null`；默认`null` | null不发送；不填写密钥或敏感信息。 |
| `assets` | 必需 | 至少1份视频，可加图片/音频参考 | 同类型数量上限：2.5图30/视频10/音频10，2.0系列图9/视频3/音频3；明确延长方向和源视频。 |
| `assets[].kind` | 每项必需 | `image`、`video`、`audio` | 实际允许类型由本能力决定，不能在图片生成或首尾帧模式加入音视频。 |
| `assets[].source` | 每项必需 | 本地图片/音频绝对路径、HTTPS URL、已有火山`asset://`ID | 视频仅HTTPS/已有素材ID，禁止本地路径及Base64；本地图片/音频提交时内存编码；当前无上传命令。 |
| `assets[].role` | 可选 | `reference_image`、`reference_video`、`reference_audio`，按实际素材类型 | 视频省略时默认reference_加kind；首帧/首尾帧不能使用该默认值。 |
| `assets[].purpose` | 每项必需 | 非空用途字符串；标注图可用`annotated edit region` | 说明提供主体、背景、外观、动作、镜头或声音等职责，保持输入顺序。 |
| `assets[].metadata` | 条件必需 | 真实测量信息对象 | 确认前核验尺寸、时长、大小和格式；远程不自动抓取，本地有ffprobe时可补充。不得用示例数值代替测量。 |
| `assets[].metadata.width` | 图片/视频确认前需取得 | 实际正数宽度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.height` | 图片/视频确认前需取得 | 实际正数高度，像素 | 图片/视频宽高300..6000、比例0.4..2.5；视频总像素407696..8295044。 |
| `assets[].metadata.bytes` | 确认前需取得；本地自动读取 | 实际正数字节数 | 图片≤30MB；视频任务输入图片须小于30MB；视频≤200MB；音频≤15MB。 |
| `assets[].metadata.duration` | 视频/音频每项必需 | 实测秒数，有限正数 | 2.5每段2..30秒，2.5编辑的视频每段4..30秒；2.0系列每段2..15秒；视频、音频各自合计不超过2.5的30秒或2.0系列15秒。 |
| `assets[].metadata.fps` | 输入视频确认前需核验 | 实际视频帧率`24..60` | CLI保留该元数据，不能据此声称脚本已自动检查帧率；仅视频适用。 |
| `assets[].metadata.has_alpha` | 可选，仅记录图片信息 | 布尔`true`、`false`，需实际检测 | 仅作图片原始信息记录；不作为视频透明输出开关。 |
| `assets[].metadata.mime` | 可选；本地自动识别 | 真实MIME，如`image/png`、`video/mp4`、`audio/mpeg` | 仅填写实际类型；音频仅WAV/MP3，拆分图片仅PNG/JPEG；MIME字符串不能单独证明内容格式正确。 |
| `assets[].provenance` | 条件必需 | 实际来源信息对象；普通公开参考不需要时可省略 | asset://要求匹配provider；可信人像还要实际账户、时间和原始性证据；声明不能代替授权或信任资格。 |
| `assets[].provenance.provider` | 使用asset://时必需；其他可选 | `volcengine`，需符合实际来源 | 不得借用其他供应商或账户素材ID；字段匹配不证明账户归属。 |
| `assets[].provenance.account_profile` | 需要账户来源证据时填写 | 真实账户标识字符串 | 不填写密钥；用于核对素材所属账户，不证明已获得使用授权。 |
| `assets[].provenance.generated_at` | 需要生成时间证据时填写 | 实际生成时间，带时区ISO 8601 | 可信原始人像按参考章节的30天窗口核验；普通素材不适用时删除，不伪造时间。 |
| `assets[].provenance.original` | 需要原始性证据时填写 | 布尔`true`、`false` | 记录是否保留原始字节；true本身不证明已获授权或满足供应商人像信任要求。 |
| `budget_cny` | 可选 | 有限正数人民币预算 | 仅按用户实际预算启用；上界未知或超预算时拒绝计划，不是供应商消费上限。 |
| `budget_usd` | 可选 | 有限正数美元预算 | 火山以人民币计价；美元预算比较必须有有效汇率。 |
| `fx` | 可选 | 仅含`usd_cny`和`expires_at`的对象 | 不提供时CLI可使用项目.env有效汇率；仅人民币报价不需要换算。 |
| `fx.usd_cny` | 提供fx时必需 | 有限正数，CNY/USD | 一美元兑换的人民币；必须真实核验，不能编造。 |
| `fx.expires_at` | 提供fx时必需 | 未来、带时区的ISO 8601时间 | 过期、缺失时区或无效值会被拒绝；不是价格快照的七天核验时间。 |
| `optimizer` | 2.5必需；2.0系列可省略 | 实际应用提示词优化skill后的记录对象 | Seedance 2.5先读取并实际应用sd25-pe，再记录状态。 |
| `optimizer.skill` | 2.5必需 | 2.5固定`sd25-pe` | 2.0系列无需套用该优化器。 |
| `optimizer.status` | 2.5必需 | 实际应用后填写`applied` | 不能仅为了通过编译器校验伪造执行记录。 |

#### 生成步骤

1. 检查源视频、延长方向与目标内容，明确API时长设置和用户期望片长的关系。
2. 显式填写resolution、duration及音频要求；读取任务配置与cost.json并展示确认单（见调用示例），报价与连续性要求一并确认。
3. 确认后submit、status、download；检查衔接、实际时长、身份和音轨连续性。

#### 调用示例

第一步：在项目目录设定技能路径和新的临时工作目录，运行环境检查。项目 `.env` 需要 `VOLCENGINE_API_KEY`；不要把密钥写进请求。目录已存在或检查发现影响本任务的问题时先处理，不继续后续步骤。

```bash
SKILL="/Users/chenyu/.codex/skills/richmedia-creator"
WORK="$(TZ=Asia/Shanghai date +/tmp/richmedia-%Y%m%d%H%M%S)"
mkdir -m 700 "$WORK"
python3 "$SKILL/scripts/media.py" check
```

仅当缺少当前任务依赖时运行 `python3 "$SKILL/scripts/media.py" doctor --dependencies`，需要汇率时可用 `doctor --exchange-rate`，修复后再次 `check`。使用2.5时先实际应用sd25-pe，再填写下方注释中的optimizer；当前2.0示例不需该记录。

第二步：先检查各素材并替换URL、元数据；视频不能本地Base64提交，当前无上传脚本，缺少可用视频来源时先停止补齐。将下列注释版请求中的实际参数填写完整，**移除所有 `//` 注释后**保存为 `$WORK/task-spec.json`。启用整行注释的可选字段时补齐实际值并保持严格JSON语法，不要把 `<...>` 占位符提交给CLI。

```jsonc
{
  // 以下为可选的计划控制字段；整行注释表示默认不启用，不能把未知值写成null提交。
  // "budget_cny": 10, // 可选：正数人民币预算，10仅演示；上界未知或超预算时拒绝计划，不是服务端限额。
  // "budget_usd": 2, // 可选：正数美元预算，2仅演示；火山跨币种预算需要有效汇率，不需要时删除。
  // "fx": { // 可选汇率对象；不提供时CLI使用项目.env有效汇率，仅人民币报价不必配置。
  //   "usd_cny": <实际核验的有限正数>, // 必需子字段：一美元兑换的人民币，不使用猜测示例值。
  //   "expires_at": "<未来且带时区的ISO 8601时间>" // 必需子字段：过期或无时区会被拒绝。
  // },
  // "optimizer": { // 切换到Seedance 2.5时必需；其他模型可省略，不能为通过校验而虚构执行。
  //   "skill": "sd25-pe", // 2.5必需：实际应用的提示词优化skill名称。
  //   "status": "applied" // 2.5必需：仅在实际读取并应用后记录applied。
  // },
  "provider": "volcengine", // 必需：本示例固定volcengine；不能复用其他供应商密钥或素材ID
  "model": "seedance-2.0", // 必需：seedance-2.5、seedance-2.0、seedance-2.0-fast、seedance-2.0-mini，或对应准确ID；用户指定模型不得静默更换
  "operation": "extend-video",
  "mode": "after", // 必需：before 向前延长，after 向后延长；须与提示词一致
  "original_prompt": "向后延长视频1，延续原有场景、动作方向、镜头运动和音轨，人物继续向前走，衔接自然。", // 流程要求保留：用户原始需求；不作为最终生成提示词发送
  "prompt": "向后延长视频1，延续原有场景、动作方向、镜头运动和音轨，人物继续向前走，衔接自然。", // 必需：优化后的完整提示词；2.5需先实际应用sd25-pe
  "parameters": { // 可配置参数对象：以下列出本类生成当前已开放的全部字段；省略字段按注释默认
    "resolution": "480p", // 延长必需，其他可省略默认480p；2.5支持480p/720p/1080p；2.0另支持4k；Fast/Mini仅480p/720p
    "duration": 12, // 延长必需，其他默认4秒；-1自动或4..上限的整数，2.5上限30、2.0系列15；2.5编辑必须-1
    "ratio": "16:9", // 可选：16:9、4:3、1:1、3:4、9:16、21:9、adaptive；文生默认16:9，带素材默认adaptive；2.5首帧/首尾帧/编辑/延长仅adaptive
    "generate_audio": true, // 可选布尔：普通任务默认false，延长默认true；按实际音频需求选择
    "watermark": true, // 可选布尔：默认true，控制平台水印
    "output_format": "mp4", // 可选：默认mp4；2.5支持mp4/mov；2.0系列固定mp4且编译时不发送此字段
    "return_last_frame": false, // 可选布尔：默认false；true请求末帧，下载时还需检查末帧产物
    "execution_expires_after": 172800, // 可选整数：任务有效期秒数，3600..259200，默认172800
    "priority": 0, // 可选整数：任务优先级0..9，默认0；取值被接受不证明账户具有对应权益
    "callback_url": null, // 可选：默认null不发送；启用时填受控的HTTPS回调URL，不能把回调当成本地已交付
    "safety_identifier": null // 可选：默认null不发送；启用时为1..64字符ASCII安全标识，不填秘密或敏感信息
  },
  "assets": [ // 必须提供本能力所需素材；每项字段说明见下；URL和元数据必须实际核验
    {
      "kind": "video", // 必需：素材类型；本项为video；本能力允许的种类见运行要求
      "source": "https://media.example/source.mp4", // 必需：HTTPS或已有火山asset://；拒绝本地视频/Base64；CLI没有上传/创建素材命令
      "role": "reference_video", // 可选：默认reference_video；本项角色为reference_video，编辑/延长/参考只允许reference_*
      "purpose": "需要向后延长的源视频", // 必需：说明素材用途；使用标注图进行局部编辑时对应项可设为annotated edit region
      "metadata": { // 条件必需：真实测量信息；远程不自动抓取，本地图片/音频有ffprobe时可补充；不要凭示例编造
        "duration": 8, // 视频/音频必需：每段实测秒数；2.5为2..30秒、编辑视频4..30秒，2.0系列2..15秒；每类合计不超过模型上限
        "width": 1280, // 确认前核验：实测宽度像素，正数；具体限制见本能力运行要求
        "height": 720, // 确认前核验：实测高度像素，正数；具体限制见本能力运行要求
        "fps": 30, // 确认前核验视频帧率24..60；CLI保留元数据但不自动证明满足帧率限制
        "bytes": 12000000, // 确认前核验：真实字节数；图片≤30MB、视频≤200MB、音频≤15MB；本地自动读取
        "mime": "video/mp4" // 可选实测MIME；本地文件自动识别；此值本身不证明真实文件格式正确
      },
      "provenance": { // 条件必需：asset://需匹配provider；可信人像需实际账户/时间/原始性证据，普通公开素材可省略
        "provider": "volcengine", // asset://必需匹配volcengine；普通素材可省略；匹配不代表已核验账户归属
        "account_profile": "<实际素材所属账户标识>", // 需账户来源时填写真实账户标识；可选，不填写API密钥
        "generated_at": "<实际生成时间，带时区ISO 8601>", // 需来源证据时填写实际生成时间，带时区ISO 8601；不适用时删除，不伪造时间
        "original": true // 需来源证据时填写原始性布尔值；true仅为记录，不自动证明人像可信或获授权
      }
    }
  ]
}
```

`service_tier=default`由编译器固定；2.5参考/编辑/延长的`omni_reference_task_type`由operation自动映射；2.0系列不发送该字段。`framespersecond`、draft、tools、seed、camera_fixed、frames不是可填写的请求参数，不要加入JSON。输入请求体不得超过64MB。

第三步：校验JSON语法，独立计算费用。成本脚本自行读取单价，结果保存在 `$WORK/volcengine/cost.json`；不额外生成计划。

```bash
python3 -m json.tool "$WORK/task-spec.json" > /dev/null
# 按主流程第4步完成成本计算后，读取该供应商的cost.json。
```

第四步：读取任务配置与cost.json，按[确认单模板](confirmation_cn.md)在final正文完整展示任务确认单，等待用户选择确认；核验远程素材及费用未知项。

```bash
```

第五步：收到用户实际选择确认后，仅提交一次。`--request`为本次任务配置，`--workdir`为init创建的工作目录，`--approval-text`记录实际选项或回复。费用上界未知时，先取得明确接受才可附加 `--accept-uncertain-cost`。参数变化后更新配置，计费输入变化时重新估价，并重新确认。

```bash
python3 "$SKILL/scripts/media.py" submit --request "$WORK/task-spec.json" --workdir "$WORK" --approval-text '<用户实际确认原文>'
```


第六步：查询视频任务状态。`--wait`可选0..45秒、默认0；queued/running时有界重复本命令，succeeded后进入下载。failed/expired/cancelled或未知结果按失败恢复规则处理，不重新提交。

```bash
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 45
```

第七步：只在succeeded且响应含主视频后下载。请求末帧时也检查末帧。下载失败可重复本命令，不重复生成。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

第八步：核对 对应提交记录中的 `result` 清单、实际文件与本能力成功条件。仅把已完成媒体复制到用户输出目录，保留原始字节并使用不冲突的文件名；过程文件留在临时目录。

#### 成功、失败与重试

不能仅因输出比源视频长就判定满足需求；检查衔接方向及内容、成片时长和音轨。需要拼接时另行明确后期任务，当前没有内置拼接命令。 失败及重试按共用判断表执行；任何再次付费的生成均需新计划与新确认。


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

官方指南提供可信模型原始素材、虚拟人像或经过认证/授权的真人素材等路径。不要假定任意真人面部直接上传都能使用。可信原始素材必须在 30 天内来自同一 Ark 账户和平台，包括指定 Seedance 原始含人脸视频或末帧，以及 Seedream 5.0 Lite/Pro/Flash 的**文生图**人脸图片。编辑、压缩、转发可能使信任资格失效。30 天信任窗口与 24 小时下载 URL 保留期不同。仅有来源记录并不构成授权，也不保证供应商接受。授权 IP 输入可能产生普通生成价格之外的附加费，应在批准前取得真实报价。

## 官方来源

- [Seedance 2.5 教程](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)
- [Seedance 2.5 提示词指南](https://docs.volcengine.com/docs/ark/seedance-2-5-prompt-guide?lang=zh)
- [Seedance 2.0 系列教程](https://docs.volcengine.com/docs/ark/seedance-2-0?lang=zh)
- [Seedance 2.0 提示词指南](https://docs.volcengine.com/docs/ark/seedance-2-0-prompt-guide?lang=zh)
- [视频生成教程与像素映射](https://docs.volcengine.com/docs/ark/video-generation-tutorial?lang=zh)
- [创建视频任务 API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)
- [查询视频任务 API](https://docs.volcengine.com/docs/ark/get-video-generation-task-api?lang=zh)
- [人像素材](https://docs.volcengine.com/docs/ark/seedance-portrait-asset-guide?lang=zh)
- [Seedream Pro/Flash 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)
- [交互式图片编辑](https://docs.volcengine.com/docs/ark/seedream-5-0-pro-editing-guide?lang=zh)
- [通用图片生成与模型特例](https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh)
- [图片 API](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh)
- [模型列表](https://docs.volcengine.com/docs/ark/model-list?lang=zh)





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