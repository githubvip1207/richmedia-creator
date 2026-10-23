# CLI 与请求结构

成本JSON包含任务参数和 `assets` 数组，每项可带素材标识 `id`，并包含 `kind` 与绝对文件路径或HTTPS URL `source`。Python自行统计图片数量并通过 `ffprobe` 读取素材宽高、视频/音频时长；价格表按 `provider` 自动读取，不传单价、价格文件、`input_images` 或 `input_video_seconds`。没有素材可省略 `assets`。脚本将完整结果同时写入cost.json并返回标准输出，完整记录只有 `input`、`calculation`、`result` 三个顶层字段。素材探测失败时停止，不以猜测值报价；远程素材读取可能联网，但不提交生成。

条件性计费依据放在 `estimate_context`：多视频估算目标用 `target_asset_index`，无法自动推导的输出像素用有依据的 `output_dimensions`，输入视频的最低计费门槛用 `minimum_billable_tokens` 和 `minimum_tokens_source`。这些字段不包含单价或素材实测值，具体填写条件见供应商成本规则。缺少必要依据时读取结果中的 `result.uncertainties`，不要把下界当作总价。

`cost.json` 用于复核计算过程：

- `input`：原始输入 JSON，保留素材 ID、地址、任务参数及补充依据。
- `calculation`：实际参与计算的数据。包括归一化供应商/模型/能力参数、素材数量及逐段时长、`assets` 中带 ID 和来源的实测宽高/时长、所选单价及来源/核验日期、计价规则、估算时间和结构版本、补充依据与汇率。图片记录像素档位、额外输入费用和输出数量/单价范围；视频记录输出宽高、尺寸推导依据、时长范围、帧率、公式 Token、最低计费 Token 及最终 Token。`steps` 逐项保存公式和中间值，`notes` 保存假设与限制；金额取整到小数点后 6 位。只有本次使用的费率写入文件，不复制无关模型的完整价格表。
- `result`：确认单使用的 `status`、`currency`、`amount: {min,max}` 和 `uncertainties: [{field,reason}]`；有效汇率存在时附带 `conversion`。`null` 表示未知，不等于零。

核验时按 `calculation.assets` 检查素材，按所选费率和 `steps` 重算分项，再比对 `result.amount`。提交读取已保存结果及计费依据，不重新报价；参数变化时重新估算并确认。



通过JSON标准输入调用 `media.py estimate-cost --workdir <工作目录>` 独立计算。每家分别执行，固定保存为 `<工作目录>/<供应商>/cost.json`。大模型读取各家结果生成确认单；用户选择确认后，submit直接读取所选供应商的cost.json。具体公式见[Volcengine 预估成本](volcengine_cn.md#预估成本)。


将 `SKILL` 设置为安装目录（通常为 `~/.codex/skills/richmedia-creator`）。示例要求 Python 3.9 及以上。使用init按系统本地时间创建私有目录 `/tmp/richmedia-YYYYMMDDHHmmss/`，例如 `/tmp/richmedia-20261021105342/`；如已存在则使用新的时间戳。每份请求、成本、状态文件、响应、清单及中间下载均存于其中。CLI 工作目录保持为项目目录，以加载 `.env`。只有最终媒体及图层拆分位置元数据放入用户选定的输出目录，默认当前项目目录。不要在项目或已安装技能中创建过程目录。

在项目目录运行时，CLI 从项目 `.env` 读取 `VOLCENGINE_API_KEY`、`BYTEPLUS_API_KEY`、`USD_CNY` 和 `USD_CNY_EXPIRES_AT`。赋值按数据解析，不执行文件、不打印密钥，业务配置不回退读取进程环境变量。其他 `.env` 键会被忽略。

```bash
python3 "$SKILL/scripts/media.py" init < /absolute/path/requirements.json
python3 "$SKILL/scripts/media.py" check
python3 "$SKILL/scripts/media.py" doctor
python3 "$SKILL/scripts/media.py" doctor --dependencies
python3 "$SKILL/scripts/media.py" doctor --exchange-rate
python3 "$SKILL/scripts/media.py" models --provider volcengine
python3 "$SKILL/scripts/media.py" models --provider byteplus
python3 "$SKILL/scripts/media.py" estimate-cost --workdir /tmp/richmedia-20261021105342 <<'JSON'
{
  "provider": "volcengine",
  "model": "seedream-5.0-flash",
  "operation": "text-to-image",
  "size": "1K"
}
JSON
```

## 运行目录与需求记录

```bash
python3 "$SKILL/scripts/media.py" init <<'JSON'
{
  "original_prompt": "生成一张正方形熊猫图片",
  "intent": {"operation": "text-to-image", "description": "根据文字生成熊猫图片"},
  "assets": [],
  "providers": {
    "volcengine": {
      "model": "doubao-seedream-5-0-flash-260915",
      "operation": "text-to-image",
      "parameters": {"size": "1K", "ratio": "1:1"},
      "assets": []
    }
  }
}
JSON
```

命令无需内容参数，JSON通过标准输入传入，不占用命令行参数长度。可用带引号的heredoc（如上）或已有文件重定向；带引号的JSON分隔符阻止Shell展开内容。目录时间戳使用系统本地时间。在 `/tmp` 原子创建权限0700的 `richmedia-YYYYMMDDHHmmss` 目录并写入request.json；同名文件、目录或符号链接存在时换用新的时间戳，不复用、覆盖已有任务。仅返回一个字段：

```json
{"workdir": "/tmp/richmedia-20261022153000"}
```

返回的workdir为绝对路径，示例时间仅用于说明格式。由大模型组织传入内容，init以UTF-8原样写入 `<workdir>/request.json`（文件权限0600）；仅返回workdir。

init先解析标准输入：空输入、非法JSON、非对象顶层或NaN/Infinity会在创建目录前报错。它不校验业务字段和供应商能力，不检查账户权限、不安装依赖、不联网，也不修改当前项目文件；写入失败会清理本次未完成的目录，不返回成功。后续保持项目目录为CLI工作目录以加载.env，将返回的workdir设置为WORK并复用，不重复初始化。

### 大模型维护的request.json

字段及示例见[主流程初始化](../SKILL_cn.md#3-准备运行环境)。统一使用该处的简化结构：素材完整信息集中在顶层，供应商项只用 `id` 引用；不重复保存模式或意图说明。初始化记录不直接作为生成接口请求体；后续按供应商能力文档构建实际请求。

### 传给submit的任务配置

需求记录不能直接传入submit。优化提示词后另存 `task-spec.json` 或 `<provider>-task-spec.json`，结构遵循下面的CLI请求说明；明确选中供应商并展开素材引用。保留原始request.json。不需要再生成计划或比价文件。

## 检查与修复

| 命令 | 行为 |
|---|---|
| `check` | 只读检查 `.env`、已配置供应商、汇率状态、sd25-pe 文件及 ffprobe 路径 |
| `doctor` | 安装缺失依赖，更新缺失或无效、过期的汇率，完成后重新检查 |
| `doctor --dependencies` | 仅修复缺失依赖，完成后重新检查 |
| `doctor --exchange-rate` | 强制获取最新汇率并更新 `.env`，完成后重新检查 |

`check` 不联网、不安装、不修改文件，也不验证密钥有效性、模型权限、余额或额度。API 密钥缺失时提示用户在本地配置，修复命令不会获取密钥。默认可选供应商只包含已配置密钥的供应商。

`doctor` 从官方 Ark 技能目录安装 sd25-pe；缺少 npx 时报告失败。缺少 ffprobe 时执行 `brew install ffmpeg`；没有 Homebrew 时提示通过系统包管理器安装 FFmpeg。安装后重新检查。安装器输出不直接回显。修复失败会在结果中报告；无法满足依赖要求时停止相关任务。

汇率固定请求 [Frankfurter 的 ECB USD/CNY 接口](https://api.frankfurter.dev/v2/providers/ecb/rate/usd/cny)，无需 API Key。检查响应币种、有限正数汇率和数据日期；过期时间为数据日期 UTC 零点起七天，不按下载时间重新延长旧数据。`.env` 中只更新 `USD_CNY` 和 `USD_CNY_EXPIRES_AT`，保留其他配置、注释及换行风格。失败时保留原值，不切换来源或编造汇率。

`USD_CNY_EXPIRES_AT` 使用带时区的 ISO 8601，例如 `2026-10-28T00:00:00+00:00`。缺失、无效或过期时，普通计划与比价只展示原币；需要换算预算时先修复汇率。旧 `USD_CNY_VERIFIED_ON`、`USD_CNY_SOURCE` 不再作为配置读取。更新 `.env` 后若要使用新汇率，重新估价并确认。

task-spec.json 执行配置结构如下（严格JSON，不含凭证或Base64）：

```json
{
  "provider": "volcengine",
  "model": "seedance-2.5",
  "operation": "text-to-video",
  "original_prompt": "一只熊猫在草坡上打滚",
  "prompt": "写实自然风格，熊猫幼崽在绿色草坡上笨拙地侧滚，最后趴在草地上。低机位中景，镜头轻微跟随。",
  "optimizer": {"skill": "sd25-pe", "status": "applied"},
  "parameters": {"ratio": "16:9"},
  "assets": []
}
```

图片任务在准备前选定 `parameters.ratio`，可选 21:9、16:9、3:2、4:3、1:1、3:4、2:3、9:16。适配器将其追加为构图提示，不保证准确像素比例。默认最低图片尺寸为 `1K`；每个付费计划对应一次输出请求。

为已准备请求生成 cURL 时，用 `compile_request` 编译任务配置并准确复制返回的 `payload_template` 与提示词；已有提交则读取 `submit-NNN.json` 的 `execution.compiled`。不要把 `1K` 加比例自行转换为假定像素，也不要更改 `output_format`、`watermark` 等字段。Seedream 5.0 Pro/Flash 准确尺寸必须满足官方总像素 921600..4624220、比例 1/16..16：例如 1024x768 低于最低值，而 1152x864 是有效的 4:3、1K 参考映射。每次请求返回一张图片，不支持 `n` 或顺序组图输出。原始 `curl` 不会自动读取项目 `.env`；构造 cURL 示例时应使用安全的纯数据加载器读取项目 `.env` 中所选供应商的密钥。不要 source `.env` 或打印其中的密钥。

代理必须实际应用 sd25-pe 后才写入最终 `prompt`。省略的生成或编辑设置按低成本规则解析。上例仅说明结构，不能证明已经执行优化或取得人工批准。

提交配置必须明确填写用户选中的 `provider`，模型ID必须属于该供应商。多家报价时由大模型分别保存任务配置，用户选择后仅提交对应的一份。

别名：`seedance-2.5`、`seedance-2.0`、`seedance-2.0-fast`、`seedance-2.0-mini`、`seedream-5.0-pro`、`seedream-5.0-flash`。也接受模型目录中的准确版本 ID。

操作与素材要求：

| operation | mode | 素材 / Assets |
|---|---|---|
| `text-to-image` | — | 无 / None |
| `image-to-image` | — | 1～10 张图片 / 1–10 images |
| `decompose-layers` | — | 1 张图片 / 1 image |
| `text-to-video` | — | 无 / None |
| `image-to-video` | `first-frame`、`first-last-frame` | 首帧 1 张、首尾帧按顺序 2 张 / 1 first frame or 2 ordered frames |
| `reference-to-video` | `reference`、`edit` | 必须有参考素材；编辑必须有视频 / References required; editing needs video |
| `extend-video` | `before`、`after` | 必须有视频 / Video required |

每种素材内部保留顺序。单条素材结构：

```json
{
  "kind": "video",
  "source": "https://your-approved-storage.example/reference.mp4",
  "role": "reference_video",
  "purpose": "参考动作和运镜；不采用原视频人物外观",
  "metadata": {"duration": 8.0, "width": 1280, "height": 720, "bytes": 12000000},
  "provenance": {"provider": "volcengine", "account_profile": "my-ark-profile", "generated_at": "2026-10-21T10:00:00+08:00", "original": true}
}
```

`source` 接受本地图片或音频的绝对路径（仅在提交时于内存中转为 Base64）、HTTPS URL，以及已有且属于该供应商的 `asset://` ID。本技能支持本地图片或音频的 Base64 输入路径，但**没有**实现任何一家供应商的上传 API，也不创建 `asset://` ID；应另行通过目标供应商或获准存储上传，再用 URL 或对应供应商素材 ID 重新制定计划。这些任务 API 的**视频输入不支持 Base64**。本技能绝不会暗中上传至公共存储。素材 ID 不是提示词引用，应使用 图片1/视频1/音频1。

本地文件会获取 SHA256；有 ffprobe 时也获取元数据。`ffprobe` 为可选工具，不自动安装。远程元数据必须来自检查或用户提供的实测信息，不得编造时长或尺寸。透明图片要求从实际输入验证 `metadata.has_alpha=true`。CLI 不固定远程 URL/ID 对应文件的字节；内容发生变化时应重新检查和确认。本地视频路径会在联网前被拒绝。

展示 `任务确认单`，并**收到用户对当前供应商的选择和确认后**：

```bash
python3 "$SKILL/scripts/media.py" submit --workdir /tmp/richmedia-20261021105342 \
  --request /tmp/richmedia-20261021105342/task-spec.json --approval-text '<actual user confirmation>'
python3 "$SKILL/scripts/media.py" status --submission /tmp/richmedia-20261021105342/submit-001.json --wait 45
python3 "$SKILL/scripts/media.py" download --submission /tmp/richmedia-20261021105342/submit-001.json
```

`--request` 指向选中供应商的完整任务配置，`--workdir` 是init创建的原工作目录。`--approval-text` 记录用户实际选项或回复。费用上界未知时，先取得明确接受才可使用 `--accept-uncertain-cost`。参数不能代替真实用户确认。

`attach-task --submission <submit-NNN.json> --task-id ...` 在提交结果不明时关联经过独立核对的已有视频任务；它验证 ID 和模型，但不能证明任务与准确提示词对应，因此还需在控制台核对创建时间和素材。它不执行付费生成。将 `request.json`、可选的 `task-spec.json`、各家 `cost.json`、`submit-NNN.json` 和 `outputs/` 一并保留于临时工作目录。下载后仅将完整媒体以明确且不冲突的名称复制到最终目录，不修改字节；清单与过程文件保留在 `/tmp`。图层拆分还需交付位置元数据。失败或结果未知时保留恢复状态；系统可能清理 `/tmp`，状态缺失不授权再次付费。原始响应可能含临时签名结果 URL，不要把这些 URL 或 Base64 粘贴到聊天日志，使用最终本地文件链接。

局部编辑时，先扣除画布偏移并处理缩放，再按 `round(pixel / displayed_image_dimension * 1000)` 将图片局部像素坐标归一化，限制在 0..999。提示词使用 `<point>x y</point>` 或 `<bbox>x1 y1 x2 y2</bbox>`。没有内置交互画布。

增加供应商时，需添加经审查的模型能力与价格、`scripts/providers/` 下的传输适配器、操作编译与路由，以及有意义的模拟集成测试。共享面向用户的确认机制与单次提交持久化逻辑。不要假定其他供应商与 Ark 使用相同端点、角色名、计费或异步状态。

## 多供应商报价与选择

分别调用 `estimate-cost`，每家成本保存在 `<workdir>/<供应商>/cost.json`。大模型结合各家任务配置汇总确认单，不生成单独的比价文件。供应商的模型、素材来源、价格和汇率分别核验；不同币种没有有效换算时不比较数字大小。

用户实际选择并确认后，将任务 JSON 通过标准输入传给 `submit`（也可使用 `--request` 读取文件）。脚本返回 `{"submission":"/absolute/path/submit-001.json"}`。该文件保留原始输入，顶层 `response` 保存生成接口响应，`execution` 保存执行与恢复状态，`queries` 保留每次查询的请求和响应，`result` 保存下载清单。后续使用 `status|download|attach-task --submission <该文件路径>`，可以单独操作任一次历史提交。每次确认只提交一次；前次任务进入明确终态并取得新的用户确认后，可在同一目录继续提交，编号递增。查询或下载重试不发起生成。媒体保存到 `outputs/submit-NNN/`；不另建状态、响应或清单 JSON 文件。

媒体 URL 下载使用 Python urllib：套接字超时 120 秒，每次读取 64 KiB；传输错误、不完整传输及 HTTP 408/429/500/502/503/504 最多尝试三次，退避等待 2/4 秒。每次重新写入临时文件，没有实现 Range 断点续传。其他 HTTP 错误立即停止。这些重试仅适用于媒体 GET，绝不用于付费生成 POST。

使用持久化 Codex 执行规则时，直接调用已安装 CLI：`python3 /Users/chenyu/.codex/skills/richmedia-creator/scripts/media.py submit|status|download ...`；每次只使用一个真实子命令，不加 Shell 包装或内联 Python。加载规则后，匹配的允许规则可避免重复执行提示，但托管限制仍然生效。执行授权绝不代替付费 POST 所需的当前任务确认与供应商选择。
