# Volcengine · 图层拆分（`operation=decompose-layers`）

## 生成要求

### 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | 图层拆分提示词，对应 `optimized_prompt`；提交时须与确认单一致。原生 API 可省略以自动识别主要元素，当前技能要求填写 |
| `size` | 必需 | `1K`、`1.5K`、`2K`、`auto`，不支持准确宽高像素。用户未指定时，默认 `1K`；底图保持原图比例，各图层保持对应元素的比例 |
| `assets` | 必需 | 按确认顺序提供的图片素材列表，数量、格式及填写要求见下方“素材要求” |

### 素材要求

- 支持 JPEG、PNG，每张图片不超过 30 MiB。
- 总像素为 262144～3600 万，宽高比为 1/16～16。
- 图层拆分只提供 1 张待拆分图片，不添加辅助参考图。
- 按确认顺序填写外层 `assets`，每项包含 `id`、`kind`、`source`、`purpose`，其中 `kind` 固定为 `image`。`source` 为本地绝对路径或可访问的 HTTPS URL；脚本按顺序处理素材，将本地图片编码为 Base64，并填入 `payload.image`。该字段留空数组或省略，不手工填写素材内容。

### 提示词优化

- 在生成确认单前，结合实际参考图使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求；确认后的生成步骤不再改写提示词。
- 用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。
- 明确需要拆分的对象，例如人物、标题文字、背景或装饰元素；用户未指定具体对象时，在提示词中表达拆分主要元素的要求。
- 可用自然语言定位，或使用用户已标注的参考图；使用 `<bbox>x1 y1 x2 y2</bbox>` 时，坐标须为 0～999 的归一化整数，框从左上到右下且面积非零，先核对实际区域，不编造坐标。图层拆分不使用 `<point>` 标签或独立 mask 参数。

## 生成步骤

以下步骤在用户需要图层拆分且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除示例中的全部注释后，将严格 JSON 直接追加到下一步命令的标准输入中。以下示例为拆分人物和标题文字；按实际需求提供一张待拆分图片，在最终提示词中说明需要拆分的对象。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "decompose-layers", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "拆出图片中的人物和标题文字", // 流程记录：用户原始提示词，不提交给供应商
     "assets": [ // 必需：本方案使用的素材，按输入顺序排列，由脚本解析，不直接提交给供应商
       {
         "id": "layer-source", // 必需：任务内唯一标识，供供应商引用；不是供应商素材 ID
         "kind": "image", // 必需：image、video 或 audio；本能力仅接受 image
         "source": "/absolute/path/poster.png", // 必需：执行前替换为实际 HTTPS URL 或本地绝对路径
         "purpose": "待拆分的海报，提取人物与标题文字" // 必需：素材用途，只在这里记录一次
       }
     ],
     "payload": { // 必需：火山引擎请求参数，脚本校验模型、参数及需求记录，解析外层 assets 并填充素材字段后提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       // 必需：准确模型 ID，按已确认方案二选一。
       // Pro：doubao-seedream-5-0-pro-260628，偏重图片质量。
       // Flash：doubao-seedream-5-0-flash-260915，偏重速度与成本。
       "model": "doubao-seedream-5-0-flash-260915",

       // 必需：明确需要拆分的对象；未指定具体对象时，描述拆分主要元素的要求。
       // 读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写。
       // 原生 API 可省略 prompt 自动识别主要元素；当前技能要求填写。
       // 需要区域定位时，在提示词中使用已核实的 bbox 坐标，无需额外的模式或 mask 字段。
       "prompt": "将图片1中的人物和标题文字分别拆分为独立图层。",

       // 由脚本根据外层 assets 按顺序填充；此处留空数组或省略，不手工填写素材。
       // 原生 API 支持单个图片字符串或仅含一项的数组，内容为图片 URL 或 Base64 数据。
       // 技能的本地绝对路径填在 assets.source，由脚本编码，不直接传给 API。
       "image": [],

       // 必需：1K、1.5K、2K、auto，不支持准确宽高像素。
       // 用户未指定时，技能默认 1K；API 默认 auto，根据输入图及各元素的尺寸适配。
       // 底图保持原图比例，各图层保持对应元素的比例，不保证各层具有相同宽高像素。
       "size": "1K",

       // 必需，固定 png：底图文件格式。
       // API 可选 png、jpeg，默认 jpeg；技能固定输出 PNG。
       // 此字段仅控制底图格式，前景图层始终输出带透明通道的 PNG。
       "output_format": "png",

       // 必需，固定 url：返回下载链接，生成后 24 小时内有效。
       // API 还支持 b64_json，直接返回 Base64 图片数据；API 默认 url。
       "response_format": "url",

       // 必需，固定 false：不添加可见水印。
       // API 可选 true、false，默认 true；true 在右下角添加“AI 生成”水印。
       "watermark": false,

       // 必需，固定 opaque：底图不启用透明背景，也是 API 默认值。
       // 前景图层仍带透明通道，无需设为 transparent。
       "background": "opaque",

       // 必需，固定 true：启用图层拆分，必须提供一张待拆分图片。
       // 返回一张底图和最多 16 张前景图层，实际数量由模型决定。
       // API 默认 false，表示普通图片生成，不进行图层拆分。
       "layer_decomposition": true

       // optimize_prompt_options 固定省略，不在此 JSON 中添加该字段。
       // API 的 mode 默认 standard；Pro 支持 standard、fast，Flash 仅支持 standard。
       // standard 偏重质量；fast 降低耗时，效果可能略低。省略字段不表示关闭服务端优化。
     }
   }
   ```

2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态，如果失败则提示用户，如果成功则继续交付。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将底图、图层和位置元数据 `layers.json` 交付到启动本技能时所在项目目录下的独立子目录，并返回交付文件清单。完成后按主流程核验内容并展示结果：检查拆分对象是否符合要求、前景图层是否带透明通道，以及图层位置和层级是否正确；实际图层数量由模型决定，一次请求返回一张底图和最多 16 张前景图层。

## 参考文档

[图片生成 API](https://console.volcengine.com/ark/region:cn-beijing/docs/image-generation-api.md)
[Seedream 5.0 Pro / Flash 教程](https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh)
