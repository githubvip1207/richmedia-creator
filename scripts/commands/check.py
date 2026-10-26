r"""命令行调用

    python3 "$SKILL/scripts/main.py" check

    # 无额外命令行参数。读取当前项目目录的 .env。

输入文件格式

不接收命令行指定的 JSON 文件，也不读取 stdin。
读取当前目录 .env；它是 KEY=VALUE 文本，不是 JSON，格式见 __init__.py 的运行上下文。

标准输出格式

```jsonc
{
  "pricing": { // object；各供应商本地价格快照的时效；不发起联网核价。
    "volcengine": { // Freshness；status/age_days/verified_on，逐字段见 __init__.py。
      "status": "fresh", // "fresh" | "stale" | "invalid"；7 天以内、过期或日期无效。
      "age_days": 0, // integer | null；距核实日期的 UTC 天数；无法解析时 null。
      "verified_on": "2026-10-26" // string | null；YYYY-MM-DD 核实日期；缺失时 null。
    }
  },
  "configuration": { // object；项目配置诊断，不包含任何密钥原文。
    "file": "/absolute/project/.env", // string | null；实际读取的 .env 绝对路径；未找到时 null。
    "status": "ok", // "ok" | "missing"；是否找到项目 .env，不表示供应商鉴权成功。
    "suppliers": [ // object[]；已配置非空 API 密钥的供应商列表。
      {
        "id": "volcengine", // Provider；供应商标识。
        "name": "formula_tokens" // string；供应商显示名称。
      }
    ],
    "issues": [ // object[]；缺失供应商密钥的诊断条目。
      {
        "item": "exchange_rate", // string；缺失配置名称，例如 VOLCENGINE_API_KEY。
        "status": "missing", // "missing"；当前条目状态。
        "action": "运行对应 doctor 修复命令" // string；本地配置建议，不包含密钥。
      }
    ],
    "exchange_rate": { // object；项目 USD/CNY 缓存状态。
      "status": "ok", // "ok" | "missing" | "expired" | "invalid"；汇率检查结果。
      "expires_at": "2026-10-27T00:00:00+00:00", // string?；仅有效时出现；带时区 ISO 8601 到期时间。
      "action": "运行对应 doctor 修复命令" // string?；非有效状态时出现；修复建议。
    }
  },
  "dependencies": { // object；两项必需依赖的本地安装情况。
    "sd25_pe": { // DependencyStatus；提示词优化技能的检查结果，定义见下。
      "status": "ok", // "ok" | "missing"；依赖可用或缺失。
      "path": "/absolute/output.png", // string?；可用时出现；技能文件或程序绝对路径。
      "action": "运行对应 doctor 修复命令" // string?；缺失时出现；安装/修复建议。
    },
    "ffprobe": { // DependencyStatus；媒体测量工具的检查结果，定义见下。
      "status": "ok", // "ok" | "missing"；依赖可用或缺失。
      "path": "/absolute/output.png", // string?；可用时出现；技能文件或程序绝对路径。
      "action": "运行对应 doctor 修复命令" // string?；缺失时出现；安装/修复建议。
    }
  },
  "network_checked": false // false；未请求供应商 API，不能据此确认密钥可用。
}
```

文件输出格式

无文件输出。

失败输出

已捕获异常的 stderr JSON 格式见 __init__.py；命令行参数错误使用 argparse usage 文本。
"""

import shutil
from core.envfile import read_config, load_project_env
from core.exchange_rate import fx_state
from core import dependencies
from providers import PROVIDERS


def check():
    values = read_config()
    suppliers = []
    issues = []
    for name, info in PROVIDERS.items():
        key = info["adapter"].KEY_ENV
        if values.get(key):
            suppliers.append({"id": name, "name": info["name"]})
        else:
            issues.append(
                {
                    "item": key,
                    "status": "missing",
                    "action": "Configure this API key locally in .env to enable the supplier",
                }
            )
    from core.pricing import load_pricing, freshness
    return {
        'pricing': {name: freshness(load_pricing(name)) for name in PROVIDERS},
        "configuration": {
            "file": load_project_env(),
            "status": "ok" if load_project_env() else "missing",
            "suppliers": suppliers,
            "issues": issues,
            "exchange_rate": fx_state(),
        },
        "dependencies": {
            "sd25_pe": dependencies.skill_status(),
            "ffprobe": (
                {"status": "ok", "path": shutil.which("ffprobe")}
                if shutil.which("ffprobe")
                else {
                    "status": "missing",
                    "action": "Run doctor --dependencies; required for every task",
                }
            ),
        },
        "network_checked": False,
    }


def run(args):
    return check()
