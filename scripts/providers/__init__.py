# 供应商注册与解析：显示名称、币种、模型目录、价目表和适配器一起绑定。
# 两家凭证彼此独立；多家已配置时不猜测选择，要求调用方明确指定或走比价流程。
"""明确区分供应商身份，不通过共用密钥或模型前缀选择供应商。"""

from core.envfile import config_value
from .volcengine import client as volcengine
from .byteplus import client as byteplus

# 每个供应商独立绑定适配器、结算币种和目录文件，禁止仅替换地址却复用价格或凭证。
PROVIDERS = {
    "volcengine": {
        "name": "Volcengine",
        "adapter": volcengine,
        "currency": "CNY",
        "catalog": "volcengine.json",
        "pricing": "volcengine-pricing.json",
    },
    "byteplus": {
        "name": "BytePlus",
        "adapter": byteplus,
        "currency": "USD",
        "catalog": "byteplus.json",
        "pricing": "byteplus-pricing.json",
    },
}


# 从固定注册表查找供应商；未知名称直接报错，不能由请求传入自定义主机。
def get_provider(name):
    if name not in PROVIDERS:
        raise ValueError("Unknown provider: " + str(name))
    return PROVIDERS[name]


# 仅判断 .env 中各供应商自己的密钥配置是否非空，不验证其有效性、权限或余额。
def configured():
    return [name for name, p in PROVIDERS.items() if config_value(p["adapter"].KEY_ENV)]


# 优先使用请求明确指定的供应商；只有一家已配置时可自动解析。
# 多家已配置则要求选择，没有密钥时仅为离线计划保留 Volcengine 默认值。
def resolve_provider(spec):
    if spec.get("provider"):
        get_provider(spec["provider"])
        return spec["provider"]
    active = configured()
    if len(active) > 1:
        raise ValueError(
            "Multiple suppliers configured: select a supplier and set provider explicitly"
        )
    return active[0] if active else "volcengine"


def get_capability(provider, operation):
    """仅解析已注册的供应商及能力模块，不接受调用方指定的模块路径。"""
    from importlib import import_module
    from core.operations import OPERATIONS

    get_provider(provider)
    if operation not in OPERATIONS:
        raise ValueError("operation must be one of: " + ", ".join(OPERATIONS))
    return import_module("providers." + provider + "." + operation.replace("-", "_"))


def capability_for_record(record):
    """根据 submit 保存的固定编译方案，为状态查询和交付选择能力模块。"""
    from core.validation import require

    compiled = record["execution"]["compiled"]
    provider, operation = compiled["provider"], compiled["operation"]
    require(
        record.get("provider", provider) == provider
        and record.get("operation", operation) == operation
        and record["execution"].get("provider", provider) == provider,
        "Submission record supplier/operation differs from compiled plan",
    )
    return get_capability(provider, operation)


def compile_request(spec, measured_assets=None):
    from core.validation import require

    require(isinstance(spec, dict), "Request must be an object")
    require(
        "payload" in spec,
        "Submission requires a provider-native payload; legacy request format is not supported",
    )
    return get_capability(spec.get("provider"), spec.get("operation")).compile_request(
        spec, measured_assets
    )


def compile_cost_inputs(inputs, measured_assets=None):
    return get_capability(inputs["provider"], inputs["operation"]).validate_cost_inputs(
        inputs, measured_assets
    )


def calculate_inputs(inputs, pricing=None, context=None, fx=None, measured_assets=None):
    return get_capability(inputs["provider"], inputs["operation"]).calculate_inputs(
        inputs, pricing, context, fx, measured_assets
    )


def calculate_asset_inputs(inputs, fx=None):
    from core.validation import require

    require(isinstance(inputs, dict), "Cost input must be a JSON object")
    for field in ("provider", "model", "operation"):
        require(
            isinstance(inputs.get(field), str) and bool(inputs[field]),
            field + " must be a nonempty string",
        )
    return get_capability(inputs["provider"], inputs["operation"]).cost(inputs, fx)


def estimate(compiled, context=None, pricing=None, fx=None):
    return get_capability(compiled["provider"], compiled["operation"]).calculate_cost(
        compiled, context, pricing, fx
    )


def consume_quote(spec, quote):
    from core.validation import require

    require(
        "payload" in spec,
        "Submission requires a provider-native payload; legacy request format is not supported",
    )
    from core.cost_quote import consume_quote as bind_quote

    capability = get_capability(spec.get("provider"), spec.get("operation"))
    return bind_quote(
        spec, quote, capability.compile_request, get_provider(spec["provider"])["currency"]
    )
