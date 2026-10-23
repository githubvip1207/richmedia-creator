# 脚本操作手册

## 当前适用范围

本手册用于解释支持的脚本功能和脚本运行指南。所有脚本必须在包含 `.env` 文件的目录运行命令，且要求 Python 3.9 及以上。将 `SKILL` 设置为实际安装目录：

```bash
SKILL="$HOME/.codex/skills/richmedia-creator"
```

## 命令总表

| 命令 | 输入 | 输出与用途 |
|---|---|---|
| `init` | 标准输入中的需求 JSON 对象 | 创建临时工作目录、构造 `request.json` 文件，返回 `workdir` |
| `models [--provider volcengine或byteplus]` | 可选供应商标识 | 返回本地模型目录；不验证账户是否有调用权限 |
| `check` | 无 | 只读检查项目配置、供应商密钥是否已配置、汇率和依赖 |
| `doctor [--dependencies或--exchange-rate]` | 可选修复范围 | 修复依赖或汇率后重新检查 |
| `estimate-cost --workdir "$WORK"` | 标准输入中的成本 JSON 对象 | 保存所选供应商的 `cost.json`，并返回完整结果 |
| `submit --workdir "$WORK" --approval-text '用户实际确认原文'` | 标准输入中的任务 JSON；也可用 `--request` 指定文件 | 提交一次生成请求，返回 `submission` 路径 |
| `status --submission "$SUBMISSION"` | 已有提交文件路径 | 文生图仅返回本地执行状态，不向供应商查询，也不恢复未知结果 |
| `download --submission "$SUBMISSION"` | 已有提交文件路径 | 下载图片，更新提交文件内的结果清单 |

## 配置与环境检查、修复

配置按数据读取，不执行 `.env`，不回退读取进程环境变量。缺少密钥时忽略对应供应商；不要将密钥写入任务文件或聊天。

| 项目 `.env` 配置项 | 用途 |
|---|---|
| `VOLCENGINE_API_KEY` | Volcengine 密钥 |
| `BYTEPLUS_API_KEY` | BytePlus 密钥 |
| `USD_CNY` | 1 美元对应的人民币金额 |
| `USD_CNY_EXPIRES_AT` | 汇率过期时间，使用带时区的 ISO 8601 |


```bash
python3 "$SKILL/scripts/media.py" check  # 不联网，不验证密钥有效性、模型权限、余额或额度。
python3 "$SKILL/scripts/media.py" doctor --dependencies  # 尝试通过 npx 安装缺失的 sd25-pe、通过 Homebrew 安装提供 ffprobe 的 FFmpeg，安装工具缺失或修复失败时会报告。
python3 "$SKILL/scripts/media.py" doctor --exchange-rate # 获取 USD/CNY，仅更新项目 `.env` 中两个汇率配置项。
```

## 初始化与运行目录

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `init`：

```bash
python3 "$SKILL/scripts/media.py" init <<'JSON'
<完整 JSON 对象，不含注释> 
JSON

# 返回如下结果，将实际返回路径设置为 `$WORK` 并在后续复用。
{"workdir": "/tmp/richmedia-20261022153000"}  
```

## 成本计算

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `estimate-cost`分别估价。估价结果将保存到 `$WORK/<供应商>/cost.json`，同时返回标准输出。

```bash
python3 "$SKILL/scripts/media.py" estimate-cost --workdir "$WORK" <<'JSON'
<完整 JSON 对象，不含注释> 
JSON

# 返回如下结果
{
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

任务 JSON 使用 `provider`、`operation`、`original_prompt` 和 `payload`。`payload` 按供应商 API 所需的字段和格式组织，但不一定是完整请求体；Python 脚本可能新增或修改字段，例如读取素材并进行 Base64 编码后填入请求。具体处理逻辑以 Python 脚本为准。

以下为结构示例，实际输入字段以对应供应商能力章节为准：

```jsonc
{
  "provider": "volcengine", // 必需：用户选中的供应商
  "operation": "text-to-image", // 必需：当前能力
  "original_prompt": "生成一张正方形熊猫图片", // 流程记录：用户原始提示词
  "payload": { // 必需：按供应商 API 字段格式组织的请求参数；Python 脚本可能补充或修改字段
    "model": "doubao-seedream-5-0-flash-260915", // 必需：该供应商的准确模型 ID
    "prompt": "一只熊猫坐在草坡上，柔和自然光，写实摄影，不添加文字。构图比例偏好：1:1。", // 必需：最终确认的提示词
    ...  // 模型所需的其他参数
  }
}
```

接收主流程组织的 JSON 对象，去除注释后通过标准输入传给 `submit` 完成任务提交，返回 `submission` 路径，该文件保存着任务 JSON 及结果清单。

```bash
# --approval-text` 必须记录真实回复。费用上界未知时，只有用户明确接受该不确定性后才能加 `--accept-uncertain-cost`。

# 方案 1，通过标准输入提交
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' <<'JSON'
<已确认的完整任务 JSON，不含注释>
JSON

# 方案 2，将 JSON 保存到 `$WORK/task-spec.json` 后提交：
python3 "$SKILL/scripts/media.py" submit --workdir "$WORK" --approval-text '<用户实际确认原文>' --request "$WORK/task-spec.json"

# 返回如下结果
{"submission": "/tmp/richmedia-20261022153000/submit-001.json"}
```

## 查看执行状态

`$SUBMISSION` 使用 `submit` 返回的 `submission` 文件绝对路径。

```bash
# --wait 可选，取值 0～600 秒，默认 0；异步任务最多等待 10 分钟。
python3 "$SKILL/scripts/media.py" status --submission "$SUBMISSION" --wait 600

# 返回如下结果
{"success": true, "error": null}
```

## 下载结果

图片保存在 `$WORK/outputs/submit-NNN/`。URL 结果通过 HTTPS 下载；`b64_json` 结果由脚本解码保存。清单写入原提交文件的 `result.files`，包含本地路径、SHA256 及供应商来源信息。

```bash
python3 "$SKILL/scripts/media.py" download --submission "$SUBMISSION"
```

## 运行文件及失败处理

| 路径 | 内容 |
|---|---|
| `$WORK/request.json` | 初始化的原始需求记录 |
| `$WORK/<供应商>/cost.json` | 各供应商的成本输入、计算过程和报价 |
| `$WORK/task-spec.json` | 可选：已确认的提交请求；也可直接用标准输入 |
| `$WORK/submit-NNN.json` | 原始提交输入、`response`、`execution` 执行状态与 `result` 下载清单 |
| `$WORK/outputs/submit-NNN/` | 对应提交的下载文件及下载中的临时文件 |

以下状态名来自提交文件的 `execution.state`；`status` 命令只返回 `success` 和 `error`。

| 状态或问题 | 处理 |
|---|---|
| 提交前参数或报价校验失败 | 修正原因，涉及方案变化时重新估价并确认，再提交 |
| `succeeded` | 调用 `download` 并核验内容，状态本身不代表交付完成 |
| `partial_failed` | 存在成功项时可以下载，但不能按全部成功交付；检查错误后决定下一步 |
| `failed` | 生成失败，无成功输出可下载；检查错误，需要再次生成时取得新的确认 |
| `rejected` | 根据已保存错误处理；需要重新生成时取得新的确认 |
| `submitting`、`submission_unknown`，或网络中断导致结果不明 | 保留记录，先在供应商控制台核对；文生图的 `status` 只读本地记录，不能消除不确定性。不要自动重新提交或切换供应商 |
| 下载中断或失败 | 对同一个 `$SUBMISSION` 再次运行 `download`，不重新生成；已完成且哈希匹配的文件可复用 |
| 图片内容不符合确认要求 | 说明具体差异；需要再次付费修正时重新确认 |

只有生成成功、`execution.download_complete=true`、实际文件与 `result.files` 清单一致，并通过已确认要求的内容核验，才算任务完成。`status` 返回 `success=true` 仅表示生成成功，不表示下载或交付完成。

媒体 GET 下载最多尝试三次，间隔 2/4 秒；付费生成 POST 不自动重试。下载没有 Range 断点续传。结果 URL 失效时先检查已保存文件或供应商恢复方式，不自动付费补生成。

临时目录可能被系统清理，文件缺失不代表允许再次付费。原始响应及清单可能含临时签名 URL，不将其或 Base64 正文粘贴到聊天中。
