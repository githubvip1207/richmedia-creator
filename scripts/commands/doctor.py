r"""命令行调用

    python3 "$SKILL/scripts/main.py" doctor
    python3 "$SKILL/scripts/main.py" doctor --dependencies --exchange-rate --pricing

    # --dependencies：仅选择依赖修复类别，可选，默认不单独选择。
    # --exchange-rate：选择更新当前项目 .env 汇率，可选。
    # --pricing：选择核对并更新技能中的价格快照，可选。
    # 开关可组合；全部省略时，只修复缺失依赖和异常汇率。

输入文件格式

不接收命令行指定的 JSON 文件，也不读取 stdin。
读取当前目录 .env；它是 KEY=VALUE 文本，不是 JSON，格式见 __init__.py 的运行上下文。

标准输出格式

```jsonc
{
  "repairs": [ // Repair[]；实际执行的修复结果；无需修复时可以为空。
    {
      "item": "exchange_rate", // string；sd25-pe/ffprobe/exchange_rate/volcengine_pricing/byteplus_pricing。
      "status": "repaired", // "repaired" | "failed"；此项修复成功或失败。
      "reason": "示例说明：输出时长由模型自动决定", // string?；部分失败分支提供的原因；不是所有失败分支都会有该字段。
      "rate": 7.0, // number?；仅汇率更新成功时：1 美元对应人民币金额。
      "expires_at": "2026-10-27T00:00:00+00:00", // string?；仅汇率更新成功时：带时区 ISO 8601 到期时间。
      "data_date": "2026-10-26", // string?；仅汇率更新成功时：数据源汇率观测日 YYYY-MM-DD。
      "source": "https://example.com/reference.png", // string?；仅汇率更新成功时：固定公开汇率源 URL。
      "verified_on": "2026-10-26" // string?；仅价格更新成功时：快照核实日期 YYYY-MM-DD。
    }
  ],
  "check": { // CheckReport；修复后完整检查；所有嵌套字段见 commands/check.py。
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
  },
  "note": "说明文本" // string；密钥需本地配置、本次未提交生成等说明。
}
```

文件输出格式

- 启用汇率修复时：更新当前目录 .env 的 USD_CNY 与 USD_CNY_EXPIRES_AT；仍为 KEY=VALUE 文本，格式见 __init__.py。
- --pricing 成功时：更新 models/<provider>-pricing.json；完整 JSON 格式见 __init__.py 的“价格快照文件”。
- 依赖修复通过安装器完成，不产生本命令自定义的 JSON 输出文件。

失败输出

修复项含 failed 时，仍输出上述完整 stdout 报告，退出码为 1。其他已捕获异常格式见 __init__.py。
"""

import urllib.error
from core.exchange_rate import fx_state, update_exchange_rate
from core.dependencies import repair_dependencies
from .check import check


def doctor(dependencies=False, exchange_rate=False, pricing=False):
    """无选项时修复缺失依赖及异常汇率；定向参数只处理指定类别，最后始终复查。"""
    all_items = not dependencies and (not exchange_rate) and not pricing
    results = repair_dependencies() if dependencies or all_items else []
    if exchange_rate or (all_items and fx_state()["status"] != "ok"):
        try:
            results.append(update_exchange_rate())
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
            detail = (
                "HTTP " + str(error.code)
                if isinstance(error, urllib.error.HTTPError)
                else type(error).__name__
            )
            results.append(
                {
                    "item": "exchange_rate",
                    "status": "failed",
                    "reason": "Could not obtain a valid fresh rate ("
                    + detail
                    + "); previous .env values were preserved",
                }
            )
    if pricing:
        from core.pricing import load_pricing, refresh
        from core.catalogs import ROOT
        from core.submission_store import write
        for provider in ('volcengine', 'byteplus'):
            previous = load_pricing(provider)
            updated = refresh(provider, previous, None)
            if updated.get('refresh_status'):
                results.append({'item': provider + '_pricing', 'status': 'failed',
                                'reason': updated['refresh_status']})
            else:
                write(ROOT / 'models' / (provider + '-pricing.json'), updated)
                results.append({'item': provider + '_pricing', 'status': 'repaired',
                                'verified_on': updated['verified_on']})
    report = check()
    return {
        "repairs": results,
        "check": report,
        "note": "Missing API keys must be supplied locally. No media generation was submitted.",
    }


def run(args):
    return doctor(args.dependencies, args.exchange_rate, getattr(args, 'pricing', False))
