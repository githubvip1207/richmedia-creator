# Volcengine · 参考生视频（`operation=reference-to-video`）

## 生成要求

### 参数要求

| 参数 | 必须性 | 可选项 / 默认值 |
|---|---|---|
| `content[].text` | 必需 | 视频生成提示词，对应 `optimized_prompt`；提交时须与确认单一致。官方允许参考素材输入时省略文本，当前技能要求填写 |
| `mode` | 必需，技能任务字段 | `reference`：参考生成，借鉴素材生成新视频；`edit`：视频编辑，修改已有视频的内容。须与确认单一致，填写在任务 JSON 顶层，不提交给供应商 |
| `assets` | 必需，技能任务字段 | 至少 1 份图片、视频或音频；编辑模式必须包含待编辑视频。按确认顺序提供素材，由脚本转换为 API 素材项 |
| `ratio` | 可选 | 参考生成及 2.0 视频编辑支持 `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`，默认 `adaptive`；2.5 视频编辑默认且仅支持 `adaptive`，输出画幅保持目标视频比例 |
| `duration` | 可选 | 参考生成：2.5 支持整数 4～30 秒或 `-1`，默认 `-1`；2.0 系列支持整数 4～15 秒或 `-1`，默认 5 秒。`-1` 表示模型在有效范围内自动选择时长。2.5 视频编辑仅支持 `-1`，输出时长基本跟随目标视频，可能略短约 0.4 秒 |
| `resolution` | 可选 | 2.5 支持 `480p`、`720p`、`1080p`；2.0 支持上述档位及 `4k`；2.0 Fast / Mini 支持 `480p`、`720p`。均默认 `720p` |
| `generate_audio` | 可选 | `true`：生成同步音频，包括人声、音效或音乐；`false`：无声视频。默认 `true`；生成音频为单声道 |
| `omni_reference_task_type` | 可选，仅 2.5；技能要求明确填写 | 官方可选 `auto`（默认，自动判断）、`reference`（参考生成）、`edit`（视频编辑）、`extend`（视频延长）。本能力参考生成填写 `reference`，视频编辑填写 `edit`；视频延长使用独立的 `extend-video` 能力，并填写 `extend`。2.0 系列省略，通过提示词表达任务 |

### 素材要求

| 素材 | 格式及来源 | 尺寸、大小及时长 |
|---|---|---|
| 图片 | JPEG、PNG、WebP、BMP、TIFF、GIF、HEIC、HEIF；本地绝对路径或 HTTPS URL | 宽高均为 300～6000 px，宽高比为 0.4～2.5；每张小于 30 MB |
| 视频 | MP4、MOV，H.264 / H.265；HTTPS URL | 宽高均为 300～6000 px，宽高比为 0.4～2.5，总像素为 407696～8295044；帧率为 24～60 FPS；每段不超过 200 MB |
| 音频 | WAV、MP3；本地绝对路径或 HTTPS URL | 每段不超过 15 MB |

- 2.5 最多输入 30 张图片、10 段视频、10 段音频；视频和音频分别累计不超过 30 秒，单段为 2～30 秒。2.5 视频编辑模式的输入视频须为 4～30 秒。
- 2.0 系列最多输入 9 张图片、3 段视频、3 段音频；视频和音频分别累计不超过 15 秒，单段为 2～15 秒。2.5 支持仅参考音频；2.0 系列须至少有一张图片或一段视频。不要求三种素材全部提供。
- 原生 API 素材项的 `type` 分别为 `image_url`、`video_url`、`audio_url`，来源放在对应对象的 `url` 中。图片、音频支持公网 URL、Base64 数据和账户所属的 `asset://<ASSET_ID>`；视频支持公网 URL 和账户素材 ID，不支持 Base64。
- 本地路径不能直接发送给 API。当前技能仅接受外层 `assets` 中的本地图片、音频绝对路径或 HTTPS URL；视频须提供 HTTPS URL，不自动上传本地视频，不接受 `asset://` 或手填 Base64。脚本通过 `ffprobe` 实测素材信息，提交时编码本地图片、音频；完整 API 请求体不超过 64 MB。
- 图片、视频和音频的 `role` 必须分别为 `reference_image`、`reference_video`、`reference_audio`。这些值位于素材项顶层，与 `image_url`、`video_url`、`audio_url` 同级。
- 首帧、首尾帧和全模态参考是互斥场景，不混入 `first_frame`、`last_frame`。参考生成中的素材用于定义外观、场景、动作、运镜或声音，不直接作为视频的起止画面约束。

### 提示词优化

- 在生成确认单前，使用 `sd25-pe` 优化提示词，仅应用与当前视频能力相关的规则，最终提示词须符合所选模型的要求；确认后的生成步骤不再改写提示词。
- 用户明确要求不优化时，按主流程将完整拼接的 `original_prompt` 原样赋给 `optimized_prompt`，不调用本地提示词优化，也不主动启用供应商服务端提示词优化。如所选模型无法关闭服务端优化，先说明限制并取得用户接受，再提交。
- 参考生成须逐份说明素材用于主体外观、场景、动作、运镜或声音中的哪一项，明确新视频的主体、事件顺序与结局；需要对白时，建议用双引号标出对白内容。不把参考视频当成待编辑母版；可能被误判为编辑时，按 `sd25-pe` 规则加入“请注意这不是视频编辑。”。
- 视频编辑须明确唯一母版、修改范围、保持内容及原时间线；其他素材仅辅助指定修改。2.5 编辑的画幅与基本时长由目标视频决定，不另改画幅或时长。只编辑声音时明确修改与保留的声音、口型时点及全部保留画面；需要先修改再续接时分成独立任务。
- 比例、分辨率、总时长和声音开关通过接口参数落实，不追加到提示词。输入素材顺序与提示词编号保持一致。

## 生成步骤

以下步骤在用户需要参考生视频且确认当前 Volcengine 方案后执行。

1. **构建任务 JSON：** 参考如下示例，基于用户输入的参数和确认的供应商、模型和能力，生成任务 JSON 数据。以下为参考生成和视频编辑共用的 JSON 模板；按注释选择模式、删除不适用字段并移除全部注释后得到严格 JSON。根据实际需求提供图片、视频或音频，并同步调整提示词。下方 `payload` 的生成参数按官方 API 编写，素材项由脚本填充；脚本调用方式见脚本操作手册“提交生成”。

   ```jsonc
   {
     "provider": "volcengine", // 必需：供应商，供脚本选择对应适配器
     "operation": "reference-to-video", // 必需：能力，供脚本选择接口及结果处理方式
     "mode": "reference", // 必需：reference 参考生成、edit 视频编辑；须与确认单一致，不提交给供应商
     // 仅视频编辑使用：引用 assets 中待编辑母版的 id，须与提示词指定的目标一致。
     // 多视频编辑时必填；单视频编辑时可省略；mode=reference 时删除整个字段，不传空字符串或 null。
     // 仅供技能估价和规格核验，不提交给供应商，不放入 payload。
     "target_asset_id": "motion",
     "original_prompt": "参考熊猫图片、动作视频和环境声，生成熊猫在草地挥手的新视频", // 流程记录：完整用户原话，不提交给供应商
     // 必需：按确认顺序提供素材；不要求三种素材全部提供。
     "assets": [
       {
         "id": "panda", // 必需：任务内唯一标识，不是供应商素材 ID
         "kind": "image", // 必需：素材类型 image、video 或 audio
         "source": "/absolute/path/panda.png", // 必需：实际本地绝对路径或 HTTPS URL
         "purpose": "熊猫外观" // 必需：素材用途
       },
       {
         "id": "motion", // 必需：任务内唯一标识，不是供应商素材 ID
         "kind": "video", // 必需：素材类型 image、video 或 audio
         "source": "https://example.com/motion.mp4", // 必需：视频使用实际 HTTPS URL
         "purpose": "挥手动作与运镜" // 必需：素材用途；改为视频编辑时，明确此视频为待编辑母版
       },
       {
         "id": "ambience", // 必需：任务内唯一标识，不是供应商素材 ID
         "kind": "audio", // 必需：素材类型 image、video 或 audio
         "source": "/absolute/path/ambience.wav", // 必需：实际本地绝对路径或 HTTPS URL
         "purpose": "草地环境声" // 必需：素材用途
       }
     ],
     "payload": {
       // 必需：准确模型 ID，按已确认方案选择。
       // 2.5：doubao-seedance-2-5-260628
       // 2.0：doubao-seedance-2-0-260128
       // 2.0 Fast：doubao-seedance-2-0-fast-260128
       // 2.0 Mini：doubao-seedance-2-0-mini-260615
       "model": "doubao-seedance-2-5-260628",

       // 必需：本任务 JSON 仅填写文本项；素材项由脚本根据外层 assets 按顺序添加。
       // 图片、视频、音频分别添加 reference_image、reference_video、reference_audio 角色。
       "content": [
         {
           // 必需：文本项固定为 text。
           "type": "text",

           // 必需：描述主体、场景、动作顺序、运镜及声音。
           // 视频编辑时明确唯一母版、修改范围和保留内容；其他素材仅作为辅助参考。
           // 例如：编辑 @视频1，将背景替换为雪山，保留熊猫外观、动作、机位与原视频时间线。
           // 模型根据提示词选择待编辑视频，不读取 target_asset_id；视频、图片和音频分别按各自的输入顺序编号。
           // 读取当前 request.json 的 optimized_prompt，须与确认单一致，不再改写。
           "text": "图片1定义熊猫外观，视频1仅参考挥手动作与运镜，音频1用于参考草地环境声。生成熊猫在阳光草地上朝镜头挥手的新视频，保持主体外观一致，动作自然连贯。"
         }
       ],

       // 可选，仅 2.5：全模态任务类型引导，默认 auto。
       // auto：自动判断；reference：参考生成；edit：视频编辑；extend：视频延长。
       // 本能力下，参考生成填写 reference，视频编辑填写 edit。
       // 视频延长使用独立的 extend-video 能力，并填写 extend。
       // 技能内部 mode=before/after 表示延长方向，不直接作为本字段的取值。
       // 显式指定可提前检查参数限制，模型仍会结合提示词判断任务。
       // 2.0 / Fast / Mini 省略此字段，通过提示词明确任务。
       "omni_reference_task_type": "reference",

       // 可选：输出分辨率；2.5 和 2.0 系列默认 720p。
       // 2.5：480p、720p、1080p。
       // 2.0：480p、720p、1080p、4k。
       // 2.0 Fast / Mini：480p、720p。
       "resolution": "720p",

       // 可选：输出画幅；2.5 和 2.0 系列默认 adaptive。
       // 可选 16:9、4:3、1:1、3:4、9:16、21:9、adaptive。
       // 参考生成允许选择新的画幅，不要求保持参考图片或视频的比例。
       // 2.5 视频编辑默认且仅支持 adaptive，保持目标视频比例。
       "ratio": "16:9",

       // 可选：输出秒数；本例明确生成 5 秒，不作为技能默认值。
       // 2.5：整数 4～30 或 -1，默认 -1。
       // 2.0 / Fast / Mini：整数 4～15 或 -1，默认 5 秒。
       // -1：由模型在有效范围内自动选择时长。
       // 2.5 视频编辑仅支持 -1，时长基本跟随目标视频，可能略短约 0.4 秒。
       "duration": 5,

       // 可选：是否生成同步音频；默认 true。
       // true：根据提示词、画面及参考音频生成匹配的人声、音效或音乐。
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
       "priority": 0,

       // 本例沿用当前技能的 2.5 方案启用联网搜索，模型按需决定是否搜索。
       // 2.0 系列官方联网搜索仅支持纯文本输入，参考生视频必须改为 []。
       // 改为 [] 可关闭；实际次数见查询结果 usage.tool_usage.web_search。
       "tools": [
         {
           // 必需：工具类型，固定 web_search。
           "type": "web_search"
         }
       ]

       // 以下字段按需添加，注意补齐 JSON 逗号。

       // callback_url：接收任务状态变化通知的回调地址。
       // 示例："callback_url": "https://example.com/video-callback"

       // safety_identifier：终端用户稳定唯一标识，英文字符串，不超过 64 字符。
       // 官方建议使用用户 ID 等信息的哈希值，避免直接传个人信息。

       // service_tier：本例省略，不在此 JSON 中添加该字段。
       // 官方该字段支持列表仅列 1.0 Pro / Pro Fast；2.5 / 2.0 系列不使用。

       // seed、camera_fixed、frames：官方支持列表未包含 2.5 / 2.0 系列，不传。

     }
   }
   ```

   原生 API 的 `payload.content` 素材项如下；脚本调用时不手工添加，由上述 `assets` 自动填充。根据实际素材保留相应项，文本项仍放在同一 `content` 数组中。

   ```jsonc
   [
     {
       "type": "image_url", // 必需：图片项固定为 image_url
       "image_url": {
         // 必需：公网 URL、Base64 数据或 API 支持的账户素材 ID；不能直接填本地路径。
         "url": "https://example.com/panda.png"
       },
       "role": "reference_image" // 必需：参考图片角色，不使用 first_frame / last_frame
     },
     {
       "type": "video_url", // 必需：视频项固定为 video_url
       "video_url": {
         // 必需：公网 URL 或 API 支持的账户素材 ID；不支持本地路径或视频 Base64。
         "url": "https://example.com/motion.mp4"
       },
       "role": "reference_video" // 必需：参考视频角色，编辑母版也使用此值
     },
     {
       "type": "audio_url", // 必需：音频项固定为 audio_url
       "audio_url": {
         // 必需：公网 URL、Base64 数据或 API 支持的账户素材 ID；不能直接填本地路径。
         "url": "https://example.com/ambience.wav"
       },
       "role": "reference_audio" // 必需：参考音频角色
     }
   ]
   ```

2. **调用脚本提交生成：** 脚本完成官方参数适配后，使用上一步构建的 JSON 对象通过 `python3 "$SKILL/scripts/main.py" submit` 提交生成任务。使用本次任务文件目录 `$WORK` 作为 `--workdir`。脚本校验通过后将已确认的完整请求保存为 `$WORK/payload.json`；每次提交及其输出分别保存为 `submit-NNN.json` 和 `output-NNN/`。任务文件目录、提交序号及记录文件由脚本管理；记录返回的当前序号，并将提交文件路径记为 `$SUBMISSION`，供后续使用，不自行递增编号或拼接路径。命令示例见脚本操作手册。
3. **判断生成结果：** 调用 `python3 "$SKILL/scripts/main.py" status` 检查生成任务状态；`queued`、`running` 表示尚未完成，继续查询同一任务，不重新提交。如果失败则提示用户，如果成功则继续交付。提交结果未知时按脚本操作手册的失败处理规则核对原任务。
4. **交付结果：** 调用 `python3 "$SKILL/scripts/main.py" deliver` 获取并校验生成结果，将最终视频交付到启动本技能时所在项目目录下的独立子目录，并返回交付文件清单。完成后进入主流程的内容核验与结果展示步骤。视频核验时，检查实测分辨率、时长、音轨及画面、对白、音效、事件顺序是否符合确认要求。参考生成还须检查素材用途和主体对应关系；编辑模式还须检查修改区域、身份、保留画面、时间线和声音，2.5 编辑须比较目标视频与输出的画幅和实测时长。API 返回的整数时长可能与文件实测时长不同，以文件实测为准。生成内容不承诺像素级或音轨字节级复刻。

## 参考文档

[创建视频生成任务 API](https://console.volcengine.com/ark/region:cn-beijing/docs/create-video-generation-task-api.md)
[Seedance 2.5 教程](https://docs.volcengine.com/docs/ark/seedance-2-5?lang=zh)
