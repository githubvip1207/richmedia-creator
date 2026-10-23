"""供应商配置与必备依赖测试替身，隔离真实项目 .env、进程环境变量及机器依赖。"""
from contextlib import contextmanager
from unittest.mock import patch

@contextmanager
def config_fixture(values, clear=False):
    def value(key):
        return values.get(key)
    with patch('providers.config_value', side_effect=value), patch('providers.transport.config_value', side_effect=value), patch('commands.submit.config_value', side_effect=value), patch('commands.submit.require_dependencies'):
        yield
