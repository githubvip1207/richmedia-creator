# BytePlus · 图生视频（`operation=image-to-video`）

## 生成要求

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

## 生成步骤

以下步骤在用户需要图生视频且确认当前 BytePlus 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除行尾注释后，将严格 JSON 直接追加到下一步命令的标准输入中。以下示例为首尾帧；首帧时外层 `assets` 只保留首图。

   ```jsonc
   {
     "provider": "byteplus", // 必需：供应商，供脚本选择对应适配器
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
     "payload": { // 必需：BytePlus 请求参数，脚本校验模型、参数及需求记录，解析外层 assets 并填充带角色的图片项后提交，不改写提示词；调用约定见脚本操作手册“提交生成”
       "model": "dreamina-seedance-2-5-260628", // 必需：准确模型 ID；使用 2.0 系列时替换为对应 ID
       "content": [ // 必需：仅填写文本项；图片项由 Python 根据外层 assets 按顺序添加
         {
           "type": "text", // 固定：文本提示词
           "text": "熊猫向镜头挥手" // 必需：读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写
         }
       ],
       "resolution": "480p", // 必需：所选模型支持的分辨率；用户未指定时默认 480p
       "ratio": "adaptive", // 固定：adaptive
       "duration": 4, // 必需：2.5 为整数 4～30 秒或 -1，2.0 系列为整数 4～15 秒或 -1；默认 4 秒
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

视频核验时，检查实测分辨率、时长、音轨及画面、对白、音效、首尾状态是否符合确认要求。API 返回的整数时长可能与文件实测时长不同，以文件实测为准。
