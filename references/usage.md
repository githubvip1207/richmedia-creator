# 脚本操作手册

## 当前适用范围

本手册用于解释支持的脚本功能和脚本运行指南。所有脚本必须在包含 `.env` 文件的目录运行命令，且要求 Python 3.9 及以上。所有命令始终在启动本技能时的项目目录运行；`$WORK` 是任务文件目录，通过参数传入，不切换到该目录运行命令。将 `SKILL` 设置为实际安装目录：

```bash
SKILL="$HOME/.codex/skills/richmedia-creator"
```

## 命令总表

| 命令 | 输入 | 输出与用途 | 执行环境 |
|---|---|---|---|
| `init` | 标准输入中的需求 JSON 对象 | 创建临时任务文件目录、构造 `request.json` 文件，返回 `workdir` | 无限制 |
| `models [--provider volcengine或byteplus]` | 可选供应商标识 | 返回本地模型目录；不验证账户是否有调用权限 | 无限制 |
| `check` | 无 | 只读检查项目配置、供应商密钥是否已配置、汇率和依赖 | 无限制 |
| `doctor [--dependencies或--exchange-rate]` | 可选修复范围 | 修复依赖或汇率后重新检查 | 必须沙箱外 |
| `estimate-cost --workdir "$WORK"` | 标准输入中的成本 JSON 对象 | 保存当前需求的 `{供应商}-priceing.json`，返回 `workdir`、`quote` 及完整成本结果 | 无限制 |
| `submit --workdir "$WORK" --approval-text '用户实际确认原文'` | 标准输入中的任务 JSON；也可用 `--request` 指定文件 | 提交一次生成请求，返回 `submission` 路径 | 必须沙箱外 |
| `status --submission "$SUBMISSION"` | 已有提交文件路径 | 文生图仅返回本地执行状态，不向供应商查询，也不恢复未知结果 | 必须沙箱外 |
| `download --submission "$SUBMISSION"` | 已有提交文件路径 | 下载图片，更新提交文件内的结果清单 | 必须沙箱外 |

表中“必须沙箱外”的命令从首次执行起即使用沙箱外环境，不先在受限沙箱中尝试。通过 `exec_command` 执行时，设置 `sandbox_permissions: "require_escalated"`，并在 `justification` 中说明联网用途。

## 命令与文件对应

统一入口为 `scripts/main.py`，负责参数解析、命令分发和 JSON 输出。每个命令的实现放在 `scripts/commands/` 的同名模块中；Python 模块名将命令中的连字符替换为下划线。

| 命令 | 实现文件 |
|---|---|
| `init` | `scripts/commands/init.py` |
| `models` | `scripts/commands/models.py` |
| `check` | `scripts/commands/check.py` |
| `doctor` | `scripts/commands/doctor.py` |
| `estimate-cost` | `scripts/commands/estimate_cost.py` |
| `submit` | `scripts/commands/submit.py` |
| `status` | `scripts/commands/status.py` |
| `download` | `scripts/commands/download.py` |

`core/` 保存共用逻辑：`submission_store.py` 管理记录和锁，`dependencies.py` 检查依赖，`media_probe.py` 实测计费素材，`cost_quote.py` 组织及核对报价，`cost_formula.py` 计算费用。`providers/` 保存供应商适配和网络传输。命令均通过 `main.py` 调用，不直接执行模块文件。

## 配置与环境检查、修复

配置按数据读取，不执行 `.env`，不回退读取进程环境变量。缺少密钥时忽略对应供应商；不要将密钥写入任务文件或聊天。

| 项目 `.env` 配置项 | 用途 |
|---|---|
| `VOLCENGINE_API_KEY` | Volcengine 密钥 |
| `BYTEPLUS_API_KEY` | BytePlus 密钥 |
| `USD_CNY` | 1 美元对应的人民币金额 |
| `USD_CNY_EXPIRES_AT` | 汇率过期时间，使用带时区的 ISO 8601 |


```bash
python3 "$SKILL/scripts/main.py" check  # 不联网，不验证密钥有效性、模型权限、余额或额度。
python3 "$SKILL/scripts/main.py" doctor --dependencies  # 尝试通过 npx 安装缺失的 sd25-pe、通过 Homebrew 安装提供 ffprobe 的 FFmpeg，安装工具缺失或修复失败时会报告。
python3 "$SKILL/scripts/main.py" doctor --exchange-rate # 获取 USD/CNY，仅更新项目 `.env` 中两个汇率配置项。
```

## 初始化与运行目录

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `init`：

```bash
python3 "$SKILL/scripts/main.py" init <<'JSON'
<完整 JSON 对象，不含注释> 
JSON

# 将本次初始化返回的实际路径设置为 `$WORK`；重新理解意图后初始化会返回新的任务文件目录。
{"workdir": "/tmp/richmedia-creator-xxxxxx"}
```

## 成本计算

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `estimate-cost`分别估价。脚本将各供应商报价分别保存到当前 `$WORK` 下的 `{供应商}-priceing.json`，例如 `volcengine-priceing.json`、`byteplus-priceing.json`，并返回 `workdir`、报价文件绝对路径 `quote` 及 `input`、`calculation`、`result`。记录返回的任务文件目录及报价文件路径，不自行选择目录或覆盖其他需求的记录。

```bash
python3 "$SKILL/scripts/main.py" estimate-cost --workdir "$WORK" <<'JSON'
<完整 JSON 对象，不含注释> 
JSON

# 返回如下结果
{
    "workdir": "/tmp/richmedia-creator-xxxxxx",
    "quote": "/tmp/richmedia-creator-xxxxxx/volcengine-priceing.json",
    "input": {},
    "calculation": {},
    "result": {
      "status": "estimate", # estimate：估算值或范围；lower_bound：仅有费用下界；unknown：金额未知
      "currency": "CNY",    # 原币币种，确认单展示此币种和金额
      "amount": {           # 原币金额范围；示例为 Seedream Pro、1K、1 张输入图及 1 张输出图
          "min": 0.3,       # 费用下界；未知时为 null，不能写成 0
          "max": 0.3        # 费用上界；null 表示上界未知，不能把下界当总价
      },
      "uncertainties": []   # 不确定项数组；每项为 {"field":"缺失或未确定的字段", "reason":"费用不确定的原因"}
      # 有有效汇率时还包含 conversion：currency 为换算币种，amount 为换算后的 {min,max}，
      # usd_cny 为 1 美元对应人民币数值，expires_at 为汇率有效期；无有效汇率时不返回此字段。
      }
}
```

## 提交生成

任务 JSON 使用 `provider`、`operation`、`original_prompt` 和 `payload`。`payload` 按供应商 API 所需的字段和格式组织。当前文生图要求显式提供 `size` 及能力指南规定的固定参数；脚本验证后原样提交，不追加提示词或套用供应商默认输出规格。

以下为结构示例，实际输入字段以对应供应商能力章节为准：

```jsonc
{
  "provider": "volcengine", // 必需：用户选中的供应商
  "operation": "text-to-image", // 必需：当前能力
  "original_prompt": "生成一张正方形熊猫图片", // 流程记录：用户原始提示词
  "payload": { // 必需：按供应商 API 字段格式组织的请求参数；Python 脚本可能补充或修改字段
    "model": "doubao-seedream-5-0-flash-260915", // 必需：该供应商的准确模型 ID
    "prompt": "一只熊猫坐在草坡上，柔和自然光，写实摄影，不添加文字。构图比例偏好：1:1。", // 必需：当前 request.json 的 optimized_prompt，须与确认单一致
    ...  // 模型所需的其他参数
  }
}
```

选择并确认供应商后，提交上述完整任务 JSON。脚本在校验通过后将其保存为当前 `$WORK` 下的 `payload.json`；使用 `--request` 时由调用方先保存输入文件。提交只接受含供应商原生 `payload` 的格式，不接受旧版通用任务格式。提交前脚本核对 `request.json` 的原话、最终提示词、供应商方案及参数，并检查 `sd25-pe` 和 `ffprobe` 均已安装。脚本为每次提交分别保存 `submit-NNN.json`，包含本次实际请求及结果清单，并返回 `submission` 路径。NNN 从 `001` 开始递增。

```bash
# --approval-text` 必须记录真实回复。费用上界未知时，只有用户明确接受该不确定性后才能加 `--accept-uncertain-cost`。

# 方案 1，通过标准输入提交
python3 "$SKILL/scripts/main.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<已确认的完整任务 JSON，不含注释>
JSON

# 方案 2，将调用方已保存的任务 JSON 文件绝对路径记为 `$PAYLOAD` 后提交：
python3 "$SKILL/scripts/main.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' --request "$PAYLOAD"

# 返回如下结果
{"submission": "/tmp/richmedia-creator-xxxxxx/submit-001.json"}
```

## 查看执行状态

`$SUBMISSION` 使用 `submit` 返回的 `submission` 文件绝对路径。

```bash
# --wait 可选，取值 0～600 秒，默认 0；异步任务最多等待 10 分钟。
python3 "$SKILL/scripts/main.py" status --submission "$SUBMISSION" --wait 600

# 返回如下结果
{"success": true, "error": null}
```

## 下载结果

输出保存在当前 `$WORK` 下的 `output-NNN/`，与本次 `submit-NNN.json` 使用同一提交序号，以脚本返回的文件清单为准。URL 结果通过 HTTPS 下载；`b64_json` 结果由脚本解码保存。清单写入原提交文件的 `result.files`，包含本地路径、SHA256 及供应商来源信息。

```bash
python3 "$SKILL/scripts/main.py" download --submission "$SUBMISSION"
```

## 最终文件交付

下载并核验完成后，只将最终媒体复制到启动本技能时的当前项目目录；图层拆分同时复制位置元数据。保留临时目录中的请求、报价、提交记录和下载文件，不复制过程文件。例如启动目录是 `/project`，则按脚本返回的文件清单将最终文件复制到 `/project`，并提供交付文件的绝对路径链接或预览；同名文件使用不冲突的名称，避免覆盖。

## 运行文件及失败处理

以下是脚本管理的目录结构示意；每次重新理解意图对应一个新的 `$WORK`，`NNN` 对应该任务文件目录内的提交序号。实际访问使用脚本返回的路径，不由大模型按此表构造路径。

| 路径 | 内容 |
|---|---|
| `$WORK/request.json` | 当前需求的原始输入和需求记录；每个任务文件目录各有一个 |
| `$WORK/{供应商}-priceing.json` | 当前需求对应供应商的成本输入、计算过程和报价 |
| `$WORK/payload.json` | 提交校验通过后由脚本保存的完整提交请求 |
| `$WORK/submit-NNN.json` | 本次实际提交输入、`response`、`execution` 执行状态与 `result` 下载清单 |
| `$WORK/output-NNN/*` | 本次提交的下载文件及下载中的临时文件 |

供应商错误仅保留脱敏后的错误码、消息、请求 ID 及 HTTP 状态（若有），写入提交文件的 `response.error`；明确失败与结果未知分别处理，不因错误自动重发。

以下状态名来自提交文件的 `execution.state`；`status` 命令只返回 `success` 和 `error`。

| 状态或问题 | 处理 |
|---|---|
| 提交前参数或报价校验失败 | 修正原因，涉及方案变化时重新估价并确认，再提交 |
| `succeeded` | 调用 `download` 并核验内容，状态本身不代表交付完成 |
| `partial_failed` | 存在成功项时可以下载，但不能按全部成功交付；检查错误后决定下一步 |
| `failed` | 生成失败，无成功输出可下载；检查错误，需要再次生成时取得新的确认 |
| `rejected` | 根据已保存错误处理；需要重新生成时取得新的确认 |
| 供应商返回人脸、人像或肖像相关错误 | 保留提交记录及错误码，向用户说明供应商实际返回的错误；仅在错误发生后告知，不在生成前要求人像来源、授权认证或可信期限核验。本技能不代办供应商认证或素材接入；需要再次付费生成时重新估价并取得确认，不自动重试 |
| `submitting`、`submission_unknown`，或网络中断导致结果不明 | 保留记录，先在供应商控制台核对；文生图的 `status` 只读本地记录，不能消除不确定性。不要自动重新提交或切换供应商 |
| 下载中断或失败 | 对同一个 `$SUBMISSION` 再次运行 `download`，不重新生成；已完成且哈希匹配的文件可复用 |
| 图片内容不符合确认要求 | 说明具体差异；需要再次付费修正时重新确认 |

只有生成成功、`execution.download_complete=true`、实际文件与 `result.files` 清单一致，并通过已确认要求的内容核验，才算任务完成。`status` 返回 `success=true` 仅表示生成成功，不表示下载或交付完成。

媒体 GET 下载最多尝试三次，间隔 2/4 秒；付费生成 POST 不自动重试。下载没有 Range 断点续传。结果 URL 失效时先检查已保存文件或供应商恢复方式，不自动付费补生成。

临时目录可能被系统清理，文件缺失不代表允许再次付费。原始响应及清单可能含临时签名 URL，不将其或 Base64 正文粘贴到聊天中。
