# 供应商注册与解析：显示名称、币种、模型目录、价目表和适配器一起绑定。
# 两家凭证彼此独立；多家已配置时不猜测选择，要求调用方明确指定或走比价流程。
"""Provider identities, never selected by a shared API key or a model prefix."""
from core.envfile import config_value
from . import volcengine, byteplus

# 每个供应商独立绑定适配器、结算币种和目录文件，禁止仅替换地址却复用价格或凭证。
PROVIDERS = {
    'volcengine': {'name':'Volcengine', 'adapter':volcengine,
                  'currency':'CNY', 'catalog':'volcengine.json', 'pricing':'volcengine-pricing.json'},
    'byteplus': {'name':'BytePlus', 'adapter':byteplus,
                 'currency':'USD', 'catalog':'byteplus.json', 'pricing':'byteplus-pricing.json'}
}


# 从固定注册表查找供应商；未知名称直接报错，不能由请求传入自定义主机。
def get_provider(name):
    if name not in PROVIDERS:
        raise ValueError('Unknown provider: ' + str(name))
    return PROVIDERS[name]


# 仅判断 .env 中各供应商自己的密钥配置是否非空，不验证其有效性、权限或余额。
def configured():
    return [name for name,p in PROVIDERS.items() if config_value(p['adapter'].KEY_ENV)]


# 优先使用请求明确指定的供应商；只有一家已配置时可自动解析。
# 多家已配置则要求选择，没有密钥时仅为离线计划保留 Volcengine 默认值。
def resolve_provider(spec):
    if spec.get('provider'):
        get_provider(spec['provider'])
        return spec['provider']
    active = configured()
    if len(active) > 1:
        raise ValueError('Multiple suppliers configured: select a supplier and set provider explicitly')
    return active[0] if active else 'volcengine'
