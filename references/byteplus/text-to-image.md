# BytePlus · 文生图（`operation=text-to-image`）

## 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | 描述图片内容、风格、构图及文字等要求；读取已确认的 `optimized_prompt`。支持中英文等语言；使用尺寸档位时，可在提示词中表达比例偏好，但不保证精确比例 |
| `size` | 必需 | `1K`、`1.5K`、`2K`，或准确像素 `宽x高`，例如 `1024x1024`。准确像素要求：宽×高为 921600～4624220，宽/高为 1/16～16；两项须同时满足。用户未指定时，默认 `1K` |

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。

## 生成步骤

以下步骤在用户需要文生图且确认当前 BytePlus 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除示例中的全部注释后，将严格 JSON 直接追加到下一步命令的标准输入中。

   ```jsonc
   {
     "provider": "byteplus", // 必需：供应商，供脚本选择对应适配器
     "operation": "text-to-image", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "生成一张正方形熊猫图片", // 流程记录：用户原始提示词，不提交给供应商
     "payload": { // 必需：BytePlus 请求参数，脚本校验模型、参数及需求记录后原样提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       // 必需：准确模型 ID，按已确认方案二选一。
       // Pro：dola-seedream-5-0-pro-260628，偏重图片质量。
       // Flash：dola-seedream-5-0-flash-260915，偏重速度与成本。
       "model": "dola-seedream-5-0-flash-260915",

       // 必需：描述图片内容、风格、构图及文字等要求。
       // 读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写。
       // 使用尺寸档位时，提示词中的比例为构图偏好，不保证精确比例。
       "prompt": "一只熊猫坐在草坡上，柔和自然光，写实摄影，不添加文字。构图比例偏好：1:1。",

       // 必需：1K、1.5K、2K，或准确像素，例如 1024x1024。
       // 准确像素须同时满足：宽×高为 921600～4624220，宽/高为 1/16～16。
       // 用户未指定时，技能默认 1K；API 默认 2K。文生图不使用 auto。
       "size": "1K",

       // 必需，固定 png：图片文件格式。
       // API 可选 png、jpeg，默认 jpeg；技能固定输出 PNG。
       "output_format": "png",

       // 必需，固定 url：返回下载链接，生成后 24 小时内有效。
       // API 还支持 b64_json，直接返回 Base64 图片数据；API 默认 url。
       "response_format": "url",

       // 必需，固定 false：不添加可见水印。
       // API 可选 true、false，默认 true；true 在右下角添加“AI 生成”水印。
       "watermark": false,

       // 必需，固定 opaque：不透明背景，也是 API 默认值。
       // API 的 transparent 仅适用于输入一张带透明通道图片的图生图，且须输出 PNG。
       // 本能力为文生图，不使用 transparent。
       "background": "opaque",

       // 必需，固定 false：普通图片生成，也是 API 默认值。
       // true 为图层拆分，必须提供一张输入图片，不适用于本例文生图。
       "layer_decomposition": false

       // optimize_prompt_options 固定省略，不在此 JSON 中添加该字段。
       // API 的 mode 默认 standard；Pro 支持 standard、fast，Flash 仅支持 standard。
       // standard 偏重质量；fast 降低耗时，效果可能略低。省略字段不表示关闭服务端优化。
     }
   }
   ```
2. **调用脚本提交生成：** 使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态，如果失败则提示用户，如果成功则继续交付。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终媒体交付到启动本技能时所在的当前项目目录，图层拆分同时交付位置元数据，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。

参数及模型差异依据：[图片生成 API](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/image-generation-api.md)、[Seedream 5.0 Pro / Flash 教程](https://docs.byteplus.com/en/docs/modelark/seedream-5-0-pro)。
