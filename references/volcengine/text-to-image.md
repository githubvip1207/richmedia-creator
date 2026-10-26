# Volcengine · 文生图（`operation=text-to-image`）

## 生成要求

- 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `prompt` | 必需 | |
| `size` | 必需 | 参考模型列表中的尺寸约束；用户未指定时默认最小尺寸；已指定时按用户要求 |

- 提示词优化

在主流程第 2 步落实本节生成要求时确定最终提示词，供估价和确认单使用；以下生成步骤只使用已确认的最终提示词，不再改写。
本能力要求使用 `sd25-pe` 优化提示词，仅应用与当前图片能力相关的规则，最终提示词须符合所选模型的要求。用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。

## 生成步骤

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
