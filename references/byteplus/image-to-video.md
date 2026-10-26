# BytePlus · 图生视频（`operation=image-to-video`）

## 生成要求

### 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `content[].text` | 必需 | 视频生成提示词，对应 `optimized_prompt`；提交时须与确认单一致。官方允许图片输入时省略文本，当前技能要求填写 |
| `assets` | 必需，技能任务字段 | 首帧 1 张；首尾帧按首帧、尾帧顺序 2 张。提供本地绝对路径或 HTTPS URL，由脚本转换为 API 图片项 |
| `ratio` | 可选 | 2.5 默认且仅支持 `adaptive`，输出画幅保持首帧比例；2.0 系列默认 `adaptive`，也支持 `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`，指定比例不一致时会居中裁剪。当前技能固定 `adaptive` |
| `duration` | 可选 | 2.5 支持整数 4～30 秒或 `-1`，默认 `-1`；2.0 系列支持整数 4～15 秒或 `-1`，默认 5 秒。`-1` 表示模型在有效范围内自动选择时长 |
| `resolution` | 可选 | 2.5 支持 `480p`、`720p`、`1080p`；2.0 支持上述档位及 `4k`；2.0 Fast / Mini 支持 `480p`、`720p`。均默认 `720p` |
| `generate_audio` | 可选 | `true`：生成同步音频，包括人声、音效或音乐；`false`：无声视频。默认 `true`；生成音频为单声道 |

### 素材要求

- 支持 JPEG、PNG、WebP、BMP、TIFF、GIF、HEIC、HEIF；每张图片小于 30 MB，宽高均为 300～6000 px，宽高比为 0.4～2.5；完整 API 请求体不超过 64 MB。
- 首帧模式输入 1 张图；首尾帧模式输入 2 张图，首尾帧可以相同。比例不一致时以首帧为主，尾帧自动裁剪适配。
- 原生 API 图片项的 `type` 为 `image_url`，图片来源放在 `image_url.url`。API 支持公网 URL、`data:image/<格式>;base64,...` 和账户所属的 `asset://<ASSET_ID>`；本地路径须先编码，不能直接发送给 API。当前技能仅接受外层 `assets` 中的本地绝对路径或 HTTPS URL，不接受 `asset://` 或手填 Base64。
- 首帧的 `role` 为 `first_frame`，单首帧时官方允许省略，但建议显式填写；首尾帧模式必须分别填写 `first_frame`、`last_frame`。这些值位于图片项顶层，与 `image_url` 同级。
- 首帧、首尾帧和全模态参考是互斥场景，不混入 `reference_image`、参考视频或参考音频。

### 提示词优化

- 在生成确认单前，使用 `sd25-pe` 优化提示词，仅应用与当前视频能力相关的规则，最终提示词须符合所选模型的要求；确认后的生成步骤不再改写提示词。
- 用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。
- 结合实际首尾帧描述起始状态、结束状态、中间动作、事件顺序、运镜及声音；需要对白时，建议用双引号标出对白内容。首尾帧定义视频的起止画面，不改作人物、产品或风格参考。
- 比例、分辨率、总时长和声音开关通过接口参数落实，不追加到提示词。

## 生成步骤

以下步骤在用户需要图生视频且确认当前 BytePlus 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。移除示例中的全部注释后得到严格 JSON。以下示例为首尾帧；首帧模式只保留第一份外层素材，并同步调整提示词。下方 `payload` 的生成参数按官方 API 编写，图片项由脚本填充；脚本调用方式见脚本操作手册“提交生成”。

   ```jsonc
   {
     "provider": "byteplus", // 必需：供应商，供脚本选择对应适配器
     "operation": "image-to-video", // 必需：能力，供脚本选择接口及结果处理方式
     "original_prompt": "以两张熊猫图片作为首尾帧，生成熊猫向镜头挥手的视频，伴随鸟鸣和风声", // 流程记录：完整用户原话，不提交给供应商
     // 必需：首尾帧按顺序提供；首帧模式仅保留第一项，不填写 mode。
     "assets": [
       {
         "id": "first", // 必需：任务内唯一标识，不是供应商素材 ID
         "kind": "image", // 必需：本能力仅接受 image
         "source": "/absolute/path/first.png", // 必需：实际本地绝对路径或 HTTPS URL
         "purpose": "视频首帧，定义起始画面" // 必需：素材用途
       },
       {
         "id": "last", // 必需：任务内唯一标识，不是供应商素材 ID
         "kind": "image", // 必需：本能力仅接受 image
         "source": "/absolute/path/last.png", // 必需：实际本地绝对路径或 HTTPS URL
         "purpose": "视频尾帧，定义结束画面" // 必需：素材用途
       }
     ],
     "payload": {
       // 必需：准确模型 ID，按已确认方案选择。
       // 2.5：dreamina-seedance-2-5-260628
       // 2.0：dreamina-seedance-2-0-260128
       // 2.0 Fast：dreamina-seedance-2-0-fast-260128
       // 2.0 Mini：dreamina-seedance-2-0-mini-260615
       "model": "dreamina-seedance-2-5-260628",

       // 必需：本任务 JSON 仅填写文本项；图片项由脚本根据外层 assets 按顺序添加。
       // 第一张添加 role=first_frame，第二张添加 role=last_frame。
       "content": [
         {
           // 必需：文本项固定为 text。
           "type": "text",

           // 必需：描述主体、场景、动作顺序、运镜及声音。
           // 读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写。
           "text": "从首帧中熊猫的姿态自然开始，熊猫抬起前爪向镜头缓慢挥手，再自然过渡到尾帧指定的姿态和画面。保持熊猫外观、草地场景、光线和固定机位一致，伴随鸟鸣和轻微风声。"
         }
       ],

       // 可选：输出分辨率；2.5 和 2.0 系列默认 720p。
       // 2.5：480p、720p、1080p。
       // 2.0：480p、720p、1080p、4k。
       // 2.0 Fast / Mini：480p、720p。
       "resolution": "720p",

       // 可选：输出画幅；2.5 默认且仅支持 adaptive，保持首帧比例。
       // 2.0 系列默认 adaptive，由模型根据首帧在标准比例中选择；
       // 也可指定 16:9、4:3、1:1、3:4、9:16、21:9，必要时居中裁剪。
       // 当前技能固定 adaptive，不把 2.0 的 API 可选项描述为脚本已开放。
       "ratio": "adaptive",

       // 可选：输出秒数；本例明确生成 5 秒，不作为技能默认值。
       // 2.5：整数 4～30 或 -1，默认 -1。
       // 2.0 / Fast / Mini：整数 4～15 或 -1，默认 5。
       // -1：由模型在有效范围内自动选择时长。
       "duration": 5,

       // 可选：是否生成同步音频；默认 true。
       // true：根据提示词和画面生成匹配的人声、音效或音乐。
       // false：无声视频。生成的音频为单声道。
       "generate_audio": true,

       // 可选：是否添加可见水印；默认 false。
       // true：右下角添加“AI 生成”标识；false：不添加。
       "watermark": false,

       // 可选，仅 2.5：输出格式，默认 mp4。
       // mp4 便于播放与分发；mov 面向高色彩精度后期，部分播放器不兼容。
       // 使用 2.0 / Fast / Mini 时省略此字段。
       "output_format": "mp4",

       // 可选：是否额外返回末帧图片；默认 false。
       // true：通过查询接口获取末帧 JPEG，尺寸与视频一致，图片无水印。
       "return_last_frame": false,

       // 可选，仅 2.5：样片模式，默认 false。
       // true：生成预览样片，resolution 必须改为 480p。
       // false：正常生成视频。
       "draft": false,

       // 可选：任务过期时间，单位秒；从任务创建时间开始计算。
       // 范围 3600～259200，默认 172800（48 小时）。
       // 到期后终止任务并标记为 expired。
       "execution_expires_after": 172800,

       // 可选：排队优先级，范围 0～9，默认 0；越大越优先。
       // 仅影响同一 Endpoint 内的排队顺序，不中断正在运行的任务。
       "priority": 0

       // tools：当前官方创建任务文档未列出，技能也未实现视频联网搜索，不传。

       // 以下字段按需添加，注意补齐 JSON 逗号。

       // callback_url：接收任务状态变化通知的回调地址。
       // 示例："callback_url": "https://example.com/video-callback"

       // safety_identifier：终端用户稳定唯一标识，英文字符串，不超过 64 字符。
       // 官方建议使用用户 ID 等信息的哈希值，避免直接传个人信息。

       // service_tier：本例省略，不在此 JSON 中添加该字段。
       // API 默认 default（普通在线推理）；2.5 / 2.0 系列不支持 flex，无需切换服务等级。

       // seed、camera_fixed、frames：官方支持列表未包含 2.5 / 2.0 系列，不传。
       // omni_reference_task_type：用于全模态参考任务类型引导，首帧 / 首尾帧图生视频不传。
     }
   }
   ```

   原生 API 的 `payload.content` 图片项如下；脚本调用时不手工添加，由上述 `assets` 自动填充。首帧模式仅保留 `first_frame` 项，首尾帧模式保留两项，文本项仍放在同一 `content` 数组中。

   ```jsonc
   [
     {
       "type": "image_url", // 必需：图片项固定为 image_url
       "image_url": {
         // 必需：公网 URL、Base64 数据或 API 支持的账户素材 ID；不能直接填本地路径。
         "url": "https://example.com/first.png"
       },
       "role": "first_frame" // 首帧；单首帧时 API 可省略，脚本显式填写
     },
     {
       "type": "image_url", // 必需：图片项固定为 image_url
       "image_url": {
         "url": "https://example.com/last.png" // 必需：尾帧图片来源
       },
       "role": "last_frame" // 尾帧；首尾帧模式必须显式填写两个角色
     }
   ]
   ```

2. **调用脚本提交生成：** 脚本完成官方参数适配后，使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态；`queued`、`running` 表示尚未完成，继续查询同一任务，不重新提交。如果失败则提示用户，如果成功则继续交付。提交结果未知时按脚本操作手册的失败处理规则核对原任务。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终视频交付到启动本技能时所在项目目录下的独立子目录，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。视频核验时，检查实测分辨率、时长、音轨及画面、对白、音效、事件顺序和首尾状态是否符合确认要求。API 返回的整数时长可能与文件实测时长不同，以文件实测为准。

## 参考文档

[创建视频生成任务 API](https://ai.byteplus.com/ark/region:ap-southeast-1/docs/create-video-generation-task-api.md)
[Seedance 2.5 教程](https://docs.byteplus.com/en/docs/modelark/seedance-2-5)
