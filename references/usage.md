# 脚本操作手册

## 当前适用范围

本文档用于解释支持的脚本功能和脚本运行指南。所有脚本必须在包含 `.env` 文件的目录运行命令，且要求 Python 3.9 及以上。所有命令始终在启动本技能时的项目目录运行；`$WORK` 是任务文件目录，仅用于保存本次任务文件，通过参数传入，不切换到该目录运行命令：

## 命令总表

| 命令 | 功能描述 | 执行环境 | 详细说明 |
|---|---|---|---|
| `init` | 读取需求 JSON，创建任务目录并保存 `request.json`，返回 `workdir` | 无限制 | [初始化与运行目录](#初始化与运行目录) |
| `check` | 只读检查项目配置、供应商凭证配置状态、汇率和依赖 | 无限制 | [配置与环境检查、修复](#配置与环境检查修复) |
| `doctor [--dependencies] [--exchange-rate] [--pricing]` | 按指定范围修复依赖、更新汇率或核对价格，并返回检查结果 | 必须沙箱外 | [配置与环境检查、修复](#配置与环境检查修复) |
| `cost --workdir "$WORK"` | 读取成本 JSON，估算费用并保存供应商报价文件 | 无限制 | [成本计算](#成本计算) |
| `submit --workdir "$WORK" --approval-text '用户实际确认原文'` | 按已确认方案提交一次生成请求，返回提交记录路径 | 必须沙箱外 | [提交生成](#提交生成) |
| `status --submission "$SUBMISSION"` | 查询已有任务的执行状态，返回是否成功及错误原因 | 必须沙箱外 | [查看执行状态](#查看执行状态) |
| `deliver --submission "$SUBMISSION"` | 获取、校验并交付最终媒体和图层元数据到当前项目目录 | 必须沙箱外 | [交付结果](#交付结果) |

表中“必须沙箱外”的命令从首次执行起即使用沙箱外环境，不先在受限沙箱中尝试。通过 `exec_command` 执行时，设置 `sandbox_permissions: "require_escalated"`，并在 `justification` 中说明联网用途。

## 命令与文件对应

统一入口为 `scripts/main.py`，负责参数解析、命令分发和 JSON 输出。每个命令的实现放在 `scripts/commands/` 的同名模块中；

```text
scripts/
├── main.py                         参数解析、命令分发和 JSON 输出
├── commands/                       接收命令，组织确认检查、锁和记录保存
│   ├── check.py / doctor.py         配置检查、依赖修复和汇率更新
│   ├── init.py                     初始化需求
│   ├── cost.py            调用选定供应商能力的估价入口，保存报价
│   ├── submit.py                   核对需求与报价，先记录 submitting，再提交一次
│   ├── status.py                   根据原提交记录分发查询、限时轮询、保存查询记录
│   └── deliver.py                  检查状态，调用能力交付，再发布最终文件
├── providers/
│   ├── __init__.py                 供应商注册、能力路由、请求与报价编译入口
│   ├── volcengine/                 火山引擎独立规则
│   │   ├── client.py               固定地址、独立凭证、请求与查询路径
│   │   ├── text_to_image.py         文生图
│   │   ├── image_to_image.py        图生图
│   │   ├── decompose_layers.py      图层拆分
│   │   ├── text_to_video.py         文生视频
│   │   ├── image_to_video.py        图生视频
│   │   ├── reference_to_video.py    参考生成与视频编辑
│   │   └── extend_video.py          视频延长
│   └── byteplus/                   同样按七种能力拆文件，独立维护模型与供应商规则
│       ├── client.py
│       └── 同名的七个能力模块
└── core/                           公共工具，按功能拆文件
    ├── validation.py               基础条件和数值校验
    ├── catalogs.py                 读取本地模型目录
    ├── operations.py               七种能力及模式标识
    ├── envfile.py                  项目 .env 解析
    ├── exchange_rate.py            汇率获取、有效性检查、原子更新配置
    ├── dependencies.py             必需依赖检查和安装
    ├── process.py                  外部工具执行
    ├── http.py                     HTTP、认证、防重定向、超时和错误脱敏
    ├── download.py                 已生成媒体的 GET 下载与有限重试
    ├── file_io.py                  私有 JSON 读写和原子替换
    ├── file_lock.py                进程间文件锁
    ├── file_hash.py                文件 SHA256
    ├── submission_store.py         提交路径、编号、时间和重复提交保护
    ├── asset_inspect.py            素材来源和本地文件检查
    ├── media_format.py             根据文件内容识别图片格式
    ├── media_base64.py             素材 Base64 编码及编码前哈希核对
    ├── media_probe.py              ffprobe 测量尺寸、时长、帧率等
    ├── media_validate.py           验证下载媒体可解码、尺寸及透明通道
    ├── payload_size.py             编码后请求大小预检
    ├── payload.py                  按已编译模板回填素材
    ├── cost_quote.py               通用计费字段提取、报价有效期与一致性核对
    ├── cost_record.py              通用报价审计结构；不包含供应商计费公式
    ├── layers.py                   图层几何校验和位置元数据
    ├── output_files.py             按能力给定的输出项下载、校验并保存缓存清单
    └── delivery_files.py           防覆盖发布最终文件、核对哈希并保存交付清单
```

### 能力模块的接口与数据依赖

每个能力模块包含本供应商模型的估价、请求规则、状态判断及输出解析。相同模型名不意味着可以共用另一供应商的模型 ID、价格或凭证。

| 接口 | 输入与职责 | 输出 |
|---|---|---|
| `cost(inputs, fx=None)` | 校验该能力及模型的计费参数，调用 `core.media_probe` 测量素材，按本模块公式估价 | `input`、`calculation`、`result` |
| `compile_request(spec, measured_assets=None)` | 按模型校验生成参数，将外层素材转换为图片或视频模板所需的结构，核对估价时记录的素材 | `compiled`：供应商、能力、模型、参数、素材、提示词和 `payload_template` |
| `build_payload(compiled)` | 调用公共工具编码本地素材，按模板回填供应商 API 字段 | 最终 API 正文，仅在内存中保留 Base64 |
| `submit(compiled, payload)` | 使用本供应商客户端执行一次生成 POST | 原始供应商响应；由命令层脱敏、保存 |
| `response_state(...)` | 按本能力的同步或异步响应规则判断状态 | 本地状态、usage 和错误信息 |
| `status(record, timeout=None)` | 消费同一份提交记录；图片解析同步响应，视频查询已保存的 `task_id` | 图片状态或视频查询响应；视频由 `response_state` 统一转换 |
| `deliver(record, record_path)` | 解析该能力的输出项，通过 `core` 获取、校验并保存文件；调用方持有任务锁 | 缓存文件及可选图层元数据清单 |

生命周期的调用与持久化关系：

```text
cost → 能力.cost → 保存 {供应商}-priceing.json
                                      ↓ 提交时复用并核对
submit → 能力.compile_request → 核对 request.json 和报价 → 能力.build_payload
       → 先保存 submit-NNN.json 的 submitting → 能力.submit
       → 保存 response、execution.compiled 和视频 task_id
                                      ↓ 后续始终读取同一提交
status → 从 execution.compiled 定位供应商和能力 → 能力.status
       → 保存独立 queries，不覆盖原始 POST response → 更新 execution
                                      ↓ 成功后交付
deliver → status → 能力.deliver → core 下载/验证/保存 output-NNN 缓存
        → core 发布至用户项目目录 → 保存 delivery 和 delivery_complete
```

`status` 和 `deliver` 不从当前需求、当前默认供应商或新模型配置重新推断任务身份。原有 `request.json`、报价、`submit-NNN.json` 和交付清单结构保持兼容；目录重构前已创建的提交可以继续查询和交付。结果未知时保留原提交，禁止因查询或下载失败自动重发生成。参数补全只执行已确认规则及素材回填；影响生成效果或费用的变更须重新估价和确认。

## 配置与环境检查、修复

配置按数据读取，不执行 `.env`，不回退读取进程环境变量。缺少密钥时忽略对应供应商；不要将密钥写入任务文件或聊天。

```bash
python3 "$SKILL/scripts/main.py" check  # 不联网，不验证密钥有效性、模型权限、余额或额度。
python3 "$SKILL/scripts/main.py" doctor --dependencies  # 尝试通过 npx 安装缺失的 sd25-pe、通过 Homebrew 安装提供 ffprobe 的 FFmpeg，安装工具缺失或修复失败时会报告。
python3 "$SKILL/scripts/main.py" doctor --exchange-rate # 获取 USD/CNY，仅更新项目 `.env` 中两个汇率配置项。
```

| 项目 `.env` 配置项 | 用途 |
|---|---|
| `VOLCENGINE_API_KEY` | Volcengine 密钥 |
| `BYTEPLUS_API_KEY` | BytePlus 密钥 |
| `USD_CNY` | 1 美元对应的人民币金额 |
| `USD_CNY_EXPIRES_AT` | 汇率过期时间，使用带时区的 ISO 8601 |

## 初始化与运行目录

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `init`。脚本将传入的保存到当前 `$WORK` 下的 `request.json`，并返回后续的任务文件目录 `workdir`。

```bash
python3 "$SKILL/scripts/main.py" init <<'JSON'
<完整 JSON 对象，不含注释> 
JSON

# 将本次初始化返回的实际路径设置为 `$WORK`；重新理解意图后初始化会返回新的任务文件目录。
{"workdir": "/tmp/richmedia-creator-xxxxxx"}
```

## 成本计算

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `cost`分别估价。脚本将各供应商报价分别保存到当前 `$WORK` 下的 `{供应商}-priceing.json`，例如 `volcengine-priceing.json`、`byteplus-priceing.json`。记录返回的报价文件路径以及报价结果。

```bash
python3 "$SKILL/scripts/main.py" cost --workdir "$WORK" <<'JSON'
<完整 JSON 对象，不含注释>
JSON

# 返回如下结果
{
  "cost_file": "/tmp/richmedia-creator-xxxxxx/volcengine-priceing.json", // string；本次保存的成本文件绝对路径，文件包含 input、calculation、result，不包含 cost_file。
  "input": {}, // 本次成本输入 JSON 的完整副本
  "calculation": {}, // 采用的计费参数、素材实测数据、价格快照、公式和假设
  "result": { // 用于展示和确认的费用估算结果。
    "status": "estimate", // string；当前为 estimate，表示按记录依据估算；不表示生成成功或实际已扣费。
    "currency": "CNY", // "CNY" | "USD"；估算原币，Volcengine 为 CNY，BytePlus 为 USD。
    "amount": { // object；所列假设下的原币费用范围，不是供应商保证的收费上下界。
      "min": 0.3, // number | null；估算范围起点；null 表示未知，不代表免费。
      "max": 0.3 // number | null；估算范围终点；不是扣款限额；历史报价可能为 null。
    },
    "uncertainties": [], // object[]；不确定项，每项 field 为涉及字段，reason 为原因；空数组不表示保证价格准确。
    "range_is_guaranteed": false, // false；金额范围不是实际收费的保证边界。
    "estimate_quality": "documented_estimate", // string，可选；视频为 documented_estimate 或 extrapolated，后者含未校准外推；图片通常省略。
    "conversion": { // object，可选；有有效汇率时返回另一币种的估算；无有效汇率时省略。
      "currency": "USD", // "CNY" | "USD"；换算目标币种，与上层原币不同。
      "amount": { // object；换算后的金额范围，币种为 conversion.currency。
        "min": 0.042857, // number | null；换算后的估算范围起点。
        "max": 0.042857 // number | null；换算后的估算范围终点，不是扣款限额。
      },
      "usd_cny": 7.0, // number；本次换算采用的 1 美元对应人民币金额，示意值。
      "expires_at": "2026-10-27T00:00:00+00:00" // string；汇率有效期，带时区的 ISO 8601 时间。
    }
  }
}
```

## 提交生成

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `submit`。脚本将传入的 JSON 保存到当前 `$WORK` 下的 `payload.json`，每次提交分别保存为 `submit-NNN.json`，记录请求、响应、执行状态及后续结果清单，并返回该文件的 `submission` 路径，NNN 从 `001` 开始递增。


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

## 交付结果

获取并校验指定提交的生成结果，将最终媒体保存到当前项目目录下的独立子目录；图层拆分同时交付 `layers.json`。命令始终在启动本技能时所在的项目目录运行。交付清单写入提交记录的 `delivery`，文件交付完成后设置 `execution.delivery_complete=true`；该标记不代表规格和内容验收通过，仍须按主流程第 7 步核验。重复执行时复用有效文件，不覆盖已有文件；交付失败后，对同一提交再次运行 `deliver` 恢复，不重新生成。请求、报价、响应等过程文件保留在任务目录。

```bash
python3 "$SKILL/scripts/main.py" deliver --submission "$SUBMISSION"

# 返回如下结果
{
  "directory": "/project/richmedia-task-submit-001", # 交付目录的绝对路径
  "files": [ # 最终媒体清单
    {
      "path": "/project/richmedia-task-submit-001/00-base.png", # 文件的绝对路径
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", # 文件的 SHA256
      "kind": "image", # 媒体类型
      "provider": "volcengine", # 供应商
      "model": "doubao-seedream-5-0-flash-260915" # 准确模型 ID
    }
  ],
  "delivered_at": "2026-10-24T13:00:00+00:00", # 交付时间，ISO 8601 格式
  "metadata": { # 仅图层拆分返回：位置元数据文件
    "path": "/project/richmedia-task-submit-001/layers.json", # 文件的绝对路径
    "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc" # 文件的 SHA256
  }
}
```

## 运行文件及失败处理

### 任务文件

每次重新理解意图后初始化新的任务目录 `$WORK`，`NNN` 为该目录内的提交序号。以下路径仅作结构示意，实际访问使用脚本返回的路径，不自行构造。

| 路径 | 内容 |
|---|---|
| `$WORK/request.json` | 当前需求的原始输入和需求记录 |
| `$WORK/{供应商}-priceing.json` | 对应供应商的成本输入、计算过程和报价 |
| `$WORK/payload.json` | 提交校验通过后保存的完整提交请求 |
| `$WORK/submit-NNN.json` | 本次提交的输入、响应、执行状态、缓存清单和交付清单 |
| `$WORK/output-NNN/*` | 本次提交的下载文件及下载中的临时文件 |

提交记录中，`response` 保存供应商响应，`execution` 保存执行状态，`result` 保存缓存清单，`delivery` 保存交付清单。供应商错误脱敏后写入 `response.error`，仅保留错误码、消息、请求 ID 及 HTTP 状态（若有）。

### 状态与异常处理

以下状态名来自提交记录的 `execution.state`；`status` 命令只返回 `success` 和 `error`。明确失败与结果未知分别处理，不因错误自动重发。

| 状态或问题 | 处理 |
|---|---|
| 提交前参数或报价校验失败 | 修正原因；涉及方案变化时重新估价并确认，再提交 |
| `succeeded` | 调用 `deliver` 完成交付，再核验内容 |
| `partial_failed` | 整次生成未成功，不执行完整交付；检查错误后决定下一步 |
| `failed` | 生成失败，无成功输出可下载；检查错误，再次生成须取得新的确认 |
| `rejected` | 根据已保存错误处理；重新生成须取得新的确认 |
| `submitting`、`submission_unknown`，或网络中断导致结果不明 | 保留提交记录，按对应能力指南核对是否已受理、生成或计费；结果明确前，不自动重新提交或切换供应商 |
| 获取或交付中断、失败 | 对同一个 `$SUBMISSION` 再次运行 `deliver`；复用已完成且哈希匹配的文件，不重新生成 |
| 图片或视频内容不符合确认要求 | 说明具体差异；需要再次付费修正时重新确认 |

供应商返回人脸、人像或肖像相关错误时，保留提交记录及错误码，向用户说明实际返回的错误。仅在错误发生后告知，不在生成前要求人像来源、授权认证或可信期限核验。本技能不代办供应商认证或素材接入；再次付费生成须重新估价并取得确认，不自动重试。

### 完成条件

同时满足以下条件，才算任务完成：

- 生成成功。
- `execution.delivery_complete=true`。
- 实际文件与 `delivery` 清单一致。
- 通过已确认要求的内容核验。

`status` 返回 `success=true` 仅表示生成成功，不表示下载或交付完成。结果交付必须使用 `deliver`，不得另写下载或复制代码绕过该命令。

### 注意事项

- 临时目录可能被系统清理，文件缺失不代表允许再次付费。
- 原始响应及清单可能含临时签名 URL，不将其或 Base64 正文粘贴到聊天中。
- 成本结果的解释及生成后费用核对，见对应供应商文档的“预估成本”章节。
- `doctor --pricing` 仅在官方单价完整解析通过后更新对应供应商快照；失败时保留原文件和核实日期。
